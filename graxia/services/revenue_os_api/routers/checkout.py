"""
graxia/services/revenue_os_api/routers/checkout.py
Stripe webhook receiver — idempotent, HMAC-validated.
Fixes CRIT-03 (real DB session).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.db import get_db
from ....packages.revenue_os.models import WebhookEvent
from ....packages.revenue_os.schemas import CheckoutWebhookResponse, CreateOrderPayload
from ....packages.revenue_os.services.order_service import OrderService
from ....packages.revenue_os.services.webhook_processor import WebhookProcessor
from ..dependencies import require_stripe_hmac
from sqlalchemy import select

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/stripe-webhook",
    response_model=CheckoutWebhookResponse,
    status_code=200,
    summary="Receive Stripe webhook events",
)
async def stripe_webhook(
    request: Request,
    event: dict = Depends(require_stripe_hmac),
    db: AsyncSession = Depends(get_db),
) -> CheckoutWebhookResponse:
    """
    Idempotent Stripe webhook handler.

    Guards:
      1. HMAC validated by require_stripe_hmac dependency
      2. WebhookEvent.platform_event_id has DB-level UNIQUE constraint (idempotency)
      3. Order creation uses savepoint-based idempotency key
    """
    event_id: str = event.get("id", "")
    event_type: str = event.get("type", "")

    # ── Idempotency gate: skip already-processed events ────────────────────
    existing_event = await db.scalar(
        select(WebhookEvent).where(WebhookEvent.platform_event_id == event_id)
    )
    if existing_event and existing_event.processed:
        logger.info("Duplicate webhook skipped: event_id=%s", event_id)
        return CheckoutWebhookResponse(
            status="duplicate",
            message=f"Event {event_id} already processed",
        )

    # Record webhook receipt
    if not existing_event:
        webhook_record = WebhookEvent(
            platform="stripe",
            event_type=event_type,
            platform_event_id=event_id,
            payload=event,
        )
        db.add(webhook_record)
        await db.flush()
    else:
        webhook_record = existing_event

    order_id = None

    try:
        if event_type == "checkout.session.completed":
            # Verified path: HMAC-validated by require_stripe_hmac. Uses
            # WebhookProcessor which sets PAID + fulfills immediately (idempotent).
            # Requires metadata.product_id in the checkout session (fail-closed
            # otherwise — no silent PROCESSING orders).
            session = event["data"]["object"]
            order = await WebhookProcessor.process_stripe_checkout_completed(session, db)
            if order is not None:
                order_id = order.id
            logger.info(
                "Checkout completed: order_id=%s",
                order_id or "duplicate-skipped",
            )

        elif event_type == "charge.refunded":
            # External refund (e.g. dashboard/Stripe CLI): mark order refunded
            charge = event["data"]["object"]
            await WebhookProcessor.process_stripe_refund(charge, db)
            logger.info("charge.refunded processed")

        else:
            logger.debug("Unhandled Stripe event type: %s", event_type)

        # Mark webhook as processed
        webhook_record.processed = True
        from datetime import datetime
        webhook_record.processed_at = datetime.utcnow()

        return CheckoutWebhookResponse(
            status="success",
            order_id=order_id,
            message=f"Event {event_type} processed",
        )

    except Exception as exc:
        webhook_record.processing_error = str(exc)[:500]
        logger.error(
            "Webhook processing failed: event_id=%s error=%s",
            event_id, exc, exc_info=True,
        )
        raise
