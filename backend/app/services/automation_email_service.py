"""
Automated email sequence engine — sends triggered emails with delays.
Handles: welcome, abandoned_cart, post_purchase, review_request, cross_sell, win_back.
All processing is idempotent and runs as background tasks.
"""
import hashlib
import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.funnel import (
    FunnelOrder,
    FunnelCheckoutSession,
    DigitalProduct,
)
from app.models.contact import Contact
from app.config import settings
from app.services.email_service import email_service, email_accepted
from app.services.unsubscribe_tokens import (
    InvalidUnsubscribeProof,
    UnsubscribeProofUnavailable,
    create_unsubscribe_url,
)

logger = logging.getLogger("graxia.automation_email")

STORE_URL = f"{settings.FRONTEND_URL.rstrip('/')}/store"
DELIVERY_URL = f"{settings.FRONTEND_URL.rstrip('/')}/delivery"


def normalize_email_address(email: str | None) -> str | None:
    if not isinstance(email, str):
        return None
    normalized = email.strip().casefold()
    return normalized or None


def _normalized_email_digest(email: str | None) -> str:
    normalized = normalize_email_address(email) or ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _win_back_event_email_digest(metadata_json: dict | None) -> str | None:
    if not isinstance(metadata_json, dict):
        return None
    digest = metadata_json.get("email_digest")
    if isinstance(digest, str) and len(digest) == 64 and all(
        char in "0123456789abcdefABCDEF" for char in digest
    ):
        return digest.lower()
    legacy_email = metadata_json.get("email")
    if not isinstance(legacy_email, str):
        return None
    return _normalized_email_digest(legacy_email)


def win_back_candidates_statement(cutoff: datetime, limit: int | None = None):
    """Select one latest paid order per normalized tenant recipient."""
    from sqlalchemy import func

    ranked = select(
        FunnelOrder.id.label("order_id"),
        FunnelOrder.customer_email.label("customer_email"),
        FunnelOrder.organization_id.label("organization_id"),
        FunnelOrder.paid_at.label("last_paid_at"),
        func.row_number().over(
            partition_by=(
                FunnelOrder.organization_id,
                func.lower(func.trim(FunnelOrder.customer_email)),
            ),
            order_by=(FunnelOrder.paid_at.desc(), FunnelOrder.id.desc()),
        ).label("recipient_order"),
    ).where(
        FunnelOrder.customer_email.isnot(None),
        func.trim(FunnelOrder.customer_email) != "",
        FunnelOrder.status == "paid",
        FunnelOrder.paid_at.isnot(None),
    ).subquery()
    statement = select(
        ranked.c.order_id,
        ranked.c.customer_email,
        ranked.c.organization_id,
        ranked.c.last_paid_at,
    ).where(ranked.c.recipient_order == 1, ranked.c.last_paid_at < cutoff)
    if limit is not None:
        statement = statement.order_by(ranked.c.last_paid_at, ranked.c.order_id).limit(limit)
    return statement


