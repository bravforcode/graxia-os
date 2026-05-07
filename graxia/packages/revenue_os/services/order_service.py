"""
Revenue OS Order Service
Idempotent order creation and management
"""
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime
import structlog

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError, OperationalError, TimeoutError as SQLTimeoutError

from ..models import Order, LedgerEntry, Customer, Product
from ..enums import OrderStatus, LedgerEntryType
from ..core.db_ops import atomic_operation
from ..core.validators import (
    validate_email,
    validate_amount_cents,
    validate_string_length,
    validate_currency,
    ValidationError,
)
from .outbox_service import OutboxService

logger = structlog.get_logger()


class OrderService:
    """
    Order management service with full idempotency guarantees.
    Safe to call multiple times with the same platform_order_id.
    """

    @staticmethod
    async def create_order(
        db: AsyncSession,
        platform: str,
        platform_order_id: str,
        customer_email: str,
        product_id: UUID,
        amount_cents: int,
        currency: str = "THB",
        customer_name: Optional[str] = None,
        stripe_payment_intent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Order:
        """
        Create an order with full idempotency guarantees.
        Safe to call multiple times with the same stripe event_id.

        Args:
            db: Database session
            platform: Payment platform ("stripe" | "gumroad" | "manual")
            platform_order_id: Platform's order ID
            customer_email: Customer email
            product_id: Product UUID
            amount_cents: Amount in cents
            currency: Currency code (default: THB)
            customer_name: Optional customer name
            stripe_payment_intent: Optional Stripe payment intent ID
            metadata: Optional metadata dictionary

        Returns:
            Order: Created or existing order

        Raises:
            ValueError: If product not found or invalid data
            ValidationError: If input validation fails
        """
        # Validate inputs
        try:
            validate_email(customer_email)
            validate_amount_cents(amount_cents)
            validate_currency(currency)
            validate_string_length(platform, "platform", max_length=50)
            validate_string_length(platform_order_id, "platform_order_id", max_length=255)
            if customer_name:
                validate_string_length(customer_name, "customer_name", max_length=255)
        except ValidationError as e:
            logger.error(
                "order_validation_failed",
                error=str(e),
                customer_email=customer_email,
                amount_cents=amount_cents,
            )
            raise

        idempotency_key = f"{platform}:{platform_order_id}"

        async with atomic_operation(db):
            try:
                # Check idempotency first
                result = await db.execute(
                    select(Order).where(Order.idempotency_key == idempotency_key)
                )
                existing = result.scalar_one_or_none()

                if existing:
                    logger.info(
                        "order_idempotent_return",
                        idempotency_key=idempotency_key,
                        order_id=str(existing.id),
                    )
                    return existing

                # Verify product exists
                product_result = await db.execute(
                    select(Product).where(Product.id == product_id)
                )
                product = product_result.scalar_one_or_none()
                if not product:
                    raise ValueError(f"Product {product_id} not found")

                # Get or create customer
                customer = await OrderService._get_or_create_customer(
                    db, customer_email, customer_name
                )

                # Create order
                order = Order(
                    platform=platform,
                    platform_order_id=platform_order_id,
                    idempotency_key=idempotency_key,
                    customer_id=customer.id,
                    customer_email=customer_email,
                    customer_name=customer_name,
                    product_id=product_id,
                    amount_cents=amount_cents,
                    currency=currency,
                    status=OrderStatus.PROCESSING,
                    saga_state="payment_received",
                    stripe_payment_intent=stripe_payment_intent,
                    metadata_=metadata or {},
                )
                db.add(order)
                await db.flush()

                # Create ledger entry in same transaction
                ledger_entry = LedgerEntry(
                    order_id=order.id,
                    entry_type=LedgerEntryType.CHARGE,
                    amount_cents=amount_cents,
                    currency=currency,
                    description=f"Payment for {product.name}",
                )
                db.add(ledger_entry)
                await db.flush()

                # Update customer stats
                customer.total_spent_cents += amount_cents
                if not customer.first_purchase_at:
                    customer.first_purchase_at = datetime.utcnow()
                customer.last_purchase_at = datetime.utcnow()

                # Publish outbox event (HR-07: Transactional Outbox)
                # This is written in the same transaction as the order
                await OutboxService.publish_order_created(
                    db=db,
                    order_id=order.id,
                    customer_email=customer_email,
                    amount_cents=amount_cents,
                    currency=currency,
                    platform=platform,
                    product_id=product_id,
                )

                await db.commit()

                logger.info(
                    "order_created",
                    order_id=str(order.id),
                    customer_email=customer_email,
                    product_id=str(product_id),
                    amount_cents=amount_cents,
                    platform=platform,
                )

                return order

            except IntegrityError as e:
                # Concurrent request created it first — fetch and return
                await db.rollback()
                result = await db.execute(
                    select(Order).where(Order.idempotency_key == idempotency_key)
                )
                existing = result.scalar_one_or_none()
                if existing:
                    logger.info(
                        "order_concurrent_creation",
                        idempotency_key=idempotency_key,
                        order_id=str(existing.id),
                    )
                    return existing
                raise
            except (OperationalError, SQLTimeoutError) as e:
                # Database connection or timeout error
                await db.rollback()
                logger.error(
                    "order_database_error",
                    error=str(e),
                    error_type=type(e).__name__,
                    idempotency_key=idempotency_key,
                )
                raise ValueError(f"Database error: {str(e)}") from e

    @staticmethod
    async def _get_or_create_customer(
        db: AsyncSession,
        email: str,
        name: Optional[str] = None,
    ) -> Customer:
        """
        Get existing customer or create new one.

        Args:
            db: Database session
            email: Customer email (already validated)
            name: Optional customer name

        Returns:
            Customer: Existing or newly created customer
        """
        try:
            result = await db.execute(
                select(Customer).where(Customer.email == email)
            )
            customer = result.scalar_one_or_none()

            if not customer:
                customer = Customer(
                    email=email,
                    name=name,
                )
                db.add(customer)
                await db.flush()
                logger.info("customer_created", email=email)

            return customer
        except (OperationalError, SQLTimeoutError) as e:
            logger.error(
                "customer_database_error",
                error=str(e),
                email=email,
            )
            raise

    @staticmethod
    async def get_order_by_id(
        db: AsyncSession,
        order_id: UUID,
    ) -> Optional[Order]:
        """Get order by ID."""
        result = await db.execute(
            select(Order).where(Order.id == order_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_order_by_platform_id(
        db: AsyncSession,
        platform: str,
        platform_order_id: str,
    ) -> Optional[Order]:
        """Get order by platform order ID."""
        result = await db.execute(
            select(Order).where(
                Order.platform == platform,
                Order.platform_order_id == platform_order_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_order_status(
        db: AsyncSession,
        order_id: UUID,
        status: OrderStatus,
    ) -> Order:
        """Update order status."""
        order = await OrderService.get_order_by_id(db, order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        old_status = order.status
        order.status = status
        await db.commit()

        logger.info(
            "order_status_updated",
            order_id=str(order_id),
            old_status=old_status.value,
            new_status=status.value,
        )

        return order
