"""
Automated email sequence engine — sends triggered emails with delays.
Handles: welcome, abandoned_cart, post_purchase, review_request, cross_sell, win_back.
All processing is idempotent and runs as background tasks.
"""
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.funnel import (
    FunnelOrder,
    FunnelCheckoutSession,
    DigitalProduct,
)
from app.services.email_service import email_service

logger = logging.getLogger("graxia.automation_email")

STORE_URL = "https://ai-factory-omega.vercel.app/store"


class AutomationEmailService:
    """Processes and sends automated email sequences."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Welcome Sequence ────────────────────────────────────────────────

    async def trigger_welcome(
        self, organization_id: UUID, customer_email: str, customer_name: str
    ):
        """Send welcome email immediately on signup."""
        await email_service.send_email(
            to=customer_email,
            template_name="funnel_automation_welcome",
            template_data={
                "to_name": customer_name,
                "store_url": STORE_URL,
            },
            idempotency_key=f"welcome:{customer_email}",
        )
        logger.info(f"[AUTOMATION] Welcome email sent to {customer_email}")

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
            FunnelCheckoutSession.id == checkout_session_id
        )
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()

        if not session or session.status == "completed" or session.abandoned_email_sent_at:
            return

        email = session.customer_email
        if not email:
            return

        product_name = "your product"
        if session.product_id:
            stmt = select(DigitalProduct.name).where(
                DigitalProduct.id == session.product_id
            )
            result = await self.db.execute(stmt)
            name = result.scalar_one_or_none()
            if name:
                product_name = name

        await email_service.send_email(
            to=email,
            template_name="funnel_automation_abandoned_cart",
            template_data={
                "to_name": email.split("@")[0].capitalize(),
                "product_name": product_name,
                "product_benefits": "- Battle-tested templates & tools\n- Lifetime updates included\n- 30-day money-back guarantee",
                "price": str(session.amount),
                "checkout_url": STORE_URL,
            },
            idempotency_key=f"abandoned_cart:{checkout_session_id}",
        )
        logger.info(f"[AUTOMATION] Abandoned cart email sent for session {checkout_session_id}")

    # ── Post-Purchase ───────────────────────────────────────────────────

    async def trigger_post_purchase(
        self, organization_id: UUID, order_id: UUID
    ):
        """Send post-purchase thank you + delivery email."""
        stmt = select(FunnelOrder).where(FunnelOrder.id == order_id)
        result = await self.db.execute(stmt)
        order = result.scalar_one_or_none()

        if not order or not order.customer_email:
            return

        product_name = "your product"
        if order.items:
            item = order.items[0] if order.items else None
            if item:
                stmt = select(DigitalProduct.name).where(
                    DigitalProduct.id == item.product_id
                )
                result = await self.db.execute(stmt)
                name = result.scalar_one_or_none()
                if name:
                    product_name = name

        await email_service.send_email(
            to=order.customer_email,
            template_name="funnel_automation_post_purchase",
            template_data={
                "to_name": order.customer_email.split("@")[0].capitalize(),
                "product_name": product_name,
                "delivery_url": "https://ai-factory-omega.vercel.app/delivery",
                "review_url": STORE_URL,
            },
            idempotency_key=f"post_purchase:{order_id}",
        )
        logger.info(f"[AUTOMATION] Post-purchase email sent for order {order_id}")

    # ── Review Request ──────────────────────────────────────────────────

    async def trigger_review_request(
        self, organization_id: UUID, order_id: UUID
    ):
        """Send review request email (called 3-5 days after purchase)."""
        stmt = select(FunnelOrder).where(FunnelOrder.id == order_id)
        result = await self.db.execute(stmt)
        order = result.scalar_one_or_none()

        if not order or not order.customer_email:
            return

        product_name = "your product"
        if order.items:
            item = order.items[0] if order.items else None
            if item:
                stmt = select(DigitalProduct.name).where(
                    DigitalProduct.id == item.product_id
                )
                result = await self.db.execute(stmt)
                name = result.scalar_one_or_none()
                if name:
                    product_name = name

        await email_service.send_email(
            to=order.customer_email,
            template_name="funnel_automation_review_request",
            template_data={
                "to_name": order.customer_email.split("@")[0].capitalize(),
                "product_name": product_name,
                "review_url": STORE_URL,
            },
            idempotency_key=f"review_request:{order_id}",
        )
        logger.info(f"[AUTOMATION] Review request email sent for order {order_id}")

    # ── Cross-Sell ──────────────────────────────────────────────────────

    async def trigger_cross_sell(
        self, organization_id: UUID, order_id: UUID
    ):
        """Send cross-sell recommendations (called 7 days after purchase)."""
        stmt = select(FunnelOrder).where(FunnelOrder.id == order_id)
        result = await self.db.execute(stmt)
        order = result.scalar_one_or_none()

        if not order or not order.customer_email:
            return

        await email_service.send_email(
            to=order.customer_email,
            template_name="funnel_automation_cross_sell",
            template_data={
                "to_name": order.customer_email.split("@")[0].capitalize(),
                "product_name": "your recent purchase",
                "recommendations": "- ChatGPT Power Prompts Bundle (590 THB)\n- Notion Life OS (990 THB)\n- SaaS Boilerplate Starter (1,990 THB)",
                "store_url": STORE_URL,
            },
            idempotency_key=f"cross_sell:{order_id}",
        )
        logger.info(f"[AUTOMATION] Cross-sell email sent for order {order_id}")

    # ── Win-Back ────────────────────────────────────────────────────────

    async def trigger_win_back(
        self, organization_id: UUID, customer_email: str, customer_name: str
    ):
        """Send win-back email with discount code."""
        await email_service.send_email(
            to=customer_email,
            template_name="funnel_automation_win_back",
            template_data={
                "to_name": customer_name,
                "new_products": "- AI Content Automation System (790 THB)\n- Freelancer Command Center (690 THB)\n- YouTube Growth Toolkit (790 THB)",
                "store_url": STORE_URL,
            },
            idempotency_key=f"win_back:{customer_email}",
        )
        logger.info(f"[AUTOMATION] Win-back email sent to {customer_email}")
