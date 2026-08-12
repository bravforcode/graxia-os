from __future__ import annotations

import pytest

ORG_HEADERS = {"X-Graxia-Org-Id": "00000000-0000-0000-0000-000000000001"}


@pytest.mark.asyncio
async def test_production_readiness_endpoint_is_closed_by_default(async_client):
    resp = await async_client.get("/api/v1/health/readiness/production", headers=ORG_HEADERS)
    assert resp.status_code == 200

    data = resp.json()
    assert data["production_ready"] is False
    assert data["go_no_go_required"] is True
    assert any("go/no-go" in blocker.lower() for blocker in data["blockers"])


@pytest.mark.asyncio
async def test_production_readiness_reports_provider_guards(async_client):
    resp = await async_client.get("/api/v1/health/readiness/production", headers=ORG_HEADERS)
    assert resp.status_code == 200

    checks = resp.json()["checks"]
    assert checks["live_stripe_blocked"] is True
    assert checks["real_email_send_blocked"] is True
    assert checks["real_google_mutation_blocked"] is True
    assert checks["real_llm_calls_blocked"] is True


@pytest.mark.asyncio
async def test_root_readiness_embeds_production_gate(async_client):
    resp = await async_client.get("/api/v1/health/readiness", headers=ORG_HEADERS)
    assert resp.status_code == 200

    data = resp.json()
    assert data["production_ready"] is False
    assert data["production"]["production_ready"] is False
    assert data["production"]["go_no_go_required"] is True
    assert data["blockers"]["production"] == data["production"]["blockers"]
    assert data["checks"]["production_gate_blockers"] == len(data["production"]["blockers"])
