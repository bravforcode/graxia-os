"""
Handles payment gateway webhooks and creates orders.

NOTE (2026-08): rewritten against the CURRENT Revenue OS schema — the previous
version referenced obsolete columns (Order.total_amount, Order.delivery_status,
Customer.total_orders/total_spent) that no longer exist. Current contract:
Order.amount_cents (cents), Order.product_id (NOT NULL, from metadata), PAID on
success, fulfilled immediately via FulfillmentService (idempotent).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import DeliveryStatus, OrderStatus
from ..models import Customer, Order, Product
from .fulfillment_service import FulfillmentService


class WebhookProcessor:
    """Process payment webhooks and create orders"""

    @classmethod
    async def _apply_customer_stats(cls, db: AsyncSession, customer: Customer, amount_cents: int) -> None:
        customer.total_spent_cents = (customer.total_spent_cents or 0) + amount_cents
        now = datetime.utcnow()
        if customer.first_purchase_at is None:
            customer.first_purchase_at = now
        customer.last_purchase_at = now
        await db.flush()

    @classmethod
    async def process_stripe_checkout_completed(
        cls,
        session: Dict[str, Any],
        db: AsyncSession
    ) -> Order:
        """Process Stripe checkout.session.completed"""
        customer_email = (session.get("customer_details") or {}).get("email") or session.get("customer_email")
        customer_name = (session.get("customer_details") or {}).get("name") or session.get("customer_name")
        amount_cents = int(session.get("amount_total", 0))  # Stripe amounts are cents
        if amount_cents <= 0:
            raise ValueError("checkout.session.completed amount must be greater than 0")
        currency = (session.get("currency") or "usd").upper()
        session_id = session.get("id")
        payment_intent = session.get("payment_intent")

        if not customer_email or not session_id:
            raise ValueError("checkout.session.completed missing email or id")

        # Check for existing order (idempotent)
        existing = await db.execute(
            select(Order).where(
                Order.platform == "stripe",
                Order.platform_order_id == session_id
            )
        )
        if existing.scalar_one_or_none():
            return None  # Already processed

        # Resolve product
        product_id = (session.get("metadata") or {}).get("product_id")
        product = None
        if product_id:
            product = await db.get(Product, product_id)
        if product is None:
            raise ValueError("product_id required in webhook metadata")

        customer = await cls._get_or_create_customer(db, customer_email, customer_name)

        order = Order(
            platform="stripe",
            platform_order_id=session_id,
            customer_email=customer_email,
            customer_name=customer_name,
            product_id=product.id,
            amount_cents=amount_cents,
            currency=currency,
            status=OrderStatus.PAID,
            stripe_payment_intent=payment_intent,
            metadata_={"stripe_session": session},
        )
        db.add(order)
        await db.flush()
        await cls._apply_customer_stats(db, customer, amount_cents)
        await db.commit()
        await db.refresh(order)

        # Digital fulfillment: fulfill immediately (idempotent — fulfill_order is
        # safe to re-run; the sweep task catches anything missed).
        await FulfillmentService.fulfill_order(db, order.id, auto_queue_email=True)

        return order

    @classmethod
    async def process_stripe_invoice_paid(
        cls,
        invoice: Dict[str, Any],
        db: AsyncSession
    ) -> Order:
        """Process Stripe invoice.paid (subscriptions)"""
        invoice_id = invoice.get("id")
        customer_email = invoice.get("customer_email")
        amount_cents = int(invoice.get("amount_paid", 0))
        if amount_cents <= 0:
            raise ValueError("invoice.paid amount must be greater than 0")
        currency = (invoice.get("currency") or "usd").upper()
        product_id = (invoice.get("metadata") or {}).get("product_id")

        if not customer_email or not invoice_id:
            raise ValueError("invoice.paid missing email or id")

        existing = await db.execute(
            select(Order).where(
                Order.platform == "stripe",
                Order.platform_order_id == invoice_id
            )
        )
        if existing.scalar_one_or_none():
            return None

        product = None
        if product_id:
            product = await db.get(Product, product_id)
        if product is None:
            raise ValueError("product_id required in invoice metadata")

        customer = await cls._get_or_create_customer(db, customer_email)

        order = Order(
            platform="stripe",
            platform_order_id=invoice_id,
            customer_email=customer_email,
            product_id=product.id,
            amount_cents=amount_cents,
            currency=currency,
            status=OrderStatus.PAID,
            metadata_={"stripe_invoice": invoice, "type": "subscription"},
        )
        db.add(order)
        await db.flush()
        await cls._apply_customer_stats(db, customer, amount_cents)
        await db.commit()
        await db.refresh(order)

        await FulfillmentService.fulfill_order(db, order.id, auto_queue_email=True)

        return order

    @classmethod
    async def process_stripe_payment_failed(
        cls,
        invoice: Dict[str, Any],
        db: AsyncSession
    ) -> None:
        """Log failed payment (dunning email hook point)."""
        pass

    @classmethod
    async def process_stripe_refund(
        self,
        charge: Dict[str, Any],
        db: AsyncSession
    ) -> Order:
        """Process Stripe refund (charge.refunded). The charge id (ch_*) differs from
        the payment intent id (pi_*), so match against either the payment_intent
        column or the stored session metadata."""
        charge_id = charge.get("id")
        order = (
            await db.execute(
                select(Order).where(Order.stripe_payment_intent == charge_id)
            )
        ).scalar_one_or_none()
        if order is None and charge_id:
            # Fallback: the session metadata may hold the payment_intent under a
            # different shape — match any order whose stored session id is the charge's
            # payment_intent parent.
            for candidate in (
                await db.execute(select(Order).where(Order.platform == "stripe"))
            ).scalars().all():
                meta = candidate.metadata_ or {}
                session_meta = (meta.get("stripe_session") or {})
                if isinstance(session_meta, dict) and session_meta.get("payment_intent") == charge_id:
                    order = candidate
                    break

        if order:
            order.status = OrderStatus.REFUNDED
            if order.metadata_ is None:
                order.metadata_ = {}
            order.metadata_["refunded_at"] = datetime.utcnow().isoformat()
            await db.commit()

        return order

    @classmethod
    async def process_gumroad_sale(
        cls,
        sale_data: Dict[str, Any],
        db: AsyncSession
    ) -> Order:
        """Process Gumroad sale"""
        sale_id = sale_data["sale_id"]
        email = sale_data["email"]
        price_cents = int(Decimal(str(sale_data["price"])) * 100)
        product_id = sale_data.get("product_id")

        existing = await db.execute(
            select(Order).where(
                Order.platform == "gumroad",
                Order.platform_order_id == sale_id
            )
        )
        if existing.scalar_one_or_none():
            return None

        product = None
        if product_id:
            product = await db.get(Product, product_id)
        if product is None:
            raise ValueError("product_id required in gumroad sale data")

        customer = await cls._get_or_create_customer(db, email)

        order = Order(
            platform="gumroad",
            platform_order_id=sale_id,
            customer_email=email,
            product_id=product.id,
            amount_cents=price_cents,
            currency="USD",
            status=OrderStatus.PAID,
            metadata_={"gumroad_data": sale_data},
        )
        db.add(order)
        await db.flush()
        await cls._apply_customer_stats(db, customer, price_cents)
        await db.commit()
        await db.refresh(order)

        await FulfillmentService.fulfill_order(db, order.id, auto_queue_email=True)

        return order

    @classmethod
    async def process_paypal_payment_completed(
        cls,
        resource: Dict[str, Any],
        db: AsyncSession
    ) -> Order:
        """Process PayPal payment capture"""
        capture_id = resource.get("id")
        amount = resource.get("amount", {})
        amount_cents = int(Decimal(str(amount.get("value", "0"))) * 100)
        if amount_cents <= 0:
            raise ValueError("paypal capture amount must be greater than 0")
        currency = (amount.get("currency_code") or "USD").upper()
        product_id = (resource.get("metadata") or {}).get("product_id")
        customer_email = (resource.get("payer") or {}).get("email_address")

        if not capture_id:
            raise ValueError("paypal capture missing id")

        existing = await db.execute(
            select(Order).where(
                Order.platform == "paypal",
                Order.platform_order_id == capture_id
            )
        )
        if existing.scalar_one_or_none():
            return None

        product = None
        if product_id:
            product = await db.get(Product, product_id)
        if product is None:
            raise ValueError("product_id required in paypal metadata")

        order = Order(
            platform="paypal",
            platform_order_id=capture_id,
            customer_email=customer_email or "unknown@paypal.local",
            product_id=product.id,
            amount_cents=amount_cents,
            currency=currency,
            status=OrderStatus.PAID,
            metadata_={"paypal_resource": resource},
        )
        db.add(order)
        await db.commit()
        await db.refresh(order)

        await FulfillmentService.fulfill_order(db, order.id, auto_queue_email=True)

        return order

    @classmethod
    async def process_paypal_refund(
        cls,
        resource: Dict[str, Any],
        db: AsyncSession
    ) -> None:
        """Process PayPal refund"""
        capture_id = resource.get("links", [{}])[0].get("href", "").split("/")[-1]
        order = (
            await db.execute(
                select(Order).where(
                    Order.platform == "paypal",
                    Order.platform_order_id == capture_id
                )
            )
        ).scalar_one_or_none()

        if order:
            order.status = OrderStatus.REFUNDED
            await db.commit()

    @classmethod
    async def _get_or_create_customer(
        cls,
        db: AsyncSession,
        email: str,
        name: str = None
    ) -> Customer:
        """Get or create customer by email"""
        result = await db.execute(
            select(Customer).where(Customer.email == email)
        )
        customer = result.scalar_one_or_none()

        if not customer:
            customer = Customer(
                email=email,
                name=name,
                total_spent_cents=0,
            )
            db.add(customer)
            await db.flush()

        return customer
