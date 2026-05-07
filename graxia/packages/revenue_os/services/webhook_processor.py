"""
Revenue OS — Webhook Processor Service
Handles payment gateway webhooks and creates orders
"""
from decimal import Decimal
from datetime import datetime
from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models import Order, Customer, Product
from ..enums import OrderStatus, DeliveryStatus


class WebhookProcessor:
    """Process payment webhooks and create orders"""

    async def process_stripe_checkout_completed(
        self,
        session: Dict[str, Any],
        db: AsyncSession
    ) -> Order:
        """Process Stripe checkout.session.completed"""

        # Extract data
        customer_email = session.get("customer_details", {}).get("email")
        customer_name = session.get("customer_details", {}).get("name")
        amount_total = session.get("amount_total", 0) / 100  # Convert from cents
        currency = session.get("currency", "usd").upper()
        session_id = session.get("id")

        # Check for existing order
        existing = await db.execute(
            select(Order).where(
                Order.platform == "stripe",
                Order.platform_order_id == session_id
            )
        )
        if existing.scalar_one_or_none():
            return None  # Already processed

        # Get or create customer
        customer = await self._get_or_create_customer(
            db, customer_email, customer_name
        )

        # Create order
        order = Order(
            platform="stripe",
            platform_order_id=session_id,
            customer_email=customer_email,
            customer_name=customer_name,
            currency=currency,
            total_amount=Decimal(str(amount_total)),
            status=OrderStatus.PAID,
            delivery_status=DeliveryStatus.PENDING,
            metadata={"stripe_session": session}
        )

        db.add(order)
        await db.flush()

        # Update customer stats
        customer.total_orders += 1
        customer.total_spent += float(amount_total)

        await db.commit()
        await db.refresh(order)

        return order

    async def process_stripe_invoice_paid(
        self,
        invoice: Dict[str, Any],
        db: AsyncSession
    ) -> Order:
        """Process Stripe invoice.paid (subscriptions)"""

        invoice_id = invoice.get("id")
        customer_email = invoice.get("customer_email")
        amount_paid = invoice.get("amount_paid", 0) / 100
        currency = invoice.get("currency", "usd").upper()

        # Check existing
        existing = await db.execute(
            select(Order).where(
                Order.platform == "stripe",
                Order.platform_order_id == invoice_id
            )
        )
        if existing.scalar_one_or_none():
            return None

        order = Order(
            platform="stripe",
            platform_order_id=invoice_id,
            customer_email=customer_email,
            currency=currency,
            total_amount=Decimal(str(amount_paid)),
            status=OrderStatus.PAID,
            delivery_status=DeliveryStatus.COMPLETED,
            metadata={
                "stripe_invoice": invoice,
                "type": "subscription"
            }
        )

        db.add(order)
        await db.commit()
        await db.refresh(order)

        return order

    async def process_stripe_payment_failed(
        self,
        invoice: Dict[str, Any],
        db: AsyncSession
    ) -> None:
        """Process failed payment"""
        # Log failed payment, could trigger dunning email
        pass

    async def process_stripe_refund(
        self,
        charge: Dict[str, Any],
        db: AsyncSession
    ) -> Order:
        """Process Stripe refund"""

        # Find original order by charge ID
        charge_id = charge.get("id")

        order = await db.execute(
            select(Order).where(
                Order.metadata["stripe_session"]["payment_intent"].astext == charge_id
            )
        )
        order = order.scalar_one_or_none()

        if order:
            order.status = OrderStatus.REFUNDED
            order.metadata["refunded_at"] = datetime.utcnow().isoformat()
            await db.commit()

        return order

    async def process_gumroad_sale(
        self,
        sale_data: Dict[str, Any],
        db: AsyncSession
    ) -> Order:
        """Process Gumroad sale"""

        sale_id = sale_data["sale_id"]
        email = sale_data["email"]
        price = sale_data["price"]

        # Check existing
        existing = await db.execute(
            select(Order).where(
                Order.platform == "gumroad",
                Order.platform_order_id == sale_id
            )
        )
        if existing.scalar_one_or_none():
            return None

        # Get or create customer
        customer = await self._get_or_create_customer(db, email)

        # Create order
        order = Order(
            platform="gumroad",
            platform_order_id=sale_id,
            customer_email=email,
            currency="USD",
            total_amount=Decimal(str(price)),
            status=OrderStatus.PAID,
            delivery_status=DeliveryStatus.COMPLETED,
            metadata={"gumroad_data": sale_data}
        )

        db.add(order)
        await db.flush()

        # Update customer
        customer.total_orders += 1
        customer.total_spent += float(price)

        await db.commit()
        await db.refresh(order)

        return order

    async def process_paypal_payment_completed(
        self,
        resource: Dict[str, Any],
        db: AsyncSession
    ) -> Order:
        """Process PayPal payment capture"""

        capture_id = resource.get("id")
        amount = resource.get("amount", {})
        value = amount.get("value", "0")
        currency = amount.get("currency_code", "USD")

        # Check existing
        existing = await db.execute(
            select(Order).where(
                Order.platform == "paypal",
                Order.platform_order_id == capture_id
            )
        )
        if existing.scalar_one_or_none():
            return None

        order = Order(
            platform="paypal",
            platform_order_id=capture_id,
            currency=currency,
            total_amount=Decimal(value),
            status=OrderStatus.PAID,
            delivery_status=DeliveryStatus.PENDING,
            metadata={"paypal_resource": resource}
        )

        db.add(order)
        await db.commit()
        await db.refresh(order)

        return order

    async def process_paypal_refund(
        self,
        resource: Dict[str, Any],
        db: AsyncSession
    ) -> None:
        """Process PayPal refund"""
        # Find and update order
        capture_id = resource.get("links", [{}])[0].get("href", "").split("/")[-1]

        order = await db.execute(
            select(Order).where(
                Order.platform == "paypal",
                Order.platform_order_id == capture_id
            )
        )
        order = order.scalar_one_or_none()

        if order:
            order.status = OrderStatus.REFUNDED
            await db.commit()

    async def _get_or_create_customer(
        self,
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
                total_orders=0,
                total_spent=0.0
            )
            db.add(customer)
            await db.flush()

        return customer
