import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.funnel import DigitalProduct, FunnelCheckoutSession
from app.core.stripe_client import create_stripe_checkout_session
from app.schemas.funnel import FunnelCheckoutCreate

logger = logging.getLogger(__name__)

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
    ) -> Optional[dict]:
        """
        Create a local checkout session and a Stripe checkout session.
        """
        # Load product and verify tenancy/status
        stmt = select(DigitalProduct).where(
            and_(
                DigitalProduct.id == product_id,
                DigitalProduct.organization_id == organization_id,
                DigitalProduct.status == "published",
                DigitalProduct.is_deleted == False,
            )
        )
        result = await self.db.execute(stmt)
        product = result.scalar_one_or_none()

        if not product:
            logger.warning(f"Checkout failed: Product {product_id} not found or not published for org {organization_id}")
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
        )
        self.db.add(checkout_session)
        await self.db.flush() # Get ID

        # Prepare Stripe session
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

            # Schedule abandoned cart check (1 hour delay)
            try:
                from app.tasks.funnel_automation_tasks import check_and_send_abandoned_cart
                check_and_send_abandoned_cart.apply_async(
                    args=[str(organization_id), str(checkout_session.id)],
                    countdown=3600,  # 1 hour
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
