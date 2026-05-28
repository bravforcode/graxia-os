"""Phase 16 MCP auth and permission enforcement tests."""
from __future__ import annotations

from uuid import uuid4

import pytest

import app.mcp.tools  # noqa: F401
from app.mcp.registry import mcp_registry
from app.mcp.schemas import MCPAuthContext


@pytest.mark.asyncio
async def test_registry_requires_auth_for_non_blocked_tool():
    resp = await mcp_registry.call_tool("get_system_status", {}, auth=None)
    assert resp.ok is False
    assert resp.error is not None
    assert resp.error.code == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_registry_enforces_required_permission():
    auth = MCPAuthContext(
        organization_id=uuid4(),
        actor_type="user",
        actor_id="user-1",
        permissions=["mcp:read"],
        is_authenticated=True,
    )
    resp = await mcp_registry.call_tool("get_high_score_opportunities", {"organization_id": str(auth.organization_id)}, auth=auth)
    assert resp.ok is False
    assert resp.error is not None
    assert resp.error.code == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_registry_allows_permitted_system_read_tool():
    auth = MCPAuthContext(
        organization_id=uuid4(),
        actor_type="user",
        actor_id="user-2",
        permissions=["system:read"],
        is_authenticated=True,
    )
    resp = await mcp_registry.call_tool("get_system_status", {}, auth=auth)
    assert resp.ok is True
    assert resp.data is not None
    assert resp.data["status"] == "operational"


@pytest.mark.asyncio
async def test_registry_keeps_dangerous_tools_blocked_without_auth():
    resp = await mcp_registry.call_tool("force_push", {}, auth=None)
    assert resp.ok is False
    assert resp.error is not None
    assert resp.error.code == "DANGEROUS_TOOL_BLOCKED"


@pytest.mark.asyncio
async def test_registry_blocks_org_mismatch_even_with_permission():
    auth = MCPAuthContext(
        organization_id=uuid4(),
        actor_type="user",
        actor_id="user-3",
        permissions=["workflow:read"],
        is_authenticated=True,
    )
    other_org = str(uuid4())
    resp = await mcp_registry.call_tool(
        "list_agent_workflows",
        {"organization_id": other_org},
        auth=auth,
    )
    assert resp.ok is False
    assert resp.error is not None
    assert resp.error.code == "ORG_MISMATCH"
