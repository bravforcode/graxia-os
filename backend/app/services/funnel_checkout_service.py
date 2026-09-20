import logging
from typing import Any, Mapping, Optional
from uuid import UUID
from urllib.parse import urlsplit

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.funnel import DigitalProduct, FunnelCheckoutSession
from app.core.stripe_client import create_stripe_checkout_session
from app.schemas.funnel import FunnelCheckoutCreate
from app.config import settings
from app.core.monitoring import metrics_collector
from app.services.public_funnel_service import require_public_funnel_organization

logger = logging.getLogger(__name__)

_CHECKOUT_METADATA_KEYS = {
    "source", "medium", "campaign", "referrer", "session_id",
    "content_id", "plan", "cta", "channel", "locale", "landing_path",
    "referral_code", "first_touch", "last_touch",
}
_TOUCH_KEYS = {"source", "medium", "campaign", "referrer", "path"}


def _safe_checkout_metadata(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in (raw or {}).items():
        if key not in _CHECKOUT_METADATA_KEYS or value is None:
            continue
        if key in {"first_touch", "last_touch"} and isinstance(value, Mapping):
            touch: dict[str, str] = {}
            for touch_key in _TOUCH_KEYS:
                touch_value = value.get(touch_key)
                if touch_value is None:
                    continue
                if touch_key == "referrer":
                    parsed = urlsplit(str(touch_value).strip())
                    touch_value = (
                        f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                        if parsed.netloc else parsed.path
                    )
                touch[touch_key] = str(touch_value)[:200]
            if touch:
                result[key] = touch
            continue
        result[key] = str(value)[:200]
    return result


def _stripe_attribution_metadata(metadata: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in metadata.items():
        if isinstance(value, Mapping):
            for nested_key, nested_value in value.items():
                result[f"{key}_{nested_key}"] = str(nested_value)[:200]
        else:
            result[key] = str(value)[:200]
    return result

class FunnelCheckoutService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_checkout_session(
        self,
        organization_id: UUID,
        product_id: UUID,
        payload: FunnelCheckoutCreate,
        contact_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        public: bool = False,
    ) -> Optional[dict]:
        """
        Create a local checkout session and a Stripe checkout session.
        """
        if public:
            organization_id = require_public_funnel_organization(organization_id)
        # Load product and verify tenancy/status
        stmt = select(DigitalProduct).where(
            and_(
                DigitalProduct.id == product_id,
                DigitalProduct.organization_id == organization_id,
                DigitalProduct.status == "published",
                # Older production rows may predate the non-null default and
                # contain NULL; only an explicit True means deleted.
                DigitalProduct.is_deleted.is_not(True),
            )
        )
        result = await self.db.execute(stmt)
        product = result.scalar_one_or_none()

        if not product:
            logger.warning(f"Checkout failed: Product {product_id} not found or not published for org {organization_id}")
            metrics_collector.record_checkout_create_failure("product_unavailable")
            return None

        # Create local session record
        checkout_session = FunnelCheckoutSession(
            organization_id=organization_id,
            product_id=product_id,
            contact_id=contact_id,
            user_id=user_id,
            status="created",
            amount=product.price_amount,
            currency=product.currency,
            customer_email=payload.customer_email,
            metadata_json=_safe_checkout_metadata(payload.metadata),
        )
        self.db.add(checkout_session)
        await self.db.flush() # Get ID

        # Prefer the catalog Price so receipts and webhook line items resolve to
        # the same product. Keep inline pricing for legacy rows not yet migrated.
        if product.stripe_price_id:
            line_items = [{"price": product.stripe_price_id, "quantity": 1}]
        else:
            line_items = [
                {
                    "price_data": {
                        "currency": product.currency.lower(),
                        "product_data": {
                            "name": product.name,
                            "description": product.short_description,
                        },
                        "unit_amount": int(product.price_amount * 100),
                    },
                    "quantity": 1,
                }
            ]

        metadata = {
            "organization_id": str(organization_id),
            "product_id": str(product_id),
            "funnel_checkout_session_id": str(checkout_session.id),
        }
        metadata.update(_stripe_attribution_metadata(checkout_session.metadata_json or {}))

        try:
            # We don't have customer_id yet for new buyers, using email if provided
            stripe_session = await create_stripe_checkout_session(
                customer_id=None,
                success_url=payload.success_url,
                cancel_url=payload.cancel_url,
                line_items=line_items,
                metadata=metadata,
                customer_email=payload.customer_email,
            )

            checkout_session.stripe_session_id = stripe_session.id
            checkout_session.status = "pending"
            await self.db.commit()

            # Schedule abandoned cart check (1 hour delay).
            # On serverless (no Celery broker), skip this — the cron bridge
            # (/internal/funnel/process-due → scan_abandoned_carts) covers it,
            # and attempting apply_async without a broker costs 5-7s of
            # connection-retry time (blows the 10s Vercel Hobby limit).
            try:
                broker = getattr(settings, "CELERY_BROKER_URL", "") or getattr(settings, "REDIS_URL", "")
                if broker:
                    from app.tasks.funnel_automation_tasks import check_and_send_abandoned_cart

                    check_and_send_abandoned_cart.apply_async(
                        args=[str(organization_id), str(checkout_session.id)],
                        countdown=3600,  # 1 hour
                    )
                else:
                    logger.info(
                        "Abandoned-cart scheduling skipped (no Celery broker) — cron bridge will handle it"
                    )
            except Exception as e:
                logger.warning(f"Failed to schedule abandoned cart check: {e}")

            return {
                "id": checkout_session.id,
                "organization_id": checkout_session.organization_id,
                "product_id": checkout_session.product_id,
                "stripe_session_id": stripe_session.id,
                "checkout_url": stripe_session.url,
                "status": checkout_session.status,
                "amount": checkout_session.amount,
                "currency": checkout_session.currency,
                "customer_email": checkout_session.customer_email,
                "created_at": checkout_session.created_at,
            }

        except Exception as e:
            logger.error(f"Stripe session creation failed: {e}")
            metrics_collector.record_checkout_create_failure("stripe_session_creation")
            checkout_session.status = "failed"
            await self.db.commit()
            return None

    async def get_checkout_session(
        self, organization_id: UUID, checkout_session_id: UUID
    ) -> Optional[FunnelCheckoutSession]:
        stmt = select(FunnelCheckoutSession).where(
            and_(
                FunnelCheckoutSession.id == checkout_session_id,
                FunnelCheckoutSession.organization_id == organization_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
