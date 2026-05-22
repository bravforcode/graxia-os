import logging
import stripe
from fastapi import APIRouter, HTTPException, Request, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.services.funnel_order_service import FunnelOrderService

router = APIRouter()
logger = logging.getLogger("funnel.webhooks")

async def get_order_service(db: AsyncSession = Depends(get_db)) -> FunnelOrderService:
    return FunnelOrderService(db)

@router.post("/stripe")
async def stripe_funnel_webhook(
    request: Request,
    service: FunnelOrderService = Depends(get_order_service)
):
    """
    Handle Stripe webhooks for the digital product funnel.
    Focuses on checkout.session.completed.
    """
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Webhook secret not configured"
        )

    try:
        event = stripe.Webhook.construct_event(
            payload, sig, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")

    event_type = event.get("type")
    data_object = event.get("data", {}).get("object", {})

    logger.info(f"Funnel Webhook received: {event_type}")

    order_id = None
    if event_type == "checkout.session.completed":
        order = await service.create_order_from_checkout_completed(data_object)
        if order:
            order_id = str(order.id)

    return {
        "received": True,
        "event_type": event_type,
        "order_id": order_id
    }
