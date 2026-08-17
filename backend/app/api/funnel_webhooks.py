import logging
from uuid import UUID

import stripe
from fastapi import APIRouter, HTTPException, Request, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal, get_db
from app.services.funnel_order_service import FunnelOrderService
from app.services.automation_email_service import AutomationEmailService

router = APIRouter()
logger = logging.getLogger("funnel.webhooks")


async def _forward_to_revenue_os(raw_payload: bytes, signature: str) -> None:
    """Best-effort forward of a raw Stripe webhook to Revenue OS.

    Revenue OS re-validates the Stripe signature using the shared webhook
    secret and records the order idempotently. Failures are logged and never
    raise — the funnel webhook must keep working if Revenue OS is down.
    """
    url = (settings.REVENUE_OS_WEBHOOK_URL or "").strip()
    if not url:
        return
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                content=raw_payload,
                headers={
                    "stripe-signature": signature,
                    "content-type": "application/json",
                },
            )
            if resp.status_code >= 400:
                logger.warning(
                    "Revenue OS forward failed: url=%s status=%s body=%s",
                    url, resp.status_code, resp.text[:300],
                )
            else:
                logger.info("Revenue OS forward ok: url=%s status=%s", url, resp.status_code)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Revenue OS forward error: %s", exc)

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
        # Forward to Revenue OS ops layer (best-effort, idempotent there).
        await _forward_to_revenue_os(payload, sig)

    elif event_type == "checkout.session.expired":
        # Fire abandoned cart email immediately when Stripe confirms the session expired
        await _handle_checkout_expired(data_object)

    return {
        "received": True,
        "event_type": event_type,
        "order_id": order_id
    }


async def _handle_checkout_expired(data_object: dict) -> None:
    """Handle checkout.session.expired — send abandoned cart email."""
    metadata = data_object.get("metadata", {})
    checkout_session_id = metadata.get("funnel_checkout_session_id")
    org_id_str = metadata.get("organization_id")

    if not checkout_session_id or not org_id_str:
        logger.info("[WEBHOOK] checkout.session.expired missing metadata, skipping abandoned cart")
        return

    try:
        from datetime import datetime, timezone
        from sqlalchemy import update
        from app.models.funnel import FunnelCheckoutSession as FCS
        async with AsyncSessionLocal() as session:
            svc = AutomationEmailService(session)
            await svc.trigger_abandoned_cart(
                organization_id=UUID(org_id_str),
                checkout_session_id=UUID(checkout_session_id),
            )
            # Mark dedup flag so future retries / beat task skip this session
            await session.execute(
                update(FCS)
                .where(FCS.id == UUID(checkout_session_id))
                .values(abandoned_email_sent_at=datetime.now(timezone.utc))
            )
            await session.commit()
        logger.info(f"[WEBHOOK] Abandoned cart email triggered for session {checkout_session_id}")
    except Exception as exc:
        logger.error(f"[WEBHOOK] Failed to send abandoned cart email: {exc}")
