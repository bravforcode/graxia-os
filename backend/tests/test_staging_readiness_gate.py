from __future__ import annotations

import pytest

ORG_HEADERS = {"X-Graxia-Org-Id": "00000000-0000-0000-0000-000000000001"}


@pytest.mark.asyncio
async def test_staging_readiness_includes_integrated_runtime_checks(async_client):
    resp = await async_client.get("/api/v1/health/readiness/staging", headers=ORG_HEADERS)
    assert resp.status_code == 200

    data = resp.json()
    checks = data["checks"]

    expected_keys = {
        "database_connectivity",
        "runtime_ready",
        "auth_context_middleware",
        "real_auth_context_active",
        "staging_auth_guard",
        "rate_limiting_active",
        "health_endpoints",
        "runtime_contracts_present",
        "runtime_adapters_present",
        "runtime_gateway_present",
        "runtime_orchestration_present",
        "runtime_worker_present",
        "context_quality_gate_present",
        "token_roi_controls_present",
        "mcp_runtime_tools_present",
        "staging_smoke_scripts_present",
        "google_write_scopes_disabled",
        "stripe_live_mode_blocked",
        "real_email_send_blocked",
    }

    assert expected_keys.issubset(checks.keys())
    assert all(isinstance(checks[key], bool) for key in expected_keys)
    assert "runtime" in data
    assert isinstance(data["runtime"], dict)


@pytest.mark.asyncio
async def test_staging_readiness_remains_conservative_without_real_staging(async_client):
    resp = await async_client.get("/api/v1/health/readiness/staging", headers=ORG_HEADERS)
    assert resp.status_code == 200

    data = resp.json()
    assert data["staging_ready"] is False
    assert data["checks"]["runtime_contracts_present"] is True
    assert data["checks"]["runtime_gateway_present"] is True
    assert data["checks"]["mcp_runtime_tools_present"] is True
    assert data["checks"]["google_write_scopes_disabled"] is True
    assert any("APP_ENV is not 'staging'." == blocker for blocker in data["blockers"])
    assert any("mock auth" in blocker.lower() for blocker in data["blockers"])


@pytest.mark.asyncio
async def test_readiness_endpoint_embeds_staging_gate(async_client):
    resp = await async_client.get("/api/v1/health/readiness", headers=ORG_HEADERS)
    assert resp.status_code == 200

    data = resp.json()
    assert data["staging_ready"] is data["staging"]["staging_ready"]
    assert data["blockers"]["staging"] == data["staging"]["blockers"]
    assert data["checks"]["staging_gate_blockers"] == len(data["staging"]["blockers"])
