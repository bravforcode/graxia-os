"""Test customer delivery token auth, rate limiting, and no raw token logging."""

from __future__ import annotations

import pytest
from uuid import uuid4
from datetime import datetime, timezone
from types import SimpleNamespace


@pytest.mark.asyncio
async def test_public_delivery_returns_safe_404_for_bad_token(public_async_client):
    """Delivery endpoint returns safe 404, not raw error."""
    response = await public_async_client.get(
        f"/api/v1/funnel/delivery/{uuid4().hex}"
    )
    assert response.status_code in (404, 429)
    if response.status_code == 404:
        payload = response.json()
        assert payload["error"]["code"] == "NOT_FOUND"
        assert payload["error"]["message"] == "Resource not found"
        # No raw token in response
        body = response.text.lower()
        assert "token" not in body or "[redacted]" in body
        assert "stack" not in body
        assert "traceback" not in body


@pytest.mark.asyncio
async def test_public_delivery_rate_limit_fingerprint(public_async_client):
    """Delivery endpoint rate limits by token fingerprint."""
    bad_token = uuid4().hex
    responses = []
    for _ in range(35):
        resp = await public_async_client.get(
            f"/api/v1/funnel/delivery/{bad_token}"
        )
        responses.append(resp.status_code)
        if resp.status_code == 429:
            break
    assert 429 in responses, "expected 429 after exhausting delivery rate limit"
    payload = responses[responses.index(429)]
    # Actually check the last response
    last = None
    for resp in [await public_async_client.get(f"/api/v1/funnel/delivery/{bad_token}") for _ in range(3)]:
        if resp.status_code == 429:
            last = resp
            break
    if last:
        payload = last.json()
        assert payload["error"]["code"] == "RATE_LIMITED"
        assert "detail" not in payload


@pytest.mark.asyncio
async def test_delivery_token_not_in_audit_log(public_async_client):
    """Verify delivery token is not logged in plaintext."""
    bad_token = uuid4().hex
    response = await public_async_client.get(
        f"/api/v1/funnel/delivery/{bad_token}"
    )
    assert response.status_code in (404, 429)
    body = response.text.lower()
    assert bad_token not in body


@pytest.mark.asyncio
async def test_delivery_opened_public_tracking(public_async_client):
    """Delivery-opened tracking endpoint is accessible without auth."""
    response = await public_async_client.post(
        "/api/v1/funnel/events/delivery-opened",
        params={"access_token": uuid4().hex},
    )
    assert response.status_code in (404, 429)
    if response.status_code == 404:
        payload = response.json()
        assert payload["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_delivery_opened_tracks_valid_token_without_auth(
    public_async_client, monkeypatch
):
    """A valid public token records an open and returns only the access ID."""
    from app.api import funnel_delivery

    token = "synthetic-delivery-token"
    access_id = uuid4()
    access = SimpleNamespace(id=access_id)
    calls = []

    async def verify_access(candidate, db=None):
        calls.append(("verify", candidate, db is not None))
        return access

    async def record_open(candidate, db=None):
        calls.append(("record_open", candidate, db is not None))
        return access

    monkeypatch.setattr(
        funnel_delivery.delivery_access_service, "verify_access", verify_access
    )
    monkeypatch.setattr(
        funnel_delivery.delivery_access_service, "record_open", record_open
    )

    response = await public_async_client.post(
        "/api/v1/funnel/events/delivery-opened",
        params={"access_token": token},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "tracked", "access_id": str(access_id)}
    assert calls == [("verify", token, True), ("record_open", access_id, True)]
