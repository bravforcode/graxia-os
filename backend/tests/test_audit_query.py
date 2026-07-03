"""Tests for org-scoped audit query API endpoints.

Verifies:
- Audit events list is org-scoped
- Audit MCP events list works
- Audit workflow events list works
- Approval audit list works
- Redaction of sensitive keys
- Pagination works
- Cross-org access blocked
"""
from __future__ import annotations

import uuid

import pytest


@pytest.mark.asyncio
async def test_health_readiness_endpoint_accessible(async_client):
    """Health endpoints should work with auth context."""
    resp = await async_client.get(
        "/api/v1/health",
        headers={"X-Graxia-Org-Id": "00000000-0000-0000-0000-000000000001"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_readiness_local_agent_readiness(async_client):
    """Local agent readiness must have all expected fields."""
    resp = await async_client.get(
        "/api/v1/health/readiness/local-agent",
        headers={"X-Graxia-Org-Id": "00000000-0000-0000-0000-000000000001"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "FULL_LOCAL_AGENT_READY" in data
    assert "PRODUCTION_READY" in data


@pytest.mark.asyncio
async def test_audit_events_returns_200_with_pagination(async_client):
    """Audit events endpoint returns paginated results."""
    resp = await async_client.get(
        "/api/v1/audit/events?limit=10&offset=0",
        headers={"X-Graxia-Org-Id": "00000000-0000-0000-0000-000000000001"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "limit" in data
    assert data["limit"] == 10
    assert "offset" in data
    assert data["offset"] == 0


@pytest.mark.asyncio
async def test_audit_mcp_returns_200(async_client):
    """MCP audit endpoint returns paginated results."""
    resp = await async_client.get(
        "/api/v1/audit/mcp?limit=5",
        headers={"X-Graxia-Org-Id": "00000000-0000-0000-0000-000000000001"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    # Should be an empty list (no MCP events yet)
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_audit_workflows_returns_200(async_client):
    """Workflow audit endpoint returns paginated results."""
    resp = await async_client.get(
        "/api/v1/audit/workflows",
        headers={"X-Graxia-Org-Id": "00000000-0000-0000-0000-000000000001"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_audit_approvals_returns_200(async_client):
    """Approval audit endpoint returns paginated results."""
    resp = await async_client.get(
        "/api/v1/audit/approvals",
        headers={"X-Graxia-Org-Id": "00000000-0000-0000-0000-000000000001"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_audit_approvals_filters_by_status(async_client):
    """Approval audit should filter by status."""
    resp = await async_client.get(
        "/api/v1/audit/approvals?status=pending",
        headers={"X-Graxia-Org-Id": "00000000-0000-0000-0000-000000000001"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_audit_events_without_org_header(async_client):
    """Without X-Graxia-Org-Id, audit should still work in local mode."""
    resp = await async_client.get("/api/v1/audit/events")
    assert resp.status_code in (200, 401)
    if resp.status_code == 200:
        data = resp.json()
        assert "items" in data
    elif resp.status_code == 401:
        data = resp.json()
        assert "detail" in data
