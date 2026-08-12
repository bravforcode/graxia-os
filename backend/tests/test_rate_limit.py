from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_login_rate_limit_returns_safe_error_envelope(public_async_client):
    bad_creds = {"email": "limit-phase16@example.com", "password": "wrongpass"}

    limited = None
    for _ in range(12):
        response = await public_async_client.post("/api/v1/auth/login", json=bad_creds)
        if response.status_code == 429:
            limited = response
            break

    assert limited is not None, "expected 429 after exhausting login rate limit"
    payload = limited.json()
    assert payload["error"]["code"] == "RATE_LIMITED"
    assert payload["error"]["message"] == "Too many requests"
    assert payload["error"]["request_id"].startswith("req_")
    assert payload["error"]["correlation_id"]
    assert "Retry-After" in limited.headers or "retry-after" in limited.headers
    assert "detail" not in payload
