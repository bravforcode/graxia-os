"""Test production dry-run readiness gate — always closed until explicit go/no-go."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_production_dry_run_gate_endpoint_exists(async_client):
    """Production readiness endpoint returns dry-run status."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    assert "production_ready" in payload
    assert "go_no_go_required" in payload
    assert payload["production_ready"] is False
    assert payload["go_no_go_required"] is True
    assert "blockers" in payload
    assert isinstance(payload["blockers"], list)
    assert len(payload["blockers"]) >= 1


@pytest.mark.asyncio
async def test_production_dry_run_gate_checks_include_docs(async_client):
    """Production readiness checks include production runbooks."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    checks = payload.get("checks", {})
    assert "production_runbooks_present" in checks
    assert "go_no_go_required" in checks
    assert "production_ready" in checks


@pytest.mark.asyncio
async def test_production_dry_run_gate_all_provider_checks(async_client):
    """Production readiness gate checks all live provider flags."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    checks = payload.get("checks", {})
    assert "live_stripe_blocked" in checks
    assert "real_email_send_blocked" in checks
    assert "real_google_mutation_blocked" in checks
    assert "real_llm_calls_blocked" in checks
    assert "production_db_blocked" in checks


@pytest.mark.asyncio
async def test_production_dry_run_gate_has_runtime(async_client):
    """Production readiness includes runtime state."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    runtime = payload.get("runtime", {})
    assert "is_ready" in runtime
    assert "mode" in runtime


@pytest.mark.asyncio
async def test_production_dry_run_gate_go_no_go_blocker_present(async_client):
    """Blockers include go/no-go gate message."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    blockers = payload.get("blockers", [])
    blocker_text = " ".join(blockers).lower()
    assert "go/no-go" in blocker_text or "go_no_go" in blocker_text


@pytest.mark.asyncio
async def test_main_readiness_includes_production_dry_run(async_client):
    """Main readiness endpoint includes production dry-run gate."""
    response = await async_client.get("/api/v1/health/readiness")
    assert response.status_code == 200
    payload = response.json()

    assert "production" in payload
    assert "production_ready" in payload
    assert payload["production_ready"] is False
    prod = payload.get("production", {})
    assert prod.get("go_no_go_required") is True
