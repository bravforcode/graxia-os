"""
Revenue OS Bridge Tests

Verifies the legacy funnel webhook forwards raw Stripe events to Revenue OS
(best-effort, idempotent there). Covers:
  1. Forward disabled when REVENUE_OS_WEBHOOK_URL is empty (default)
  2. Forward posts raw payload + original stripe-signature when configured
  3. Forward survives Revenue OS errors (never raises, never fails the webhook)
  4. Webhook forwards on checkout.session.completed
  5. Webhook does NOT forward on other event types
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.api.funnel_webhooks import _forward_to_revenue_os


@pytest.mark.asyncio
async def test_forward_disabled_when_url_empty():
    """Default config (empty URL) must not POST anywhere."""
    with patch("app.api.funnel_webhooks.settings") as mock_settings:
        mock_settings.REVENUE_OS_WEBHOOK_URL = ""
        with patch("httpx.AsyncClient") as mock_client:
            await _forward_to_revenue_os(b"{}", "t=1,v1=abc")
            mock_client.assert_not_called()


@pytest.mark.asyncio
async def test_forward_posts_payload_and_signature():
    """When configured, forward preserves raw payload + Stripe signature."""
    raw = b'{"id": "evt_123", "type": "checkout.session.completed"}'
    sig = "t=123,v1=deadbeef"

    mock_post = AsyncMock(return_value=SimpleNamespace(status_code=200, text="ok"))
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post = mock_post

    with patch("app.api.funnel_webhooks.settings") as mock_settings:
        mock_settings.REVENUE_OS_WEBHOOK_URL = "http://localhost:8001/api/checkout/stripe-webhook"
        with patch("httpx.AsyncClient", return_value=mock_client):
            await _forward_to_revenue_os(raw, sig)

    mock_post.assert_awaited_once()
    kwargs = mock_post.call_args.kwargs
    assert kwargs["content"] == raw
    assert kwargs["headers"]["stripe-signature"] == sig
    assert kwargs["headers"]["content-type"] == "application/json"


@pytest.mark.asyncio
async def test_forward_survives_revenue_os_error():
    """Revenue OS being down must never raise out of the webhook."""
    mock_post = AsyncMock(side_effect=Exception("connection refused"))
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post = mock_post

    with patch("app.api.funnel_webhooks.settings") as mock_settings:
        mock_settings.REVENUE_OS_WEBHOOK_URL = "http://localhost:8001/api/checkout/stripe-webhook"
        with patch("httpx.AsyncClient", return_value=mock_client):
            # Must not raise
            await _forward_to_revenue_os(b"{}", "t=1,v1=abc")


@pytest.mark.asyncio
async def test_webhook_forwards_on_checkout_completed(public_async_client: AsyncClient):
    """checkout.session.completed triggers a Revenue OS forward."""
    event_payload = {
        "id": f"evt_{__import__('uuid').uuid4().hex}",
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_123", "payment_status": "paid"}},
    }
    raw_body = json.dumps(event_payload).encode()

    fake_order = SimpleNamespace(id=__import__('uuid').uuid4())
    with patch("app.api.funnel_webhooks._forward_to_revenue_os") as mock_forward:
        mock_forward.return_value = None
        with patch(
            "app.services.funnel_order_service.FunnelOrderService.create_order_from_checkout_completed",
            new=AsyncMock(return_value=fake_order),
        ):
            with patch("stripe.Webhook.construct_event", return_value=event_payload):
                resp = await public_async_client.post(
                    "/api/v1/funnel/webhooks/stripe",
                    content=raw_body,
                    headers={"stripe-signature": "t=1,v1=abc", "content-type": "application/json"},
                )

    assert resp.status_code == 200
    mock_forward.assert_awaited_once()


@pytest.mark.asyncio
async def test_webhook_does_not_forward_other_events(public_async_client: AsyncClient):
    """Non-checkout.completed events must not trigger a forward."""
    event_payload = {
        "id": f"evt_{__import__('uuid').uuid4().hex}",
        "type": "checkout.session.expired",
        "data": {"object": {"id": "cs_456"}},
    }
    raw_body = json.dumps(event_payload).encode()

    with patch("app.api.funnel_webhooks._forward_to_revenue_os") as mock_forward:
        with patch("stripe.Webhook.construct_event", return_value=event_payload):
            resp = await public_async_client.post(
                "/api/v1/funnel/webhooks/stripe",
                content=raw_body,
                headers={"stripe-signature": "t=1,v1=abc", "content-type": "application/json"},
            )

    assert resp.status_code == 200
    mock_forward.assert_not_awaited()
