"""
Revenue OS webhook endpoint E2E — verifies the RECEIVING half of the
legacy-funnel bridge.

The legacy funnel forwards the raw Stripe payload + original stripe-signature
header to Revenue OS /api/checkout/stripe-webhook (shared webhook secret).
This test drives the REAL FastAPI endpoint + require_stripe_hmac dependency
with a properly-signed payload (as the bridge would send it) and asserts:

  1. Valid signature  -> 200, order created, fulfillment queued
  2. Duplicate event  -> idempotent (no second order, status=duplicate)
  3. Bad signature    -> 400 (HMAC rejected before any DB write)
  4. Missing signature-> 400
  5. Endpoint reachable at /api/checkout/stripe-webhook
"""
from __future__ import annotations

import hmac
import hashlib
import os
import time
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from graxia.services.revenue_os_api.app import create_app
from graxia.packages.revenue_os.db import get_db
from graxia.packages.revenue_os.models import Order, Product, WebhookEvent
from graxia.packages.revenue_os.enums import DeliveryStatus, OrderStatus, ProductStatus, ProductType


TEST_WEBHOOK_SECRET = "whsec_e2e_bridge_test_secret"


def _sign_payload(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    """Build a Stripe-compatible `t=<ts>,v1=<hex>` signature header."""
    ts = timestamp or int(time.time())
    signed = f"{ts}.{payload.decode()}"
    digest = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


async def _make_published_product(db) -> Product:
    product = Product(
        name="E2E Bridge Product",
        slug=f"e2e-bridge-{uuid.uuid4().hex[:8]}",
        type=ProductType.LOW_TICKET,
        price_cents=9900,
        currency="THB",
        status=ProductStatus.PUBLISHED,
        fulfillment_url="https://example.com/access",
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


def _checkout_completed_payload(product_id: str, session_id: str | None = None) -> dict:
    return {
        "id": f"evt_{uuid.uuid4().hex}",
        "object": "event",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": session_id or f"cs_e2e_{uuid.uuid4().hex}",
                "object": "checkout.session",
                "customer_email": "buyer@example.com",
                "customer_details": {
                    "email": "buyer@example.com",
                    "name": "E2E Buyer",
                },
                "amount_total": 9900,
                "currency": "thb",
                "payment_intent": f"pi_e2e_{uuid.uuid4().hex}",
                "metadata": {"product_id": str(product_id)},
            }
        },
    }


@pytest.fixture
def e2e_app(db_session):
    """Real FastAPI app with DB dependency pointed at the test DB."""
    app = create_app()

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    return app


@pytest.fixture
async def e2e_client(e2e_app):
    transport = ASGITransport(app=e2e_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_valid_signature_creates_order_and_queues_fulfillment(
    e2e_client: AsyncClient, db_session
):
    """The exact thing the legacy bridge sends: raw body + signature."""
    os.environ["STRIPE_WEBHOOK_SECRET"] = TEST_WEBHOOK_SECRET
    product = await _make_published_product(db_session)
    event = _checkout_completed_payload(str(product.id))
    raw_body = __import__("json").dumps(event).encode()
    sig = _sign_payload(raw_body, TEST_WEBHOOK_SECRET)

    resp = await e2e_client.post(
        "/api/checkout/stripe-webhook",
        content=raw_body,
        headers={
            "stripe-signature": sig,
            "content-type": "application/json",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"

    order = (
        await db_session.execute(
            select(Order).where(Order.platform_order_id == event["data"]["object"]["id"])
        )
    ).scalar_one_or_none()
    assert order is not None
    assert order.status == OrderStatus.PAID
    assert order.amount_cents == 9900
    assert order.product_id == product.id

    # Webhook receipt recorded + fulfillment queued
    wh = (
        await db_session.execute(
            select(WebhookEvent).where(WebhookEvent.platform_event_id == event["id"])
        )
    ).scalar_one_or_none()
    assert wh is not None
    assert wh.processed is True

    from graxia.packages.revenue_os.models import DeliveryEvent
    delivery = (
        await db_session.execute(
            select(DeliveryEvent).where(DeliveryEvent.order_id == order.id)
        )
    ).scalar_one_or_none()
    assert delivery is not None
    assert delivery.status == DeliveryStatus.QUEUED


@pytest.mark.asyncio
async def test_duplicate_event_is_idempotent(e2e_client: AsyncClient, db_session):
    """Re-delivery (Stripe retries) must not create a second order."""
    os.environ["STRIPE_WEBHOOK_SECRET"] = TEST_WEBHOOK_SECRET
    product = await _make_published_product(db_session)
    event = _checkout_completed_payload(str(product.id))
    raw_body = __import__("json").dumps(event).encode()
    sig = _sign_payload(raw_body, TEST_WEBHOOK_SECRET)
    headers = {"stripe-signature": sig, "content-type": "application/json"}

    first = await e2e_client.post("/api/checkout/stripe-webhook", content=raw_body, headers=headers)
    second = await e2e_client.post("/api/checkout/stripe-webhook", content=raw_body, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"

    orders = (
        await db_session.execute(
            select(Order).where(Order.platform_order_id == event["data"]["object"]["id"])
        )
    ).scalars().all()
    assert len(orders) == 1


@pytest.mark.asyncio
async def test_bad_signature_rejected_400(e2e_client: AsyncClient, db_session):
    """Wrong shared secret -> HMAC failure before any DB write."""
    os.environ["STRIPE_WEBHOOK_SECRET"] = TEST_WEBHOOK_SECRET
    product = await _make_published_product(db_session)
    event = _checkout_completed_payload(str(product.id))
    raw_body = __import__("json").dumps(event).encode()
    sig = _sign_payload(raw_body, "wrong_secret")  # bridge would use the SAME secret

    resp = await e2e_client.post(
        "/api/checkout/stripe-webhook",
        content=raw_body,
        headers={"stripe-signature": sig, "content-type": "application/json"},
    )

    assert resp.status_code == 400
    assert "Invalid" in resp.json()["detail"]

    orders = (await db_session.execute(select(Order))).scalars().all()
    assert len(orders) == 0


@pytest.mark.asyncio
async def test_missing_signature_rejected_400(e2e_client: AsyncClient, db_session):
    """No signature header -> 400 before HMAC."""
    os.environ["STRIPE_WEBHOOK_SECRET"] = TEST_WEBHOOK_SECRET
    event = _checkout_completed_payload(str(uuid.uuid4()))
    raw_body = __import__("json").dumps(event).encode()

    resp = await e2e_client.post(
        "/api/checkout/stripe-webhook",
        content=raw_body,
        headers={"content-type": "application/json"},
    )

    assert resp.status_code == 400
    assert "signature" in resp.json()["detail"].lower()
