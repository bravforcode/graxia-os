"""Funnel service layer — delivery access, email, lead magnets, recommendations, analytics."""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.runtime.events import business_event_service
from app.models.funnel import (
    ConversionEvent,
    DeliveryAccess,
    DeliveryEmailEvent,
    DeliveryAsset,
    DigitalProduct,
    FunnelOrder,
    FunnelOrderItem,
    FunnelRecommendation,
    LeadCapture,
    LeadMagnet,
)

logger = logging.getLogger(__name__)

# ── Token helpers ─────────────────────────────────────────────────────────

def _generate_access_token() -> str:
    """Generate a secure random access token."""
    return secrets.token_urlsafe(48)


def _hash_token(token: str) -> str:
    """Hash a token for storage. Never store raw tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _email_domain(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.split("@", 1)[1].lower()


# ── Delivery Access Service ────────────────────────────────────────────────

class DeliveryAccessService:
    """Secure delivery access lifecycle: grant, verify, revoke, open."""

    async def grant_access(
        self,
        organization_id: UUID,
        order_id: UUID,
        product_id: UUID,
        delivery_asset_id: UUID | None = None,
        expires_at: datetime | None = None,
        db: AsyncSession | None = None,
    ) -> tuple[DeliveryAccess, str]:
        """Grant delivery access and return (access_record, raw_token).

        The raw token is returned once and must be communicated to the customer.
        Only the hash is stored.
        """
        raw_token = _generate_access_token()
        token_hash = _hash_token(raw_token)

        access = DeliveryAccess(
            id=uuid4(),
            organization_id=organization_id,
            order_id=order_id,
            product_id=product_id,
            delivery_asset_id=delivery_asset_id,
            access_token_hash=token_hash,
            status="active",
            expires_at=expires_at or (datetime.now(UTC) + timedelta(days=365)),
        )

        if db:
            db.add(access)
            await db.commit()
            await db.refresh(access)
        else:
            async with AsyncSessionLocal() as session:
                session.add(access)
                await session.commit()
                await session.refresh(access)

        return access, raw_token

    async def verify_access(
        self,
        raw_token: str,
        db: AsyncSession | None = None,
    ) -> DeliveryAccess | None:
        """Verify a raw token and return the access record if valid."""
        token_hash = _hash_token(raw_token)
        async with db or AsyncSessionLocal() as session:
            stmt = select(DeliveryAccess).where(
                DeliveryAccess.access_token_hash == token_hash,
                DeliveryAccess.status == "active",
            ).where(
                or_(
                    DeliveryAccess.expires_at.is_(None),
                    DeliveryAccess.expires_at > datetime.now(UTC),
                )
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def revoke_access(
        self,
        access_id: UUID,
        organization_id: UUID,
        db: AsyncSession | None = None,
    ) -> DeliveryAccess | None:
        """Revoke a delivery access record."""
        async with db or AsyncSessionLocal() as session:
            access = await session.get(DeliveryAccess, access_id)
            if access is None or access.organization_id != organization_id:
                return None
            access.status = "revoked"
            await session.commit()
            await session.refresh(access)
            return access

    async def record_open(
        self,
        access_id: UUID,
        db: AsyncSession | None = None,
    ) -> DeliveryAccess | None:
        """Record a delivery open event (first and last access timestamps)."""
        async with db or AsyncSessionLocal() as session:
            access = await session.get(DeliveryAccess, access_id)
            if access is None:
                return None
            now = datetime.now(UTC)
            access.open_count = (access.open_count or 0) + 1
            access.first_opened_at = access.first_opened_at or now
            access.last_opened_at = now
            access.first_accessed_at = access.first_accessed_at or now
            access.last_accessed_at = now
            access.download_count = (access.download_count or 0) + 1
            await session.commit()
            await session.refresh(access)
            await business_event_service.emit(
                organization_id=str(access.organization_id),
                event_type="delivery.opened",
                subject_type="delivery_access",
                subject_id=str(access.id),
                payload={
                    "order_id": str(access.order_id),
                    "product_id": str(access.product_id),
                    "open_count": access.open_count,
                },
                actor_type="customer",
                source="funnel-service",
                correlation_id=f"delivery-open:{access.id}:{access.open_count}",
                idempotency_key=f"delivery-open:{access.id}:{access.open_count}",
            )
            return access

    async def get_access_by_id(
        self,
        access_id: UUID,
        organization_id: UUID,
        db: AsyncSession | None = None,
    ) -> DeliveryAccess | None:
        """Get a delivery access record by ID (scoped to org)."""
        async with db or AsyncSessionLocal() as session:
            access = await session.get(DeliveryAccess, access_id)
            if access is None or access.organization_id != organization_id:
                return None
            return access

    async def get_accesses_for_order(
        self,
        order_id: UUID,
        organization_id: UUID,
        db: AsyncSession | None = None,
    ) -> list[DeliveryAccess]:
        """Get all delivery accesses for an order."""
        async with db or AsyncSessionLocal() as session:
            stmt = select(DeliveryAccess).where(
                DeliveryAccess.order_id == order_id,
                DeliveryAccess.organization_id == organization_id,
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())


delivery_access_service = DeliveryAccessService()


# ── Mock Email Provider ─────────────────────────────────────────────────────

class MockEmailProvider:
    """Mock email provider — never sends real emails.

    In development/testing, logs to console and stores event records.
    In production-like environments, still uses mock unless explicitly
    configured otherwise (which it never is for tests).
    """

    async def send_delivery_email(
        self,
        customer_email: str,
        delivery_token: str,
        product_name: str,
        organization_id: UUID,
        order_id: UUID,
        delivery_access_id: UUID,
        idempotency_key: str,
        db: AsyncSession | None = None,
    ) -> DeliveryEmailEvent:
        """Mock sending a delivery email. Returns a DeliveryEmailEvent."""
        event = DeliveryEmailEvent(
            id=uuid4(),
            organization_id=organization_id,
            order_id=order_id,
            delivery_access_id=delivery_access_id,
            customer_email=customer_email,
            status="sent",
            provider="mock",
            idempotency_key=idempotency_key,
            sent_at=datetime.now(UTC),
            metadata_json={
                "product_name": product_name,
                "delivery_url": f"/delivery/{delivery_token}",
                "simulated": True,
            },
        )

        if db:
            db.add(event)
            await db.commit()
            await db.refresh(event)
        else:
            async with AsyncSessionLocal() as session:
                session.add(event)
                await session.commit()
                await session.refresh(event)

        logger.info(
            "[MOCK EMAIL] To: %s | Product: %s | Token: %s... | Event: %s",
            customer_email, product_name, delivery_token[:12], event.id,
        )
        return event

    async def send_pending_followup(
        self,
        customer_email: str,
        product_name: str,
        delivery_url: str,
        organization_id: UUID,
        idempotency_key: str,
        db: AsyncSession | None = None,
    ) -> DeliveryEmailEvent:
        """Mock sending a follow-up email for unopened delivery."""
        event = DeliveryEmailEvent(
            id=uuid4(),
            organization_id=organization_id,
            customer_email=customer_email,
            status="sent",
            provider="mock",
            idempotency_key=idempotency_key,
            sent_at=datetime.now(UTC),
            metadata_json={
                "product_name": product_name,
                "delivery_url": delivery_url,
                "type": "followup",
                "simulated": True,
            },
        )

        if db:
            db.add(event)
            await db.commit()
            await db.refresh(event)
        else:
            async with AsyncSessionLocal() as session:
                session.add(event)
                await session.commit()
                await session.refresh(event)

        logger.info(
            "[MOCK FOLLOWUP] To: %s | Product: %s | URL: %s",
            customer_email, product_name, delivery_url,
        )
        return event


mock_email_provider = MockEmailProvider()


# ── Lead Magnet Service ─────────────────────────────────────────────────────

class LeadMagnetService:
    """Lead magnet lifecycle: create, get, capture."""

    async def create(
        self,
        organization_id: UUID,
        slug: str,
        title: str,
        description: str | None = None,
        product_id: UUID | None = None,
        asset_id: UUID | None = None,
        metadata_json: dict[str, Any] | None = None,
        db: AsyncSession | None = None,
    ) -> LeadMagnet:
        magnet = LeadMagnet(
            id=uuid4(),
            organization_id=organization_id,
            slug=slug,
            title=title,
            description=description,
            product_id=product_id,
            asset_id=asset_id,
            status="active",
            metadata_json=metadata_json,
        )
        if db:
            db.add(magnet)
            await db.commit()
            await db.refresh(magnet)
        else:
            async with AsyncSessionLocal() as session:
                session.add(magnet)
                await session.commit()
                await session.refresh(magnet)
        return magnet

    async def get_by_slug(
        self,
        slug: str,
        organization_id: UUID,
        db: AsyncSession | None = None,
    ) -> LeadMagnet | None:
        async with db or AsyncSessionLocal() as session:
            stmt = select(LeadMagnet).where(
                LeadMagnet.organization_id == organization_id,
                LeadMagnet.slug == slug,
                LeadMagnet.status == "active",
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def capture(
        self,
        lead_magnet_id: UUID,
        organization_id: UUID,
        email: str,
        source: str | None = None,
        utm_source: str | None = None,
        utm_medium: str | None = None,
        utm_campaign: str | None = None,
        metadata_json: dict[str, Any] | None = None,
        db: AsyncSession | None = None,
    ) -> LeadCapture | None:
        """Capture a lead. Returns None if duplicate (idempotent)."""
        capture = LeadCapture(
            id=uuid4(),
            organization_id=organization_id,
            lead_magnet_id=lead_magnet_id,
            email=email,
            source=source,
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign,
            metadata_json=metadata_json,
        )
        try:
            if db:
                db.add(capture)
                await db.commit()
                await db.refresh(capture)
            else:
                async with AsyncSessionLocal() as session:
                    session.add(capture)
                    await session.commit()
                    await session.refresh(capture)
            await business_event_service.emit(
                organization_id=str(organization_id),
                event_type="lead.captured",
                subject_type="lead_capture",
                subject_id=str(capture.id),
                payload={
                    "lead_magnet_id": str(lead_magnet_id),
                    "email_domain": _email_domain(email),
                    "source": source,
                    "utm_source": utm_source,
                    "utm_medium": utm_medium,
                    "utm_campaign": utm_campaign,
                },
                actor_type="customer",
                source="funnel-service",
                correlation_id=f"lead-capture:{capture.id}",
                idempotency_key=f"lead-capture:{organization_id}:{lead_magnet_id}:{email.lower()}",
            )
            return capture
        except Exception:
            logger.warning("Duplicate lead capture (org=%s, magnet=%s, email=%s)", organization_id, lead_magnet_id, email)
            return None

    async def get_captures_for_magnet(
        self,
        lead_magnet_id: UUID,
        organization_id: UUID,
        db: AsyncSession | None = None,
    ) -> list[LeadCapture]:
        async with db or AsyncSessionLocal() as session:
            stmt = select(LeadCapture).where(
                LeadCapture.lead_magnet_id == lead_magnet_id,
                LeadCapture.organization_id == organization_id,
            ).order_by(LeadCapture.created_at.desc())
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def list(
        self,
        organization_id: UUID,
        status: str | None = None,
        db: AsyncSession | None = None,
    ) -> list[LeadMagnet]:
        async with db or AsyncSessionLocal() as session:
            stmt = select(LeadMagnet).where(
                LeadMagnet.organization_id == organization_id,
            )
            if status:
                stmt = stmt.where(LeadMagnet.status == status)
            stmt = stmt.order_by(LeadMagnet.created_at.desc())
            result = await session.execute(stmt)
            return list(result.scalars().all())


lead_magnet_service = LeadMagnetService()


# ── Funnel Recommendation Service ──────────────────────────────────────────

class FunnelRecommendationService:
    """Generate and manage funnel recommendations."""

    async def create(
        self,
        organization_id: UUID,
        product_id: UUID,
        recommendation_type: str,
        recommended_action: str,
        bottleneck: str | None = None,
        expected_impact: str | None = None,
        confidence: str | None = None,
        effort: str | None = None,
        risk: str | None = None,
        reasoning: str | None = None,
        draft_content: str | None = None,
        metadata_json: dict[str, Any] | None = None,
        db: AsyncSession | None = None,
    ) -> FunnelRecommendation:
        rec = FunnelRecommendation(
            id=uuid4(),
            organization_id=organization_id,
            product_id=product_id,
            recommendation_type=recommendation_type,
            bottleneck=bottleneck,
            recommended_action=recommended_action,
            expected_impact=expected_impact,
            confidence=confidence,
            effort=effort,
            risk=risk,
            reasoning=reasoning,
            draft_content=draft_content,
            status="draft",
            metadata_json=metadata_json,
        )
        if db:
            db.add(rec)
            await db.commit()
            await db.refresh(rec)
        else:
            async with AsyncSessionLocal() as session:
                session.add(rec)
                await session.commit()
                await session.refresh(rec)
        await business_event_service.emit(
            organization_id=str(organization_id),
            event_type="recommendation.created",
            subject_type="funnel_recommendation",
            subject_id=str(rec.id),
            payload={
                "product_id": str(product_id),
                "recommendation_type": recommendation_type,
                "confidence": confidence,
                "effort": effort,
                "risk": risk,
            },
            actor_type="agent",
            source="funnel-service",
            risk_level="APPROVAL_REQUIRED",
            correlation_id=f"recommendation:{rec.id}",
            idempotency_key=f"recommendation:{rec.id}",
        )
        return rec

    async def list(
        self,
        organization_id: UUID,
        product_id: UUID | None = None,
        status: str | None = None,
        limit: int = 20,
        db: AsyncSession | None = None,
    ) -> list[FunnelRecommendation]:
        async with db or AsyncSessionLocal() as session:
            stmt = select(FunnelRecommendation).where(
                FunnelRecommendation.organization_id == organization_id,
            )
            if product_id:
                stmt = stmt.where(FunnelRecommendation.product_id == product_id)
            if status:
                stmt = stmt.where(FunnelRecommendation.status == status)
            stmt = stmt.order_by(FunnelRecommendation.created_at.desc()).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get(
        self,
        rec_id: UUID,
        organization_id: UUID,
        db: AsyncSession | None = None,
    ) -> FunnelRecommendation | None:
        async with db or AsyncSessionLocal() as session:
            rec = await session.get(FunnelRecommendation, rec_id)
            if rec is None or rec.organization_id != organization_id:
                return None
            return rec

    async def submit_for_approval(
        self,
        rec_id: UUID,
        organization_id: UUID,
        approval_request_id: UUID,
        db: AsyncSession | None = None,
    ) -> FunnelRecommendation | None:
        async with db or AsyncSessionLocal() as session:
            rec = await session.get(FunnelRecommendation, rec_id)
            if rec is None or rec.organization_id != organization_id:
                return None
            rec.status = "pending_approval"
            rec.approval_request_id = approval_request_id
            await session.commit()
            await session.refresh(rec)
            return rec


funnel_recommendation_service = FunnelRecommendationService()


# ── Analytics Service ───────────────────────────────────────────────────────

class FunnelAnalyticsService:
    """Compute funnel analytics summaries."""

    async def get_summary(
        self,
        organization_id: UUID,
        db: AsyncSession | None = None,
    ) -> dict[str, Any]:
        """Get overall funnel analytics summary for an organization."""
        async with db or AsyncSessionLocal() as session:
            # Product counts
            total_products = await session.scalar(
                select(func.count(DigitalProduct.id)).where(
                    DigitalProduct.organization_id == organization_id,
                    DigitalProduct.is_deleted == False,
                )
            ) or 0

            published_products = await session.scalar(
                select(func.count(DigitalProduct.id)).where(
                    DigitalProduct.organization_id == organization_id,
                    DigitalProduct.status == "published",
                    DigitalProduct.is_deleted == False,
                )
            ) or 0

            # Order counts and revenue
            total_orders = await session.scalar(
                select(func.count(FunnelOrder.id)).where(
                    FunnelOrder.organization_id == organization_id,
                )
            ) or 0

            paid_orders = await session.scalar(
                select(func.count(FunnelOrder.id)).where(
                    FunnelOrder.organization_id == organization_id,
                    FunnelOrder.status == "paid",
                )
            ) or 0

            total_revenue_result = await session.scalar(
                select(func.coalesce(func.sum(FunnelOrder.total_amount), 0)).where(
                    FunnelOrder.organization_id == organization_id,
                    FunnelOrder.status == "paid",
                )
            ) or Decimal("0")

            # Checkout stats
            total_checkouts_result = await session.scalar(
                select(func.count(ConversionEvent.id)).where(
                    ConversionEvent.organization_id == organization_id,
                    ConversionEvent.event_type == "checkout_start",
                )
            ) or 0

            total_purchases = await session.scalar(
                select(func.count(ConversionEvent.id)).where(
                    ConversionEvent.organization_id == organization_id,
                    ConversionEvent.event_type == "purchase",
                )
            ) or 0

            abandonment_rate = 0.0
            if total_checkouts_result > 0:
                abandonment_rate = round(
                    (total_checkouts_result - total_purchases) / total_checkouts_result * 100, 2
                )

            # Delivery stats
            total_delivery_accesses = await session.scalar(
                select(func.count(DeliveryAccess.id)).where(
                    DeliveryAccess.organization_id == organization_id,
                )
            ) or 0

            opened_deliveries = await session.scalar(
                select(func.count(DeliveryAccess.id)).where(
                    DeliveryAccess.organization_id == organization_id,
                    DeliveryAccess.first_opened_at.is_not(None),
                )
            ) or 0

            delivery_open_rate = 0.0
            if total_delivery_accesses > 0:
                delivery_open_rate = round(
                    opened_deliveries / total_delivery_accesses * 100, 2
                )

            # Lead captures
            total_lead_captures = await session.scalar(
                select(func.count(LeadCapture.id)).where(
                    LeadCapture.organization_id == organization_id,
                )
            ) or 0

            return {
                "total_products": int(total_products),
                "published_products": int(published_products),
                "total_orders": int(total_orders),
                "paid_orders": int(paid_orders),
                "total_revenue": str(total_revenue_result),
                "total_checkouts": int(total_checkouts_result),
                "checkout_abandonment_rate": abandonment_rate,
                "total_delivery_accesses": int(total_delivery_accesses),
                "delivery_open_rate": delivery_open_rate,
                "total_lead_captures": int(total_lead_captures),
            }

    async def get_product_analytics(
        self,
        product_id: UUID,
        organization_id: UUID,
        db: AsyncSession | None = None,
    ) -> dict[str, Any]:
        """Get analytics for a specific product."""
        async with db or AsyncSessionLocal() as session:
            product = await session.get(DigitalProduct, product_id)
            if product is None or product.organization_id != organization_id:
                return {}

            # Product views
            total_views = await session.scalar(
                select(func.count(ConversionEvent.id)).where(
                    ConversionEvent.product_id == product_id,
                    ConversionEvent.event_type == "page_view",
                )
            ) or 0

            # Checkouts
            total_checkouts = await session.scalar(
                select(func.count(ConversionEvent.id)).where(
                    ConversionEvent.product_id == product_id,
                    ConversionEvent.event_type == "checkout_start",
                )
            ) or 0

            # Purchases
            total_purchases = await session.scalar(
                select(func.count(ConversionEvent.id)).where(
                    ConversionEvent.product_id == product_id,
                    ConversionEvent.event_type == "purchase",
                )
            ) or 0

            # Revenue
            total_revenue = await session.scalar(
                select(func.coalesce(func.sum(FunnelOrderItem.total_amount), 0)).where(
                    FunnelOrderItem.product_id == product_id,
                )
            ) or Decimal("0")

            # Orders
            orders = await session.execute(
                select(FunnelOrder).join(FunnelOrderItem).where(
                    FunnelOrderItem.product_id == product_id,
                    FunnelOrder.organization_id == organization_id,
                )
            )
            order_count = len(list(orders.scalars().all()))

            # Delivery opens
            delivery_opens = await session.scalar(
                select(func.count(DeliveryAccess.id)).where(
                    DeliveryAccess.product_id == product_id,
                    DeliveryAccess.first_opened_at.is_not(None),
                )
            ) or 0

            conversion_rate = 0.0
            if total_views > 0:
                conversion_rate = round(total_purchases / total_views * 100, 2)

            return {
                "product_id": str(product_id),
                "total_views": int(total_views),
                "total_checkouts": int(total_checkouts),
                "total_purchases": int(total_purchases),
                "total_orders": order_count,
                "total_revenue": str(total_revenue),
                "delivery_opens": int(delivery_opens),
                "conversion_rate": conversion_rate,
            }


funnel_analytics_service = FunnelAnalyticsService()


# ── Webhook Handler ─────────────────────────────────────────────────────────

class FunnelWebhookHandler:
    """Handle Stripe webhook simulation — create order, grant access, send email."""

    async def handle_checkout_completed(
        self,
        organization_id: UUID,
        checkout_session_id: UUID,
        customer_email: str,
        db: AsyncSession | None = None,
    ) -> dict[str, Any]:
        """Handle a simulated checkout.completed webhook.

        Creates order + order items, grants delivery access, sends mock email.
        Idempotent via checkout_session_id uniqueness check.
        """
        async with db or AsyncSessionLocal() as session:
            # Check for existing order (idempotency)
            existing_order = await session.scalar(
                select(FunnelOrder).where(
                    FunnelOrder.checkout_session_id == checkout_session_id,
                )
            )
            if existing_order:
                logger.info(
                    "Order already exists for checkout session %s (order %s)",
                    checkout_session_id, existing_order.id,
                )
                return {"order_id": str(existing_order.id), "duplicate": True}

            # Get checkout session
            from app.models.funnel import FunnelCheckoutSession
            checkout = await session.get(FunnelCheckoutSession, checkout_session_id)
            if checkout is None:
                raise ValueError(f"Checkout session not found: {checkout_session_id}")

            # Create order
            order = FunnelOrder(
                id=uuid4(),
                organization_id=organization_id,
                checkout_session_id=checkout_session_id,
                stripe_session_id=checkout.stripe_session_id,
                status="paid",
                subtotal_amount=checkout.amount,
                total_amount=checkout.amount,
                currency=checkout.currency,
                customer_email=customer_email or checkout.customer_email,
                paid_at=datetime.now(UTC),
            )
            session.add(order)
            await session.flush()

            # Create order item
            item = FunnelOrderItem(
                id=uuid4(),
                organization_id=organization_id,
                order_id=order.id,
                product_id=checkout.product_id,
                quantity=1,
                unit_amount=checkout.amount,
                total_amount=checkout.amount,
                currency=checkout.currency,
            )
            session.add(item)
            await session.flush()

            # Grant delivery access
            access, raw_token = await delivery_access_service.grant_access(
                organization_id=organization_id,
                order_id=order.id,
                product_id=checkout.product_id,
                db=session,
            )

            # Get product name
            product = await session.get(DigitalProduct, checkout.product_id)
            product_name = product.name if product else "Digital Product"

            # Send mock email
            idempotency_key = f"delivery_email:{order.id}:{checkout.product_id}"
            await mock_email_provider.send_delivery_email(
                customer_email=customer_email or checkout.customer_email or "",
                delivery_token=raw_token,
                product_name=product_name,
                organization_id=organization_id,
                order_id=order.id,
                delivery_access_id=access.id,
                idempotency_key=idempotency_key,
                db=session,
            )

            # Track purchase event
            purchase_event = ConversionEvent(
                id=uuid4(),
                organization_id=organization_id,
                event_type="purchase",
                product_id=checkout.product_id,
                order_id=order.id,
                occurred_at=datetime.now(UTC),
            )
            session.add(purchase_event)

            await session.commit()

            correlation_id = f"checkout:{checkout_session_id}"
            await business_event_service.emit(
                organization_id=str(organization_id),
                event_type="payment.succeeded",
                subject_type="checkout_session",
                subject_id=str(checkout_session_id),
                payload={
                    "order_id": str(order.id),
                    "product_id": str(checkout.product_id),
                    "amount": str(checkout.amount),
                    "currency": checkout.currency,
                    "customer_email_domain": _email_domain(customer_email or checkout.customer_email),
                },
                actor_type="customer",
                source="funnel-webhook",
                correlation_id=correlation_id,
                idempotency_key=f"payment-succeeded:{checkout_session_id}",
            )
            await business_event_service.emit(
                organization_id=str(organization_id),
                event_type="order.created",
                subject_type="funnel_order",
                subject_id=str(order.id),
                payload={
                    "checkout_session_id": str(checkout_session_id),
                    "product_id": str(checkout.product_id),
                    "status": order.status,
                    "total_amount": str(order.total_amount),
                    "currency": order.currency,
                },
                actor_type="service",
                source="funnel-webhook",
                correlation_id=correlation_id,
                idempotency_key=f"order-created:{order.id}",
            )
            await business_event_service.emit(
                organization_id=str(organization_id),
                event_type="delivery.access.granted",
                subject_type="delivery_access",
                subject_id=str(access.id),
                payload={
                    "order_id": str(order.id),
                    "product_id": str(checkout.product_id),
                    "delivery_access_id": str(access.id),
                    "delivery_asset_id": str(access.delivery_asset_id) if access.delivery_asset_id else None,
                },
                actor_type="service",
                source="funnel-webhook",
                correlation_id=correlation_id,
                idempotency_key=f"delivery-access-granted:{access.id}",
            )

            return {
                "order_id": str(order.id),
                "access_id": str(access.id),
                "token_preview": raw_token[:16] + "...",
                "product_name": product_name,
                "customer_email": customer_email or checkout.customer_email,
                "duplicate": False,
            }


funnel_webhook_handler = FunnelWebhookHandler()
