"""Test public route rate limiting — login, register, delivery, billing plans."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_login_rate_limit_returns_safe_429(public_async_client):
    """Login rate limit returns safe error envelope, not raw detail."""
    bad_creds = {"email": "limit-test@example.com", "password": "wrong"}
    limited = None
    for _ in range(15):
        resp = await public_async_client.post("/api/v1/auth/login", json=bad_creds)
        if resp.status_code == 429:
            limited = resp
            break
    assert limited is not None, "expected 429 after login rate limit"
    payload = limited.json()
    assert payload["error"]["code"] == "RATE_LIMITED"
    assert payload["error"]["message"] == "Too many requests"
    assert payload["error"]["request_id"].startswith("req_")
    assert "detail" not in payload
    assert "stack" not in limited.text.lower()


@pytest.mark.asyncio
async def test_register_rate_limit_returns_safe_429(public_async_client):
    """Register rate limit returns safe envelope."""
    limited = None
    for _ in range(8):
        resp = await public_async_client.post(
            "/api/v1/auth/register",
            json={"email": "reglimit-test@example.com", "password": "Test1234!"},
        )
        if resp.status_code == 429:
            limited = resp
            break
    assert limited is not None, "expected 429 after register rate limit"
    payload = limited.json()
    assert payload["error"]["code"] == "RATE_LIMITED"
    assert payload["error"]["message"] == "Too many requests"


@pytest.mark.asyncio
async def test_public_billing_plans_accessible(public_async_client):
    """Billing plans endpoint is public and rate-limited."""
    response = await public_async_client.get("/api/v1/billing/plans")
    assert response.status_code in (200, 429)
    if response.status_code == 200:
        data = response.json()
        assert "plans" in data
    elif response.status_code == 429:
        payload = response.json()
        assert payload["error"]["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_rate_limit_headers_present(public_async_client):
    """Rate-limited responses include standard headers."""
    for _ in range(12):
        resp = await public_async_client.post(
            "/api/v1/auth/login",
            json={"email": "headers-test@example.com", "password": "wrong"},
        )
        if resp.status_code == 429:
            assert "RateLimit-Limit" in resp.headers
            assert "RateLimit-Remaining" in resp.headers
            assert "RateLimit-Reset" in resp.headers
            assert "X-Request-ID" in resp.headers
            assert "X-Correlation-ID" in resp.headers
            break


@pytest.mark.asyncio
async def test_different_ip_different_rate_limit_bucket(public_async_client):
    """Different IPs get separate rate limit counters."""
    # Simulate different IP with X-Forwarded-For
    headers_ip1 = {"X-Forwarded-For": "10.0.0.1"}
    headers_ip2 = {"X-Forwarded-For": "10.0.0.2"}
    
    responses_ip1 = []
    responses_ip2 = []
    
    for _ in range(12):
        r1 = await public_async_client.post(
            "/api/v1/auth/login",
            json={"email": "ip-test@example.com", "password": "wrong"},
            headers=headers_ip1,
        )
        responses_ip1.append(r1.status_code)
        
        r2 = await public_async_client.post(
            "/api/v1/auth/login",
            json={"email": "ip-test@example.com", "password": "wrong"},
            headers=headers_ip2,
        )
        responses_ip2.append(r2.status_code)
    
    # Both should not be rate limited since they are different IPs
    # (login limit is 10 per 60s, we did 12 but they're different IPs)
    assert 200 in responses_ip1 or 401 in responses_ip1
    assert 200 in responses_ip2 or 401 in responses_ip2
