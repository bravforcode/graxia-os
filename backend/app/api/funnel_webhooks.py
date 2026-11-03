import logging
from datetime import datetime, timezone
from uuid import UUID

import stripe
from fastapi import APIRouter, HTTPException, Request, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.monitoring import metrics_collector
from app.database import AsyncSessionLocal, get_db
from app.services.funnel_order_service import FunnelOrderService
from app.services.automation_email_service import AutomationEmailService
from app.services.email_service import email_accepted

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
        metrics_collector.record_webhook_failure("configuration", "secret_missing")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Webhook secret not configured"
        )

    try:
        event = stripe.Webhook.construct_event(
            payload, sig, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        metrics_collector.record_webhook_failure("signature", "invalid_payload")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        metrics_collector.record_webhook_failure("signature", "invalid_signature")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")

    event_type = event.get("type")
    data_object = event.get("data", {}).get("object", {})

    logger.info(f"Funnel Webhook received: {event_type}")

    order_id = None
    delivery_email_result = None
    email_result = None
    if event_type == "checkout.session.completed":
        try:
            order = await service.create_order_from_checkout_completed(data_object)
        except Exception:
            metrics_collector.record_webhook_failure("processing", "order_creation")
            logger.error("funnel_webhook_order_processing_failed")
            raise HTTPException(status_code=500, detail="Webhook processing failed")
        if order:
            order_id = str(order.id)
            from app.services.funnel_delivery_email_service import DeliveryEmailOutcome
            outcome = getattr(order, "delivery_email_result", None)
            delivery_email_result = outcome if type(outcome) is DeliveryEmailOutcome else DeliveryEmailOutcome("unknown")
        # Forward to Revenue OS ops layer (best-effort, idempotent there).
        await _forward_to_revenue_os(payload, sig)

    elif event_type == "checkout.session.expired":
        # Fire abandoned cart email immediately when Stripe confirms the session expired
        email_result = await _handle_checkout_expired(data_object)

    return {
        "received": True,
        "event_type": event_type,
        "order_id": order_id,
        "delivery_email_status": delivery_email_result.status if delivery_email_result is not None else None,
        "delivery_email_provider_reference": delivery_email_result.provider_reference if delivery_email_result is not None else None,
        "email_status": email_result.get("status") if email_result else None,
    }


async def _handle_checkout_expired(data_object: dict) -> dict:
    """Handle checkout.session.expired — send abandoned cart email."""
    if not isinstance(data_object, dict):
        logger.warning("[WEBHOOK] checkout.session.expired has no session payload")
        return {"id": None, "status": "suppressed"}
    metadata = data_object.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    checkout_session_id = metadata.get("funnel_checkout_session_id")
    org_id_str = metadata.get("organization_id")
    product_id_str = metadata.get("product_id")
    stripe_session_id = data_object.get("id")
    stripe_expires_at = data_object.get("expires_at")

    if (
        not checkout_session_id
        or not org_id_str
        or not product_id_str
        or not isinstance(stripe_session_id, str)
        or not stripe_session_id
        or isinstance(stripe_expires_at, bool)
        or not isinstance(stripe_expires_at, int)
        or stripe_expires_at <= 0
    ):
        logger.warning(
            "[WEBHOOK] checkout.session.expired missing or invalid session identity/expiry"
        )
        return {"id": None, "status": "suppressed"}

    try:
        from sqlalchemy import select, update
        from app.models.funnel import FunnelCheckoutSession as FCS
        checkout_session_uuid = UUID(checkout_session_id)
        organization_uuid = UUID(org_id_str)
        product_uuid = UUID(product_id_str)

        async with AsyncSessionLocal() as session:
            checkout_stmt = (
                select(FCS)
                .where(
                    FCS.id == checkout_session_uuid,
                    FCS.organization_id == organization_uuid,
                    FCS.product_id == product_uuid,
                    FCS.stripe_session_id == stripe_session_id,
                )
                .with_for_update()
            )
            checkout = await session.scalar(checkout_stmt)
            if checkout is None:
                logger.warning(
                    "[WEBHOOK] checkout.session.expired has no matching local session"
                )
                await session.rollback()
                return {"id": None, "status": "suppressed"}

            stored_expiry = checkout.expires_at
            if stored_expiry is None:
                logger.warning(
                    "[WEBHOOK] checkout.session.expired local session has no expiry"
                )
                await session.rollback()
                return {"id": None, "status": "suppressed"}
            if stored_expiry.tzinfo is None:
                stored_expiry = stored_expiry.replace(tzinfo=timezone.utc)
            else:
                stored_expiry = stored_expiry.astimezone(timezone.utc)
            if int(stored_expiry.timestamp()) != stripe_expires_at:
                logger.warning(
                    "[WEBHOOK] checkout.session.expired expiry does not match local session"
                )
                await session.rollback()
                return {"id": None, "status": "suppressed"}

            if checkout.status in {"created", "pending"}:
                checkout.status = "expired"
                await session.commit()
            elif checkout.status == "expired":
                await session.rollback()
            else:
                logger.info(
                    "[WEBHOOK] checkout.session.expired ignored for terminal local status %s",
                    checkout.status,
                )
                await session.rollback()
                return {"id": None, "status": "suppressed"}

        async with AsyncSessionLocal() as email_session:
            svc = AutomationEmailService(email_session)
            result = await svc.trigger_abandoned_cart(
                organization_id=organization_uuid,
                checkout_session_id=checkout_session_uuid,
            )
            if not email_accepted(result):
                await email_session.rollback()
                return result if isinstance(result, dict) and result.get("status") != "sent" else {
                    "id": None, "status": "unverified",
                }
            # Mark dedup flag so future retries / beat task skip this session
            await email_session.execute(
                update(FCS)
                .where(
                    FCS.id == checkout_session_uuid,
                    FCS.organization_id == organization_uuid,
                    FCS.abandoned_email_sent_at.is_(None),
                )
                .values(abandoned_email_sent_at=datetime.now(timezone.utc))
            )
            await email_session.commit()
        logger.info("[WEBHOOK] Provider acceptance recorded")
        return result
    except Exception as exc:
        logger.warning(
            "[WEBHOOK] Expired checkout handling failed: %s", type(exc).__name__
        )
        return {"id": None, "status": "failed"}
