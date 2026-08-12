"""Test live provider guards — all real API calls blocked by default."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_live_stripe_blocked_in_production_endpoint(async_client):
    """Live Stripe must be blocked in test environment."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    checks = payload.get("checks", {})
    assert checks.get("live_stripe_blocked") is True


@pytest.mark.asyncio
async def test_real_email_send_blocked_in_production_endpoint(async_client):
    """Real email sending must be blocked in test environment."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    checks = payload.get("checks", {})
    assert checks.get("real_email_send_blocked") is True


@pytest.mark.asyncio
async def test_real_google_mutation_blocked_in_production_endpoint(async_client):
    """Real Google Workspace mutation must be blocked in test environment."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    checks = payload.get("checks", {})
    assert checks.get("real_google_mutation_blocked") is True


@pytest.mark.asyncio
async def test_real_llm_calls_blocked_in_production_endpoint(async_client):
    """Real LLM calls must be blocked in test environment."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    checks = payload.get("checks", {})
    assert checks.get("real_llm_calls_blocked") is True


@pytest.mark.asyncio
async def test_production_db_blocked_in_production_endpoint(async_client):
    """Production database must be blocked in test environment."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    checks = payload.get("checks", {})
    assert checks.get("production_db_blocked") is True


@pytest.mark.asyncio
async def test_all_live_providers_blocked_simultaneously(async_client):
    """All live provider flags must be blocked simultaneously."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    checks = payload.get("checks", {})
    blocked = [
        checks.get("live_stripe_blocked"),
        checks.get("real_email_send_blocked"),
        checks.get("real_google_mutation_blocked"),
        checks.get("real_llm_calls_blocked"),
        checks.get("production_db_blocked"),
    ]
    assert all(blocked), f"Not all live providers blocked: {blocked}"
