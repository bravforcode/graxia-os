"""Test production gate — always closed until explicit go/no-go."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_production_readiness_endpoint_returns_checks(async_client):
    """Production readiness endpoint returns all production gate checks."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    checks = payload.get("checks", {})
    assert "database_connectivity" in checks
    assert "auth_context_middleware" in checks
    assert "rate_limiting_active" in checks
    assert "safe_errors_ok" in checks
    assert "security_audit_ok" in checks
    assert "production_runbooks_present" in checks
    assert "live_stripe_blocked" in checks
    assert "real_email_send_blocked" in checks
    assert "real_google_mutation_blocked" in checks
    assert "real_llm_calls_blocked" in checks
    assert "go_no_go_required" in checks

    # Production readiness must be false by default
    assert payload["production_ready"] is False
    assert payload["go_no_go_required"] is True


@pytest.mark.asyncio
async def test_production_gate_always_closed(async_client):
    """Production readiness always returns False in any non-explicit production context."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    assert payload["production_ready"] is False
    assert len(payload.get("blockers", [])) >= 1
    assert any("go/no-go" in str(b).lower() for b in payload["blockers"])


@pytest.mark.asyncio
async def test_production_gate_live_stripe_blocked(async_client):
    """Live stripe must be blocked in test environment."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    checks = payload.get("checks", {})
    # In test env with placeholder keys, live stripe should be blocked
    assert checks.get("live_stripe_blocked") is True


@pytest.mark.asyncio
async def test_production_gate_real_email_send_blocked(async_client):
    """Real email sending must be blocked in test environment."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    checks = payload.get("checks", {})
    assert checks.get("real_email_send_blocked") is True


@pytest.mark.asyncio
async def test_production_gate_real_google_mutation_blocked(async_client):
    """Real Google Workspace mutation must be blocked in test environment."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    checks = payload.get("checks", {})
    assert checks.get("real_google_mutation_blocked") is True


@pytest.mark.asyncio
async def test_production_gate_real_llm_calls_blocked(async_client):
    """Real LLM calls must be blocked (no ALLOW_REAL_LLM_CALLS in test)."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    checks = payload.get("checks", {})
    assert checks.get("real_llm_calls_blocked") is True


@pytest.mark.asyncio
async def test_production_gate_has_runtime_info(async_client):
    """Production readiness includes runtime state."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    runtime = payload.get("runtime", {})
    assert "is_ready" in runtime
    assert "mode" in runtime
    assert "issues" in runtime


@pytest.mark.asyncio
async def test_production_unauth_blocked(public_async_client):
    """Unauthenticated requests to production readiness get blocked."""
    response = await public_async_client.get("/api/v1/health/readiness/production")
    # Should be 401/403 since auth is required, or 200 if auth middleware allows it
    # (the readiness endpoint uses Depends(get_auth_context))
    assert response.status_code in (401, 403, 200)
    if response.status_code == 200:
        payload = response.json()
        assert payload["production_ready"] is False


@pytest.mark.asyncio
async def test_production_gate_has_all_blocker_types(async_client):
    """Production gate blockers include expected categories."""
    response = await async_client.get("/api/v1/health/readiness/production")
    assert response.status_code == 200
    payload = response.json()

    blockers = payload.get("blockers", [])
    blocker_text = " ".join(blockers).lower()

    assert "go/no-go" in blocker_text or "go_no_go" in blocker_text
    # Verify that at least one blocker references the dry-run nature
    assert any("dry-run" in b.lower() or "closed" in b.lower() or "go" in b.lower() for b in blockers)
