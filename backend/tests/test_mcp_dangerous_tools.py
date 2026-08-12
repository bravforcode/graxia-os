"""Tests for MCP dangerous blocked tools — verify DANGEROUS_TOOL_BLOCKED response."""
from __future__ import annotations

import pytest

from app.mcp.registry import mcp_registry
from app.mcp.schemas import MCPAuthContext
from app.mcp.errors import ERR_DANGEROUS_BLOCKED

# Ensure tool modules are imported so their decorators register tools
import app.mcp.tools.dangerous  # noqa: F401

TEST_ORG_ID = "00000000-0000-0000-0000-000000000001"


@pytest.mark.asyncio
class TestDangerousBlockedTools:
    """All dangerous tools must:
    1. Return DANGEROUS_TOOL_BLOCKED error code
    2. Never execute any action
    3. Return safe message with no details
    """

    BLOCKED_TOOLS = [
        "deploy_production",
        "read_env",
        "print_secrets",
        "rotate_keys",
        "delete_database",
        "force_push",
        "change_stripe_secret_config",
    ]

    @pytest.fixture
    def auth(self):
        return MCPAuthContext.system(organization_id=TEST_ORG_ID)

    async def _assert_blocked(self, tool_name: str, auth: MCPAuthContext) -> None:
        """Assert a tool returns DANGEROUS_TOOL_BLOCKED."""
        resp = await mcp_registry.call_tool(tool_name, {}, auth=auth)
        assert resp.ok is False, f"Tool {tool_name} should return ok=False"
        assert resp.error is not None, f"Tool {tool_name} should have error"
        assert resp.error.code == ERR_DANGEROUS_BLOCKED, (
            f"Tool {tool_name} should return {ERR_DANGEROUS_BLOCKED}, got: {resp.error.code}"
        )
        assert resp.error.message == "This tool is intentionally blocked for safety."
        assert resp.error.safe_to_retry is False

    # ── Individual tool tests ─────────────────────────────────────────────

    async def test_deploy_production_blocked(self, auth):
        await self._assert_blocked("deploy_production", auth)

    async def test_read_env_blocked(self, auth):
        await self._assert_blocked("read_env", auth)

    async def test_print_secrets_blocked(self, auth):
        await self._assert_blocked("print_secrets", auth)

    async def test_rotate_keys_blocked(self, auth):
        await self._assert_blocked("rotate_keys", auth)

    async def test_delete_database_blocked(self, auth):
        await self._assert_blocked("delete_database", auth)

    async def test_force_push_blocked(self, auth):
        await self._assert_blocked("force_push", auth)

    async def test_change_stripe_secret_config_blocked(self, auth):
        await self._assert_blocked("change_stripe_secret_config", auth)

    # ── All blocked tools in one test ─────────────────────────────────────

    async def test_all_blocked_tools(self, auth):
        """Test every blocked tool returns the correct response."""
        for tool_name in self.BLOCKED_TOOLS:
            await self._assert_blocked(tool_name, auth)

    # ── Edge cases ────────────────────────────────────────────────────────

    async def test_blocked_tool_with_invalid_args(self, auth):
        """Blocked tools should return blocked even with unexpected args."""
        resp = await mcp_registry.call_tool(
            "read_env",
            {"organization_id": "some-org", "should_not_matter": True},
            auth=auth,
        )
        assert resp.ok is False
        assert resp.error.code == ERR_DANGEROUS_BLOCKED

    async def test_blocked_tool_without_auth(self):
        """Blocked tools should still return blocked even without auth."""
        resp = await mcp_registry.call_tool("delete_database", {}, auth=None)
        assert resp.ok is False
        assert resp.error.code == ERR_DANGEROUS_BLOCKED

    async def test_blocked_tool_cannot_be_bypassed_by_role(self):
        """Even system role cannot execute blocked tools."""
        resp = await mcp_registry.call_tool("force_push", {}, auth=MCPAuthContext.system())
        assert resp.ok is False
        assert resp.error.code == ERR_DANGEROUS_BLOCKED

    # ── Tool Listing ───────────────────────────────────────────────────────

    async def test_dangerous_tools_appear_in_listing(self, auth):
        """Dangerous tools should show up with DANGEROUS_BLOCKED risk level."""
        tools = mcp_registry.list_tools(risk_level="DANGEROUS_BLOCKED")
        tool_names = [t["name"] for t in tools]
        for blocked_tool in self.BLOCKED_TOOLS:
            assert blocked_tool in tool_names, f"{blocked_tool} should be in DANGEROUS_BLOCKED listing"
        for t in tools:
            assert t["risk_level"] == "DANGEROUS_BLOCKED"

    async def test_no_action_executed(self, auth):
        """Verify blocked tools do not create any database records.

        This is a safety check — blocked tools should never write to DB.
        """
        from app.database import AsyncSessionLocal
        from app.models.approval_request import ApprovalRequest
        from sqlalchemy import select, func

        before_count = 0
        async with AsyncSessionLocal() as db:
            before_count = await db.scalar(select(func.count(ApprovalRequest.id))) or 0

        # Call all blocked tools
        for tool_name in self.BLOCKED_TOOLS:
            await mcp_registry.call_tool(tool_name, {}, auth=auth)

        # Verify no new ApprovalRequests were created by blocked tools
        async with AsyncSessionLocal() as db:
            after_count = await db.scalar(select(func.count(ApprovalRequest.id))) or 0
        assert after_count == before_count, "Blocked tools should not create any records"
