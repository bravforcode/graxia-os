"""
Rate limiting contract tests.

Verifies that:
- Login endpoint is rate-limited at 10 req/min per IP
- 429 response includes Retry-After header
- General API endpoints respect the higher API rate limit
- Rate limits reset between test runs via reset_rate_limit_state()
"""

import pytest


@pytest.mark.asyncio
async def test_login_rate_limit_enforced(public_async_client):
    """Exceeding login limit must return 429 with Retry-After header."""
    # RateLimitMiddleware.LOGIN_RULE: 10 attempts per 60 seconds
    bad_creds = {"email": "noone@example.com", "password": "wrongpass"}

    # Exhaust the login window (11 attempts — one past the limit of 10)
    responses = []
    for _ in range(11):
        r = await public_async_client.post("/api/v1/auth/login", json=bad_creds)
        responses.append(r.status_code)

    status_codes = set(responses)
    # Must get at least one 429 once limit is reached
    assert 429 in status_codes, f"Expected 429 after exceeding login rate limit. Got: {responses}"


@pytest.mark.asyncio
async def test_login_rate_limit_includes_retry_after(public_async_client):
    """429 responses must carry a Retry-After header."""
    bad_creds = {"email": "ratelimit@example.com", "password": "wrongpass"}

    last_429 = None
    for _ in range(12):
        r = await public_async_client.post("/api/v1/auth/login", json=bad_creds)
        if r.status_code == 429:
            last_429 = r
            break

    if last_429 is None:
        pytest.skip("Rate limit not triggered in 12 requests — limit may be higher in env")

    assert "Retry-After" in last_429.headers or "retry-after" in last_429.headers, (
        "429 response missing Retry-After header"
    )


@pytest.mark.asyncio
async def test_rate_limit_state_resets_between_tests(public_async_client):
    """After reset_rate_limit_state() (called by fixture), limit is fresh."""
    # If state were NOT reset, first request might already be at the limit.
    # A single valid-format POST should not return 429.
    response = await public_async_client.post(
        "/api/v1/auth/login",
        json={"email": "check@example.com", "password": "short"},
    )
    # 422 = validation error, 401 = bad creds, 200 = success — all fine
    # Only 429 would indicate stale rate-limit state
    assert response.status_code != 429, "Rate limit state was NOT reset between tests"


@pytest.mark.asyncio
async def test_authenticated_api_has_higher_rate_limit(async_client):
    """Authenticated API traffic should use the higher API_RULE limit (600/min)."""
    # Fire 15 rapid requests — should all succeed since API limit is 600/min
    for _ in range(15):
        r = await async_client.get("/api/v1/opportunities")
        assert r.status_code != 429, (
            "API rate limit triggered too early (expected 600/min threshold)"
        )