class AutomationEmailService:
    """Processes and sends automated email sequences."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _send(
        self,
        *,
        organization_id: UUID | None = None,
        marketing_contact_id: UUID | None = None,
        **kwargs,
    ) -> dict:
        if str(kwargs.get("template_name", "")).startswith("funnel_automation_"):
            template_data = kwargs.get("template_data")
            recipient = kwargs.get("to")
            if (
                organization_id is None
                or not isinstance(template_data, dict)
                or not await self._marketing_allowed(
                    organization_id, recipient, marketing_contact_id
                )
            ):
                logger.info("[AUTOMATION] Marketing email suppressed: identity or consent check failed")
                return {"id": None, "status": "suppressed"}
            try:
                unsubscribe_url = create_unsubscribe_url(organization_id, recipient)
            except (InvalidUnsubscribeProof, UnsubscribeProofUnavailable) as exc:
                logger.warning(
                    "[AUTOMATION] Marketing email suppressed: unsubscribe proof unavailable (%s)",
                    type(exc).__name__,
                )
                return {"id": None, "status": "suppressed"}
            kwargs["template_data"] = {
                **template_data,
                "unsubscribe_url": unsubscribe_url,
            }
        result = await email_service.send_email(**kwargs)
        if email_accepted(result):
            logger.info("[AUTOMATION] Provider accepted email")
            return result
        logger.info("[AUTOMATION] Email not confirmed accepted")
        return result if isinstance(result, dict) and result.get("status") != "sent" else {
            "id": None, "status": "unverified",
        }

    async def _marketing_allowed(
        self, organization_id: UUID, email: str | None, contact_id: UUID | None = None
    ) -> bool:
        normalized_recipient = normalize_email_address(email)
        if not normalized_recipient:
            return False
        filters = [
            Contact.organization_id == organization_id,
            Contact.marketing_consent.is_(True),
            Contact.marketing_unsubscribed.is_(False),
            Contact.is_deleted.is_(False),
        ]
        if contact_id:
            filters.append(Contact.id == contact_id)
        rows = await self.db.execute(select(Contact.email).where(*filters))
        matches = [
            stored_email
            for stored_email in rows.scalars().all()
            if normalize_email_address(stored_email) == normalized_recipient
        ]
        return len(matches) == 1

    # ── Welcome Sequence ────────────────────────────────────────────────

    async def trigger_welcome(
        self, organization_id: UUID, customer_email: str, customer_name: str
    ):
        """Send welcome email immediately on signup."""
        return await self._send(
            organization_id=organization_id,
            to=customer_email,
            template_name="funnel_automation_welcome",
            template_data={
                "to_name": customer_name,
                "store_url": STORE_URL,
            },
            idempotency_key=(
                f"welcome:{organization_id}:{_normalized_email_digest(customer_email)}"
            ),
        )

    # ── Abandoned Cart ──────────────────────────────────────────────────

    async def trigger_abandoned_cart(
        self,
        organization_id: UUID,
        checkout_session_id: UUID,
        delay_hours: int = 1,
    ):
        """Send abandoned cart email after delay."""
        # Check if order was already completed (idempotency)
        stmt = select(FunnelCheckoutSession).where(
            FunnelCheckoutSession.id == checkout_session_id,
            FunnelCheckoutSession.organization_id == organization_id,
        )
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()

        if not session or session.status == "completed" or session.abandoned_email_sent_at:
            return {"id": None, "status": "suppressed"}

        email = session.customer_email
        if not email:
            return {"id": None, "status": "suppressed"}
        product_name = "your product"
        if session.product_id:
            stmt = select(DigitalProduct.name).where(
                DigitalProduct.id == session.product_id,
                DigitalProduct.organization_id == organization_id,
            )
            result = await self.db.execute(stmt)
            name = result.scalar_one_or_none()
            if name:
                product_name = name

        return await self._send(
            organization_id=organization_id,
            marketing_contact_id=session.contact_id,
            to=email,
            template_name="funnel_automation_abandoned_cart",
            template_data={
                "to_name": email.split("@")[0].capitalize(),
                "product_name": product_name,
                "product_benefits": "- Digital product files\n- Setup guidance where included\n- Support resources where available",
                "price": str(session.amount),
                "checkout_url": STORE_URL,
            },
            idempotency_key=f"abandoned_cart:{checkout_session_id}",
        )

    # ── Post-Purchase ───────────────────────────────────────────────────

    async def trigger_post_purchase(
        self, organization_id: UUID, order_id: UUID
    ):
        """Send post-purchase thank you + delivery email."""
        stmt = select(FunnelOrder).where(FunnelOrder.id == order_id, FunnelOrder.organization_id == organization_id)
        result = await self.db.execute(stmt)
        order = result.scalar_one_or_none()

        if not order or not order.customer_email:
            return {"id": None, "status": "suppressed"}

        product_name = "your product"
        if order.items:
            item = order.items[0] if order.items else None
            if item:
                stmt = select(DigitalProduct.name).where(
                    DigitalProduct.id == item.product_id,
                    DigitalProduct.organization_id == organization_id,
                )
                result = await self.db.execute(stmt)
                name = result.scalar_one_or_none()
                if name:
                    product_name = name

        return await self._send(
            organization_id=organization_id,
            marketing_contact_id=order.contact_id,
            to=order.customer_email,
            template_name="funnel_automation_post_purchase",
            template_data={
                "to_name": order.customer_email.split("@")[0].capitalize(),
                "product_name": product_name,
                "delivery_url": DELIVERY_URL,
                "review_url": STORE_URL,
            },
            idempotency_key=f"post_purchase:{order_id}",
        )

    # ── Review Request ──────────────────────────────────────────────────

    async def trigger_review_request(
        self, organization_id: UUID, order_id: UUID
    ):
        """Send review request email (called 3-5 days after purchase)."""
        stmt = select(FunnelOrder).where(FunnelOrder.id == order_id, FunnelOrder.organization_id == organization_id)
        result = await self.db.execute(stmt)
        order = result.scalar_one_or_none()

        if not order or not order.customer_email:
            return {"id": None, "status": "suppressed"}

        product_name = "your product"
        if order.items:
            item = order.items[0] if order.items else None
            if item:
                stmt = select(DigitalProduct.name).where(
                    DigitalProduct.id == item.product_id,
                    DigitalProduct.organization_id == organization_id,
                )
                result = await self.db.execute(stmt)
                name = result.scalar_one_or_none()
                if name:
                    product_name = name

        return await self._send(
            organization_id=organization_id,
            marketing_contact_id=order.contact_id,
            to=order.customer_email,
            template_name="funnel_automation_review_request",
            template_data={
                "to_name": order.customer_email.split("@")[0].capitalize(),
                "product_name": product_name,
                "review_url": STORE_URL,
            },
            idempotency_key=f"review_request:{order_id}",
        )

    # ── Cross-Sell ──────────────────────────────────────────────────────

    async def trigger_cross_sell(
        self, organization_id: UUID, order_id: UUID
    ):
        """Send cross-sell recommendations (called 7 days after purchase)."""
        stmt = select(FunnelOrder).where(FunnelOrder.id == order_id, FunnelOrder.organization_id == organization_id)
        result = await self.db.execute(stmt)
        order = result.scalar_one_or_none()

        if not order or not order.customer_email:
            return {"id": None, "status": "suppressed"}

        return await self._send(
            organization_id=organization_id,
            marketing_contact_id=order.contact_id,
            to=order.customer_email,
            template_name="funnel_automation_cross_sell",
            template_data={
                "to_name": order.customer_email.split("@")[0].capitalize(),
                "product_name": "your recent purchase",
                "recommendations": "- Browse related digital products\n- Review the latest Graxia catalog\n- Choose the next workflow that fits your needs",
                "store_url": STORE_URL,
            },
            idempotency_key=f"cross_sell:{order_id}",
        )

    # ── Win-Back ────────────────────────────────────────────────────────

    async def trigger_win_back(
        self,
        organization_id: UUID,
        customer_email: str,
        customer_name: str,
        idempotency_key: str,
    ):
        """Send win-back email with discount code."""
        email_digest = _normalized_email_digest(customer_email)
        if (not isinstance(idempotency_key, str)
                or not idempotency_key.startswith(
                    f"win_back:{organization_id}:{email_digest}:"
                )):
            raise ValueError("win_back_claim_key_required")
        return await self._send(
            organization_id=organization_id,
            to=customer_email,
            template_name="funnel_automation_win_back",
            template_data={
                "to_name": customer_name,
                "new_products": "- New digital products\n- Workflow templates\n- Practical AI resources",
                "store_url": STORE_URL,
            },
            idempotency_key=idempotency_key,
        )
