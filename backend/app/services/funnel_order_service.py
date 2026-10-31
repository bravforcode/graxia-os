import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.funnel import DigitalProduct, FunnelCheckoutSession, FunnelOrder, FunnelOrderItem
from app.services.funnel_delivery_service import FunnelDeliveryService
from app.services.automation_email_service import AutomationEmailService
from app.services.funnel_analytics_service import FunnelAnalyticsService
from app.services.funnel_delivery_email_service import DeliveryEmailOutcome
from app.config import settings

logger = logging.getLogger(__name__)

class FunnelOrderService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.delivery_service = FunnelDeliveryService(db)
        self.delivery_email_result: DeliveryEmailOutcome | None = None

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

        if (
            not all([org_id_str, product_id_str, checkout_id_str])
            or not isinstance(stripe_session_id, str)
            or not stripe_session_id.strip()
        ):
            logger.error(f"Webhook metadata missing required fields: {metadata}")
            return None

        organization_id = UUID(org_id_str)
        product_id = UUID(product_id_str)
        checkout_session_id = UUID(checkout_id_str)

        # Lock the persisted checkout before checking idempotency. This serializes
        # duplicate webhook deliveries without relying on a new database index.
        checkout_stmt = (
            select(FunnelCheckoutSession)
            .where(
                FunnelCheckoutSession.id == checkout_session_id,
                FunnelCheckoutSession.organization_id == organization_id,
            )
            .with_for_update()
        )
        result = await self.db.execute(checkout_stmt)
        checkout_session = result.scalar_one_or_none()
        if checkout_session is None:
            await self.db.rollback()
            logger.error("Checkout session %s not found for org %s", checkout_session_id, organization_id)
            return None

        if checkout_session.stripe_session_id != stripe_session_id:
            await self.db.rollback()
            logger.warning(
                "Stripe checkout session does not match persisted checkout %s",
                checkout_session_id,
            )
            return None

        if checkout_session.product_id != product_id:
            await self.db.rollback()
            logger.warning("Stripe product metadata does not match checkout %s", checkout_session_id)
            return None

        # Recheck both identities while holding the checkout row lock. Any
        # pre-existing conflicting record fails closed instead of returning an
        # order belonging to another checkout.
        stmt = select(FunnelOrder).where(
            FunnelOrder.organization_id == organization_id,
            or_(
                FunnelOrder.checkout_session_id == checkout_session_id,
                FunnelOrder.stripe_session_id == stripe_session_id,
            ),
        )
        result = await self.db.execute(stmt)
        existing_orders = list(result.scalars().all())
        if existing_orders:
            if (
                len(existing_orders) == 1
                and existing_orders[0].checkout_session_id == checkout_session_id
                and existing_orders[0].stripe_session_id == stripe_session_id
            ):
                existing_order = existing_orders[0]
                await self.db.commit()
                await self.db.refresh(existing_order)
                self.delivery_email_result = DeliveryEmailOutcome("unknown")
                existing_order.delivery_email_result = self.delivery_email_result
                logger.info(
                    "Order for stripe session %s already exists (ID: %s)",
                    stripe_session_id,
                    existing_order.id,
                )
                return existing_order

            await self.db.rollback()
            logger.error("Conflicting order identity for checkout %s", checkout_session_id)
            return None

        # Load product only after validating the locked checkout and replay key.
        stmt = select(DigitalProduct).where(
            and_(
                DigitalProduct.id == product_id,
                DigitalProduct.organization_id == organization_id,
            )
        )
        result = await self.db.execute(stmt)
        product = result.scalar_one_or_none()
        if not product:
            await self.db.rollback()
            logger.error("Product %s not found for org %s", product_id, organization_id)
            return None

        attribution = dict(checkout_session.metadata_json or {})
        try:
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
            await self.db.flush()  # Get order ID

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

            # Update checkout status while the row lock is still held.
            checkout_session.status = "completed"
            checkout_session.completed_at = datetime.now()

            # Stage access rows in the same transaction. The caller owns the
            # commit even when no active delivery asset exists.
            delivery_accesses = await self.delivery_service.grant_delivery_access_for_order(
                organization_id=organization_id,
                order_id=order.id,
                commit=False,
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

        await self.db.refresh(order)

        try:
            await FunnelAnalyticsService(self.db).log_event(
                organization_id=organization_id,
                event_type="purchase",
                product_id=product_id,
                order_id=order.id,
                session_id=attribution.get("session_id"),
                source=attribution.get("source"),
                medium=attribution.get("medium"),
                campaign=attribution.get("campaign"),
                referrer=attribution.get("referrer"),
                metadata_json={
                    key: attribution[key]
                    for key in ("content_id", "plan", "channel", "locale")
                    if key in attribution
                },
                idempotency_key=f"purchase:{order.id}",
            )
        except Exception as exc:
            # Analytics is post-commit; its failure must not prevent delivery
            # email or make the webhook replay skip fulfillment side effects.
            await self.db.rollback()
            logger.warning(
                "Purchase analytics unavailable after checkout commit: %s",
                type(exc).__name__,
            )
            await self.db.refresh(order)

        # The checkout lock has been released before analytics, provider calls,
        # or other follow-up side effects run.
        # ── EMAIL CUSTOMER SECURE LINKS ──
        try:
            from app.services.funnel_delivery_email_service import FunnelDeliveryEmailService
            email_svc = FunnelDeliveryEmailService(self.db)
            outcome = await email_svc.send_delivery_links(
                organization_id=organization_id,
                order_id=order.id,
                customer_email=order.customer_email,
                delivery_accesses=delivery_accesses
            )
            self.delivery_email_result = outcome if type(outcome) is DeliveryEmailOutcome else DeliveryEmailOutcome("unknown")
        except Exception as e:
            self.delivery_email_result = DeliveryEmailOutcome("unknown")
            logger.error("Delivery email outcome unknown: %s", type(e).__name__)
        order.delivery_email_result = self.delivery_email_result
        logger.info("Delivery email outcome: %s", self.delivery_email_result.status)

        # ── AUTOMATION TRIGGERS ──
        # Fire-and-forget: welcome (post-purchase), review request (3 days), cross-sell (7 days)
        try:
            automation_svc = AutomationEmailService(self.db)
            await automation_svc.trigger_post_purchase(
                organization_id=organization_id,
                order_id=order.id,
            )
        except Exception as e:
            logger.error(f"[AUTOMATION] Post-purchase trigger failed for order {order.id}: {e}")

        try:
            # Serverless: no Celery broker → skip (cron bridge scans cover
            # review/cross-sell). Attempting apply_async without a broker costs
            # 4-7s of connection-retry per call and blows the 10s function limit.
            broker = getattr(settings, "CELERY_BROKER_URL", "") or getattr(settings, "REDIS_URL", "")
            if broker:
                from app.tasks.funnel_automation_tasks import send_review_request, send_cross_sell
                send_review_request.apply_async(
                    args=[str(organization_id), str(order.id)],
                    countdown=3 * 24 * 3600,  # 3 days
                )
                send_cross_sell.apply_async(
                    args=[str(organization_id), str(order.id)],
                    countdown=7 * 24 * 3600,  # 7 days
                )
            else:
                logger.info(
                    f"[AUTOMATION] Review/cross-sell scheduling skipped (no broker) "
                    f"for order {order.id} — cron bridge handles it"
                )
        except Exception as e:
            logger.error(f"[AUTOMATION] Failed to schedule review/cross-sell for order {order.id}: {e}")

        logger.info(f"Order {order.id} created, delivery granted, automation triggered from Stripe session {stripe_session_id}")
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
