"""Test controlled beta readiness gate — must pass all sub-gates before beta can open."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_beta_readiness_endpoint_exists(async_client):
    """Beta readiness endpoint returns 200."""
    response = await async_client.get("/api/v1/health/readiness/beta")
    assert response.status_code == 200
    payload = response.json()

    assert "beta_ready" in payload
    assert "checks" in payload
    assert "blockers" in payload


@pytest.mark.asyncio
async def test_beta_readiness_has_required_checks(async_client):
    """Beta readiness checks include all required sub-gates."""
    response = await async_client.get("/api/v1/health/readiness/beta")
    assert response.status_code == 200
    payload = response.json()

    checks = payload.get("checks", {})
    assert "staging_ready" in checks
    assert "prod_dry_run_ready" in checks
    assert "production_ready" in checks
    assert "live_providers_enabled" in checks
    assert "approval_system_ready" in checks
    assert "operator_runbook_ready" in checks
    assert "beta_cohort_configured" in checks
    assert "kill_switch_ready" in checks
    assert "monitoring_ready" in checks
    assert "rollback_ready" in checks
    assert "support_triage_ready" in checks


@pytest.mark.asyncio
async def test_beta_readiness_production_ready_false(async_client):
    """Beta gate requires production_ready to be false."""
    response = await async_client.get("/api/v1/health/readiness/beta")
    assert response.status_code == 200
    payload = response.json()

    checks = payload.get("checks", {})
    assert checks.get("production_ready") is False


@pytest.mark.asyncio
async def test_beta_readiness_live_providers_disabled(async_client):
    """Beta gate requires live providers to be disabled."""
    response = await async_client.get("/api/v1/health/readiness/beta")
    assert response.status_code == 200
    payload = response.json()

    checks = payload.get("checks", {})
    assert checks.get("live_providers_enabled") is False


@pytest.mark.asyncio
async def test_beta_readiness_kill_switch_ready(async_client):
    """Kill switch must be active for beta readiness."""
    response = await async_client.get("/api/v1/health/readiness/beta")
    assert response.status_code == 200
    payload = response.json()

    checks = payload.get("checks", {})
    assert checks.get("kill_switch_ready") is True


@pytest.mark.asyncio
async def test_beta_readiness_has_beta_settings(async_client):
    """Beta readiness includes beta_enabled and kill_switch status."""
    response = await async_client.get("/api/v1/health/readiness/beta")
    assert response.status_code == 200
    payload = response.json()

    assert "beta_enabled" in payload
    assert "kill_switch_enabled" in payload
    assert "beta_tester_count" in payload
