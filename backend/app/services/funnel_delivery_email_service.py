import logging
from typing import List, Tuple, Optional, Literal
from dataclasses import dataclass
import re
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.email_service import email_service, email_accepted
from app.models.funnel import DeliveryAccess, DigitalProduct, FunnelOrder
from app.services.delivery_email_attempts import DeliveryEmailAttemptStore

logger = logging.getLogger("graxia.funnel_email")

@dataclass(frozen=True)
class DeliveryEmailOutcome:
    status: Literal["sent", "failed", "suppressed", "unknown"]
    provider_reference: str | None = None

    def __post_init__(self):
        if self.status not in {"sent", "failed", "suppressed", "unknown"}:
            raise ValueError("invalid_delivery_email_status")
        if self.status == "sent":
            if not isinstance(self.provider_reference, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", self.provider_reference):
                raise ValueError("delivery_email_reference_required")
        elif self.provider_reference is not None:
            raise ValueError("unaccepted_delivery_email_reference")

    def __bool__(self):
        return self.status == "sent"


class FunnelDeliveryEmailService:
    # Accepted emails only; history is not a durable delivery receipt repository.
    sent_emails: List[dict] = []

    def __init__(self, db: Optional[AsyncSession] = None, *, attempt_store=None):
        self.db = db
        self.email_service = email_service
        self.attempt_store = attempt_store if attempt_store is not None else DeliveryEmailAttemptStore()

    async def send_delivery_links(
        self,
        organization_id: UUID,
        order_id: UUID,
        customer_email: str,
        delivery_accesses: List[Tuple[DeliveryAccess, str]],
        customer_name: Optional[str] = None
    ) -> DeliveryEmailOutcome:
        """
        Send delivery access secure download links to the customer via email.
        """
        if not delivery_accesses or self.db is None or not customer_email:
            return DeliveryEmailOutcome("suppressed")

        result = await self.db.execute(select(FunnelOrder).where(
            FunnelOrder.id == order_id, FunnelOrder.organization_id == organization_id,
            FunnelOrder.status == "paid",
        ))
        order = result.scalar_one_or_none()
        if (order is None or order.id != order_id or order.organization_id != organization_id
                or order.status != "paid" or order.customer_email != customer_email):
            return DeliveryEmailOutcome("suppressed")

        if not customer_name:
            customer_name = customer_email.split("@")[0]

        delivery_items = []
        for access, raw_token in delivery_accesses:
            persisted_access = await self.db.get(DeliveryAccess, access.id)
            if (persisted_access is None or persisted_access.organization_id != organization_id
                    or persisted_access.order_id != order_id or persisted_access.status != "active"
                    or persisted_access.product_id != access.product_id
                    or not isinstance(raw_token, str) or not raw_token):
                return DeliveryEmailOutcome("suppressed")
            access = persisted_access
            product_name = "Digital Product"
            if self.db:
                try:
                    stmt = select(DigitalProduct.name).where(
                        DigitalProduct.id == access.product_id,
                        DigitalProduct.organization_id == organization_id,
                    )
                    res = await self.db.execute(stmt)
                    name = res.scalar_one_or_none()
                    if name:
                        product_name = name
                except Exception as e:
                    logger.error("Delivery product lookup failed: %s", type(e).__name__)

            expires_str = access.expires_at.strftime("%Y-%m-%d") if access.expires_at else "Never"
            download_url = f"{settings.FRONTEND_URL}/funnel/delivery/{raw_token}"
            
            delivery_items.append({
                "product_name": product_name,
                "download_url": download_url,
                "expires_at": expires_str
            })

        # Render and send email
        idempotency_key = f"funnel_delivery:{order_id}"
        
        # Track in test mock history
        email_payload = {
            "to": customer_email,
            "template_name": "funnel_delivery",
            "template_data": {
                "to_name": customer_name,
                "delivery_items": delivery_items
            },
            "idempotency_key": idempotency_key
        }
        try:
            claim = await self.attempt_store.claim(organization_id, order_id, customer_email,
                                                  tuple(access.id for access, _ in delivery_accesses))
        except Exception as exc:
            logger.error("Delivery intent not confirmed: %s", type(exc).__name__)
            return DeliveryEmailOutcome("unknown")
        if not claim.acquired:
            return DeliveryEmailOutcome(claim.outcome, claim.provider_reference)
        # Send using the global email_service
        try:
            res = await self.email_service.send_email(
                to=customer_email,
                template_name="funnel_delivery",
                template_data={
                    "to_name": customer_name,
                    "delivery_items": delivery_items
                },
                idempotency_key=idempotency_key
            )
            if email_accepted(res):
                outcome = DeliveryEmailOutcome("sent", res["id"])
            else:
                state = res.get("status") if isinstance(res, dict) else None
                # The adapter has no verified definitive-rejection contract.
                suppressed = (state in {"suppressed", "logged", "skipped"}
                              and isinstance(res, dict) and res.get("error") is None)
                outcome = DeliveryEmailOutcome("suppressed" if suppressed else "unknown")
        except Exception as e:
            logger.error("Delivery email acceptance unknown: %s", type(e).__name__)
            outcome = DeliveryEmailOutcome("unknown")
        try:
            await self.attempt_store.finish(claim, outcome.status, outcome.provider_reference)
        except Exception as exc:
            logger.error("Delivery receipt persistence unknown: %s", type(exc).__name__)
            return DeliveryEmailOutcome("unknown")
        if outcome.status == "sent":
            email_payload["provider_reference"] = outcome.provider_reference
            FunnelDeliveryEmailService.sent_emails.append(email_payload)
        return outcome
