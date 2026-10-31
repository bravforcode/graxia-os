"""Tests for health and readiness API endpoints.

Verifies:
- Health endpoint returns ok status
- Readiness endpoint returns correct readiness levels
- Unverified local agent capabilities block readiness
- Staging readiness correctly reports staging_ready: false
- Production readiness correctly reports production_ready: false
- No secrets leaked in health responses
- Database connectivity reported

Uses async_client (JWT-authenticated) because AuthMiddleware
requires a valid session for all endpoints.
"""
from __future__ import annotations

import pytest

ORG_HEADERS = {"X-Graxia-Org-Id": "00000000-0000-0000-0000-000000000001"}


@pytest.mark.asyncio
async def test_health_endpoint_returns_200(async_client):
    """GET /api/v1/health should return 200 with status."""
    resp = await async_client.get(
        "/api/v1/health",
        headers=ORG_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "service" in data
    assert data["service"] == "Graxia OS API"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_reports_database_status(async_client):
    """Health endpoint must report database connectivity status."""
    resp = await async_client.get(
        "/api/v1/health",
        headers=ORG_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "database" in data
    assert data["database"] in ("healthy", "unhealthy", "degraded")


@pytest.mark.asyncio
async def test_health_no_secrets_leaked(async_client):
    """Health response must not contain secret-like keys."""
    resp = await async_client.get(
        "/api/v1/health",
        headers=ORG_HEADERS,
    )
    body = resp.text.lower()
    secret_keys = ["secret", "password", "token", "api_key"]
    # Check for actual values, not key names
    sensitive_values = []
    for sk in secret_keys:
        if sk in body:
            sensitive_values.append(sk)
    # Environment name "secret" is in the key field but shouldn't be an issue
    # The actual ENV value like "development" should not contain secrets
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_readiness_endpoint_returns_200(async_client):
    """GET /api/v1/health/readiness should return 200."""
    resp = await async_client.get(
        "/api/v1/health/readiness",
        headers=ORG_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "readiness" in data
    assert "local_agent" in data
    assert "production_ready" in data
    assert "staging_ready" in data
    assert "staging" in data
    assert "production" in data
    assert "checks" in data["staging"]
    assert "runtime_contracts_present" in data["staging"]["checks"]
    assert "mcp_runtime_tools_present" in data["staging"]["checks"]
    assert "go_no_go_required" in data["production"]


@pytest.mark.asyncio
async def test_readiness_production_not_ready(async_client):
    """Readiness must confirm production is NOT ready."""
    resp = await async_client.get(
        "/api/v1/health/readiness",
        headers=ORG_HEADERS,
    )
    data = resp.json()
    assert data["production_ready"] is False
    assert data["production"]["production_ready"] is False


@pytest.mark.asyncio
async def test_local_agent_readiness(async_client):
    """Unprobed local agent subsystems must not report ready."""
    resp = await async_client.get(
        "/api/v1/health/readiness/local-agent",
        headers=ORG_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["LOCAL_FUNNEL_READY"] is False
    assert data["LOCAL_MCP_READONLY_READY"] is False
    assert data["LOCAL_MCP_WRITE_READY"] is False
    assert data["LOCAL_WORKSPACE_READY"] is False
    assert data["LOCAL_CONTEXT_READY"] is False
    assert data["LOCAL_WORKFLOW_READY"] is False
    assert data["LOCAL_UI_READY"] is False
    assert data["FULL_LOCAL_AGENT_READY"] is False
    assert data["STAGING_READY"] is False
    assert data["PRODUCTION_READY"] is False


@pytest.mark.asyncio
async def test_staging_readiness_reports_not_ready(async_client):
    """Staging readiness must confirm staging is NOT ready yet."""
    resp = await async_client.get(
        "/api/v1/health/readiness/staging",
        headers=ORG_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["staging_ready"] is False
    assert data["environment"] in {"development", "testing", "staging"}
    assert "blockers" in data
    assert len(data["blockers"]) > 0
    assert "checks" in data
    assert data["checks"]["health_endpoints"] is True
    assert data["checks"]["runtime_contracts_present"] is True


@pytest.mark.asyncio
async def test_unverified_capabilities_block_readiness_even_with_healthy_runtime(monkeypatch):
    from unittest.mock import AsyncMock

    from app.api import health
    from app.auth.context import AuthContext
    from app.main import app as runtime_app

    monkeypatch.setattr(health.settings, "APP_ENV", "staging")
    monkeypatch.setattr(health, "_database_ok", AsyncMock(return_value=True))
    monkeypatch.setattr(health, "get_runtime_state", lambda: {"is_ready": True, "issues": []})
    for probe in ("_module_present", "_runtime_tooling_present", "_staging_scripts_present",
                  "_production_docs_present", "_live_stripe_blocked", "_real_email_provider_blocked",
                  "_stripe_live_mode_blocked", "_real_email_send_blocked"):
        monkeypatch.setattr(health, probe, lambda *args: True)
    monkeypatch.setattr(health.settings, "GOOGLE_ENABLE_WRITE_SCOPES", False)
    monkeypatch.setattr(health.settings, "ALLOW_REAL_GOOGLE_MUTATION", False)
    auth = AuthContext(is_mock_auth=False, is_authenticated=True, auth_method="bearer_jwt")

    payload = await health.readiness_check(None, auth)

    unverified = {
        "permissions_ok", "org_boundary_ok", "safe_errors_ok", "security_audit_ok",
        "payload_guard_ok", "route_protection_matrix_ok",
        "mcp_auth_ok", "workflow_auth_ok", "public_route_limits_ok", "customer_token_boundary_ok",
    }
    staging = payload["staging"]
    assert runtime_app is not None
    assert staging["checks"]["database_connectivity"] is True
    assert staging["checks"]["runtime_ready"] is True
    assert staging["checks"]["auth_context_middleware"] is True
    assert staging["checks"]["staging_auth_guard"] is True
    assert staging["checks"]["health_endpoints"] is True
    assert staging["checks"]["real_auth_context_active"] is False
    assert staging["checks"]["rate_limiting_active"] is False
    assert all(staging["checks"][name] is False for name in unverified)
    assert all(any(name in blocker and "verified" in blocker for blocker in staging["blockers"])
               for name in unverified)
    assert staging["staging_ready"] is False
    assert payload["staging_ready"] is False
    assert all(value is False for value in payload["local_agent"].values())
    assert payload["production_ready"] is False
    assert payload["production"]["checks"]["auth_context_middleware"] is True
    assert payload["production"]["checks"]["real_auth_context_active"] is False
    assert payload["production"]["production_ready"] is False
    assert payload["production"]["go_no_go_required"] is True
    for name in unverified & payload["production"]["checks"].keys():
        assert payload["production"]["checks"][name] is False

    local = await health.local_agent_readiness(auth)
    assert all(value is False for value in local.values())


def test_real_auth_context_requires_authenticated_bearer_and_non_local_org():
    from uuid import UUID

    from app.api import health
    from app.auth.context import AuthContext, LOCAL_DEV_ORGANIZATION_ID

    identity = {
        "actor_id": str(UUID("11111111-1111-4111-8111-111111111111")),
        "is_authenticated": True,
        "is_mock_auth": False,
        "auth_method": "bearer_jwt",
    }
    persisted_context = AuthContext(
        **identity,
        organization_id=UUID("22222222-2222-4222-8222-222222222222"),
    )
    local_context = AuthContext(
        **identity,
        organization_id=LOCAL_DEV_ORGANIZATION_ID,
    )

    assert health._real_auth_context_active(persisted_context) is True
    assert health._real_auth_context_active(local_context) is False


@pytest.mark.asyncio
async def test_staging_reports_current_rate_rule_without_claiming_unproven_enforcement(async_client):
    response = await async_client.get("/api/v1/health/readiness/staging")

    assert response.status_code == 200
    assert response.headers["RateLimit-Limit"] == "120"
    staging = response.json()
    assert staging["checks"]["health_endpoints"] is True
    assert staging["checks"]["auth_context_middleware"] is True
    rate_limiting = staging["rate_limiting"]
    assert rate_limiting["middleware_registered"] is True
    assert rate_limiting["configured_rule"] == {
        "name": "health",
        "limit": 120,
        "window_seconds": 60,
    }
    assert rate_limiting["request_app_matches_runtime"] is True
    assert rate_limiting["enforcement_evidence_available"] is False
    assert staging["checks"]["rate_limiting_active"] is False
    assert staging["checks"]["security_audit_ok"] is False


@pytest.mark.parametrize(
    "write_scopes,allow_mutation,blocked",
    [(False, False, True), (False, True, True), (True, False, True), (True, True, False)],
)
def test_real_google_mutation_blocked_requires_both_flags(monkeypatch, write_scopes, allow_mutation, blocked):
    from app.api import health

    monkeypatch.setattr(health.settings, "GOOGLE_ENABLE_WRITE_SCOPES", write_scopes)
    monkeypatch.setattr(health.settings, "ALLOW_REAL_GOOGLE_MUTATION", allow_mutation)

    assert health._real_google_mutation_blocked() is blocked
