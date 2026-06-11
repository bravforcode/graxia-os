import logging
from typing import List, Tuple, Optional
from uuid import UUID
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.email_service import email_service
from app.models.funnel import DeliveryAccess, DigitalProduct

logger = logging.getLogger("graxia.funnel_email")

class FunnelDeliveryEmailService:
    # Class-level mock history to verify sent emails in tests
    sent_emails: List[dict] = []

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        self.email_service = email_service

    async def send_delivery_links(
        self,
        organization_id: UUID,
        order_id: UUID,
        customer_email: str,
        delivery_accesses: List[Tuple[DeliveryAccess, str]],
        customer_name: Optional[str] = None
    ) -> bool:
        """
        Send delivery access secure download links to the customer via email.
        """
        if not delivery_accesses:
            logger.warning(f"No delivery accesses to email for order {order_id}")
            return False

        if not customer_name:
            customer_name = customer_email.split("@")[0]

        delivery_items = []
        for access, raw_token in delivery_accesses:
            product_name = "Digital Product"
            if self.db:
                try:
                    stmt = select(DigitalProduct.name).where(DigitalProduct.id == access.product_id)
                    res = await self.db.execute(stmt)
                    name = res.scalar_one_or_none()
                    if name:
                        product_name = name
                except Exception as e:
                    logger.error(f"Error fetching product name for access {access.id}: {e}")

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
        FunnelDeliveryEmailService.sent_emails.append(email_payload)

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
            status = res.get("status")
            logger.info(f"[EMAIL AUDIT] Funnel delivery email status: {status} to {customer_email} for order {order_id}")
            return status in ["sent", "logged", "skipped"]
        except Exception as e:
            logger.error(f"[EMAIL AUDIT] Failed sending funnel delivery email: {e}")
            return False
