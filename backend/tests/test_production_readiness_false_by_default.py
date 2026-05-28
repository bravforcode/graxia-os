"""Test production readiness is false by default — cannot be enabled without explicit action."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_production_readiness_endpoint_false(async_client):
    """Production readiness endpoint returns false."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    assert payload["production_ready"] is False


@pytest.mark.asyncio
async def test_production_readiness_in_main_readiness_false(async_client):
    """Main readiness endpoint has production_ready false."""
    response = await async_client.get("/api/v1/health/readiness")
    assert response.status_code == 200
    payload = response.json()

    assert payload["production_ready"] is False


@pytest.mark.asyncio
async def test_local_agent_endpoint_production_readiness_false(async_client):
    """Local agent endpoint has PRODUCTION_READY false."""
    response = await async_client.get("/api/v1/health/readiness/local-agent")
    assert response.status_code == 200
    payload = response.json()

    assert payload["PRODUCTION_READY"] is False


@pytest.mark.asyncio
async def test_go_no_go_required_true_by_default(async_client):
    """go_no_go is required by default."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    assert payload["go_no_go_required"] is True


@pytest.mark.asyncio
async def test_production_readiness_cannot_be_enabled_without_gate(async_client):
    """Production readiness cannot be true while go/no-go gate is required."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    # If go/no-go is required, production_ready must be false
    if payload.get("go_no_go_required"):
        assert payload["production_ready"] is False


@pytest.mark.asyncio
async def test_production_readiness_has_all_gate_blockers(async_client):
    """Production readiness gate has meaningful blockers."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    blockers = payload.get("blockers", [])
    # Must have at least the dry-run gate blocker
    assert len(blockers) >= 1
    assert any("dry-run" in b.lower() or "closed" in b.lower() or "go" in b.lower() for b in blockers)
