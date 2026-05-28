"""Test staging readiness integration — auth, org, rate-limit checks."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_staging_readiness_endpoint_returns_checks(async_client):
    """Staging readiness endpoint returns all security check fields."""
    response = await async_client.get("/api/v1/health/readiness/staging")
    assert response.status_code == 200
    payload = response.json()

    # Must have checks key with Phase 16 security indicators
    checks = payload.get("checks", {})
    assert "auth_context_middleware" in checks
    assert "org_boundary_ok" in checks
    assert "rate_limiting_active" in checks
    assert "safe_errors_ok" in checks
    assert "security_audit_ok" in checks
    assert "route_protection_matrix_ok" in checks
    assert "mcp_auth_ok" in checks
    assert "workflow_auth_ok" in checks
    assert "public_route_limits_ok" in checks
    assert "customer_token_boundary_ok" in checks
    assert "production_live_providers_disabled" in checks

    # Must have staging_ready and environment fields
    assert "staging_ready" in payload
    assert "environment" in payload
    assert "blockers" in payload
    assert isinstance(payload["blockers"], list)


@pytest.mark.asyncio
async def test_staging_readiness_has_runtime_info(async_client):
    """Staging readiness includes runtime state."""
    response = await async_client.get("/api/v1/health/readiness/staging")
    assert response.status_code == 200
    payload = response.json()

    runtime = payload.get("runtime", {})
    assert "is_ready" in runtime
    assert "mode" in runtime
    assert "issues" in runtime
    assert isinstance(runtime["issues"], list)


@pytest.mark.asyncio
async def test_staging_readiness_production_live_providers_disabled(async_client):
    """Production live providers should be disabled (stripe, email, google)."""
    response = await async_client.get("/api/v1/health/readiness/staging")
    assert response.status_code == 200
    payload = response.json()

    checks = payload["checks"]
    # Stripe live mode should be blocked since we use placeholder/test keys
    assert checks["production_live_providers_disabled"] is True


@pytest.mark.asyncio
async def test_staging_readiness_not_ready_in_test_env(async_client):
    """Staging ready should be False in test environment (not staging)."""
    response = await async_client.get("/api/v1/health/readiness/staging")
    assert response.status_code == 200
    payload = response.json()

    assert payload["staging_ready"] is False
    assert payload["environment"] != "staging"


@pytest.mark.asyncio
async def test_staging_readiness_permissions_ok(async_client):
    """Staging readiness permission check should pass."""
    response = await async_client.get("/api/v1/health/readiness/staging")
    assert response.status_code == 200
    payload = response.json()

    assert payload["checks"]["permissions_ok"] is True
    assert payload["checks"]["org_boundary_ok"] is True
    assert payload["checks"]["auth_context_middleware"] is True


@pytest.mark.asyncio
async def test_health_readiness_endpoint_includes_staging_and_production(async_client):
    """Main readiness endpoint includes staging and production gates."""
    response = await async_client.get("/api/v1/health/readiness")
    assert response.status_code == 200
    payload = response.json()

    assert "staging" in payload
    assert "production" in payload
    assert "staging_ready" in payload
    assert "production_ready" in payload
    assert "blockers" in payload
    assert "staging" in payload["blockers"]
    assert "production" in payload["blockers"]
    assert payload["production_ready"] is False
    assert "go_no_go_required" in payload.get("production", {})


@pytest.mark.asyncio
async def test_production_gate_blocked_in_readiness(async_client):
    """Production gate is blocked by default."""
    response = await async_client.get("/api/v1/health/readiness")
    assert response.status_code == 200
    payload = response.json()

    prod = payload.get("production", {})
    assert prod.get("production_ready") is False
    assert len(prod.get("blockers", [])) >= 1
    assert any("go/no-go" in str(b).lower() for b in prod["blockers"])


@pytest.mark.asyncio
async def test_local_agent_endpoint_returns_ready_flags(async_client):
    """Local agent readiness endpoint returns all subsystem flags."""
    response = await async_client.get("/api/v1/health/readiness/local-agent")
    assert response.status_code == 200
    payload = response.json()

    assert payload["FULL_LOCAL_AGENT_READY"] is True
    assert payload["STAGING_READY"] is False
    assert payload["PRODUCTION_READY"] is False
    assert "LOCAL_FUNNEL_READY" in payload
    assert "LOCAL_MCP_READONLY_READY" in payload
    assert "LOCAL_MCP_WRITE_READY" in payload
    assert "LOCAL_WORKSPACE_READY" in payload
    assert "LOCAL_CONTEXT_READY" in payload
    assert "LOCAL_WORKFLOW_READY" in payload
    assert "LOCAL_UI_READY" in payload
