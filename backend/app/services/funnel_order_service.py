import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.funnel import DigitalProduct, FunnelCheckoutSession, FunnelOrder, FunnelOrderItem
from app.services.funnel_delivery_service import FunnelDeliveryService

logger = logging.getLogger(__name__)

class FunnelOrderService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.delivery_service = FunnelDeliveryService(db)

    async def create_order_from_checkout_completed(self, session_data: dict) -> Optional[FunnelOrder]:
        """
        Create a FunnelOrder and FunnelOrderItem from a completed Stripe checkout session.
        This method is idempotent based on stripe_session_id.
        """
        stripe_session_id = session_data.get("id")
        metadata = session_data.get("metadata", {})
        
        org_id_str = metadata.get("organization_id")
        product_id_str = metadata.get("product_id")
        checkout_id_str = metadata.get("funnel_checkout_session_id")

        if not all([org_id_str, product_id_str, checkout_id_str]):
            logger.error(f"Webhook metadata missing required fields: {metadata}")
            return None

        organization_id = UUID(org_id_str)
        product_id = UUID(product_id_str)
        checkout_session_id = UUID(checkout_id_str)

        # Idempotency check: Does an order for this stripe_session_id already exist?
        stmt = select(FunnelOrder).where(FunnelOrder.stripe_session_id == stripe_session_id)
        result = await self.db.execute(stmt)
        existing_order = result.scalar_one_or_none()
        if existing_order:
            logger.info(f"Order for stripe session {stripe_session_id} already exists (ID: {existing_order.id})")
            return existing_order

        # Load local checkout session
        stmt = select(FunnelCheckoutSession).where(
            and_(
                FunnelCheckoutSession.id == checkout_session_id,
                FunnelCheckoutSession.organization_id == organization_id
            )
        )
        result = await self.db.execute(stmt)
        checkout_session = result.scalar_one_or_none()
        if not checkout_session:
            logger.error(f"Checkout session {checkout_session_id} not found for org {organization_id}")
            return None

        # Load product
        stmt = select(DigitalProduct).where(
            and_(
                DigitalProduct.id == product_id,
                DigitalProduct.organization_id == organization_id
            )
        )
        result = await self.db.execute(stmt)
        product = result.scalar_one_or_none()
        if not product:
            logger.error(f"Product {product_id} not found for org {organization_id}")
            return None

        # Create Order
        order = FunnelOrder(
            organization_id=organization_id,
            checkout_session_id=checkout_session_id,
            stripe_session_id=stripe_session_id,
            stripe_payment_intent_id=session_data.get("payment_intent"),
            status="paid",
            subtotal_amount=checkout_session.amount,
            total_amount=checkout_session.amount,
            currency=checkout_session.currency,
            customer_email=session_data.get("customer_details", {}).get("email") or checkout_session.customer_email,
            paid_at=datetime.now(),
        )
        self.db.add(order)
        await self.db.flush() # Get order ID

        # Create Order Item
        order_item = FunnelOrderItem(
            organization_id=organization_id,
            order_id=order.id,
            product_id=product_id,
            quantity=1,
            unit_amount=checkout_session.amount,
            total_amount=checkout_session.amount,
            currency=checkout_session.currency,
        )
        self.db.add(order_item)

        # Update Checkout Session status
        checkout_session.status = "completed"
        checkout_session.completed_at = datetime.now()

        await self.db.commit()
        await self.db.refresh(order)

        # ── GRANT DELIVERY ACCESS ──
        # Grant access immediately after successful payment/order creation
        delivery_accesses = await self.delivery_service.grant_delivery_access_for_order(
            organization_id=organization_id,
            order_id=order.id
        )

        # ── EMAIL CUSTOMER SECURE LINKS ──
        try:
            from app.services.funnel_delivery_email_service import FunnelDeliveryEmailService
            email_svc = FunnelDeliveryEmailService(self.db)
            await email_svc.send_delivery_links(
                organization_id=organization_id,
                order_id=order.id,
                customer_email=order.customer_email,
                delivery_accesses=delivery_accesses
            )
        except Exception as e:
            logger.error(f"Error triggering delivery email for order {order.id}: {e}")

        logger.info(f"Order {order.id} created, delivery granted, and email queued from Stripe session {stripe_session_id}")
        return order

    async def get_order(self, organization_id: UUID, order_id: UUID) -> Optional[FunnelOrder]:
        stmt = select(FunnelOrder).where(
            and_(
                FunnelOrder.id == order_id,
                FunnelOrder.organization_id == organization_id
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_orders(self, organization_id: UUID, limit: int = 100, offset: int = 0) -> List[FunnelOrder]:
        stmt = (
            select(FunnelOrder)
            .where(FunnelOrder.organization_id == organization_id)
            .limit(limit)
            .offset(offset)
            .order_by(FunnelOrder.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
