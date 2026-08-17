"""
graxia/services/revenue_os_api/routers/checkout.py
Stripe checkout — session creation (customer-facing) + webhook receiver.
Fixes CRIT-03 (real DB session) + P0-1 (payment initiation).
"""
from __future__ import annotations

import logging
import os

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.db import get_db
from ....packages.revenue_os.enums import ProductStatus
from ....packages.revenue_os.models import Product, WebhookEvent
from ....packages.revenue_os.schemas import (
    CheckoutSessionCreate,
    CheckoutSessionResponse,
    CheckoutWebhookResponse,
    CreateOrderPayload,
)
from ....packages.revenue_os.services.order_service import OrderService
from ....packages.revenue_os.services.webhook_processor import WebhookProcessor
from ..dependencies import require_stripe_hmac

router = APIRouter()
logger = logging.getLogger(__name__)

stripe_checkout = stripe.checkout.Session  # monkeypatch target for tests


def _get_stripe_secret_key() -> str:
    """Fail-fast in production if key is not set (matches dependencies.py pattern)."""
    key = os.getenv("STRIPE_SECRET_KEY") or os.getenv("STRIPE_API_KEY")
    if not key:
        if os.getenv("APP_ENV") == "production":
            raise RuntimeError("STRIPE_SECRET_KEY must be set in production")
        return "sk_test_placeholder"
    return key


@router.post(
    "/session",
    response_model=CheckoutSessionResponse,
    status_code=201,
    summary="Create Stripe Checkout session",
)
async def create_checkout_session(
    payload: CheckoutSessionCreate,
    db: AsyncSession = Depends(get_db),
) -> CheckoutSessionResponse:
    """
    Create a Stripe Checkout session for a published product.

    Guards:
      1. Product must exist, be PUBLISHED, and have price_cents > 0 (fail-closed)
      2. Amount/currency come from the DB product — never from the client
      3. metadata.product_id is set so the webhook can create the order idempotently
    """
    product = await db.get(Product, payload.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.status != ProductStatus.PUBLISHED:
        raise HTTPException(status_code=400, detail="Product is not available for purchase")
    if not product.price_cents or product.price_cents <= 0:
        raise HTTPException(status_code=400, detail="Product has no price")

    stripe.api_key = _get_stripe_secret_key()
    try:
        session = stripe_checkout.create(
            mode="payment",
            success_url=payload.success_url,
            cancel_url=payload.cancel_url,
            line_items=[
                {
                    "price_data": {
                        "currency": (product.currency or "THB").lower(),
                        "unit_amount": product.price_cents,
                        "product_data": {"name": product.name},
                    },
                    "quantity": 1,
                }
            ],
            metadata={"product_id": str(product.id)},
            customer_email=payload.customer_email,
        )
    except stripe.error.StripeError as exc:
        logger.error("Stripe checkout session creation failed: %s", exc)
        raise HTTPException(status_code=502, detail="Payment provider error")

    logger.info(
        "Checkout session created: product_id=%s session_id=%s",
        product.id, session.id,
    )
    return CheckoutSessionResponse(session_id=session.id, checkout_url=session.url)


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

        elif event_type == "customer.subscription.deleted":
            # P2-10: mirror Stripe subscription lifecycle locally
            from ....packages.revenue_os.services.billing_service import BillingService
            await BillingService.handle_subscription_deleted(db, event["data"]["object"])
            logger.info("customer.subscription.deleted processed")

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
