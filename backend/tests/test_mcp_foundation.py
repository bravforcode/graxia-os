"""Tests for MCP foundation — registry, schemas, auth, permissions, errors, audit."""
from __future__ import annotations

import json
import uuid

import pytest

from app.mcp.schemas import (
    MCPAuthContext,
    MCPError,
    MCPResponse,
    MCPResponseMeta,
    MCPToolDefinition,
    RISK_READ_ONLY,
    RISK_LOW_WRITE,
    RISK_APPROVAL_REQUIRED,
    RISK_DANGEROUS_BLOCKED,
)
from app.mcp.permissions import RiskPolicy, risk_policy
from app.mcp.errors import (
    ERR_TOOL_NOT_FOUND,
    ERR_INTERNAL,
    ERR_DANGEROUS_BLOCKED,
    safe_error_response,
    handle_tool_error,
)
from app.mcp.auth import validate_org_context
from app.mcp.registry import mcp_registry
from app.mcp.audit import log_mcp_tool_call, redact_for_audit


# Ensure tool modules are imported so their decorators register tools
import app.mcp.tools.system  # noqa: F401
import app.mcp.tools.funnel  # noqa: F401


# ── Schema Tests ──────────────────────────────────────────────────────────


class TestMCPResponse:
    def test_ok_response(self):
        resp = MCPResponse.ok_response(
            data={"status": "ok"},
            request_id="req-1",
            organization_id="org-1",
            estimated_tokens=42,
        )
        assert resp.ok is True
        assert resp.data == {"status": "ok"}
        assert resp.error is None
        assert resp.meta.request_id == "req-1"
        assert resp.meta.organization_id == "org-1"
        assert resp.meta.estimated_tokens == 42

    def test_error_response(self):
        resp = MCPResponse.error_response(
            code="TEST_ERROR",
            message="Something went wrong.",
            safe_to_retry=True,
            request_id="req-2",
        )
        assert resp.ok is False
        assert resp.data is None
        assert resp.error is not None
        assert resp.error.code == "TEST_ERROR"
        assert resp.error.message == "Something went wrong."
        assert resp.error.safe_to_retry is True

    def test_to_dict_success(self):
        resp = MCPResponse.ok_response(data={"key": "val"}, request_id="r1", organization_id="o1")
        d = resp.to_dict()
        assert d["ok"] is True
        assert d["data"] == {"key": "val"}
        assert d["error"] is None
        assert d["meta"]["request_id"] == "r1"

    def test_to_dict_error(self):
        resp = MCPResponse.error_response(code="ERR", message="fail", request_id="r2", organization_id="o2")
        d = resp.to_dict()
        assert d["ok"] is False
        assert d["data"] is None
        assert d["error"]["code"] == "ERR"
        assert d["error"]["message"] == "fail"
        assert d["error"]["safe_to_retry"] is False


class TestMCPAuthContext:
    def test_system_auth(self):
        auth = MCPAuthContext.system()
        assert auth.actor_type == "system"
        assert auth.actor_id == "system"
        assert auth.organization_id is None

    def test_custom_auth(self):
        auth = MCPAuthContext(
            organization_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            actor_type="user",
            actor_id="user-123",
        )
        assert auth.actor_type == "user"
        assert auth.actor_id == "user-123"
        assert auth.organization_id is not None


class TestMCPToolDefinition:
    def test_minimal_tool(self):
        tool = MCPToolDefinition(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
        )
        assert tool.name == "test_tool"
        assert tool.risk_level == RISK_READ_ONLY
        assert tool.requires_approval is False

    def test_full_tool(self):
        tool = MCPToolDefinition(
            name="danger_tool",
            description="Dangerous",
            input_schema={},
            output_schema={},
            risk_level=RISK_DANGEROUS_BLOCKED,
            required_permission="admin.super",
            requires_approval=True,
            handler="app.tools.danger",
        )
        assert tool.risk_level == RISK_DANGEROUS_BLOCKED
        assert tool.requires_approval is True


# ── Permission Tests ─────────────────────────────────────────────────────


class TestRiskPolicy:
    def test_blocked_tools(self):
        assert risk_policy.is_blocked("deploy_production") is True
        assert risk_policy.is_blocked("read_env") is True
        assert risk_policy.is_blocked("print_secrets") is True
        assert risk_policy.is_blocked("rotate_keys") is True
        assert risk_policy.is_blocked("delete_database") is True
        assert risk_policy.is_blocked("force_push") is True
        assert risk_policy.is_blocked("change_stripe_secret_config") is True

    def test_safe_tools_not_blocked(self):
        assert risk_policy.is_blocked("get_system_status") is False
        assert risk_policy.is_blocked("list_products") is False
        assert risk_policy.is_blocked("get_revenue_summary") is False

    def test_approval_required_tools(self):
        assert risk_policy.requires_approval("publish_product_update") is True
        assert risk_policy.requires_approval("change_product_price") is True
        assert risk_policy.requires_approval("send_customer_email") is True

    def test_risk_level_mapping(self):
        assert risk_policy.risk_level("get_system_status") == RISK_READ_ONLY
        assert risk_policy.risk_level("deploy_production") == RISK_DANGEROUS_BLOCKED
        assert risk_policy.risk_level("publish_product_update") == RISK_APPROVAL_REQUIRED
        # Write tools that aren't in blocked or approval should be LOW_WRITE
        assert risk_policy.risk_level("create_product") == RISK_LOW_WRITE

    def test_check_access_blocked(self):
        from app.mcp.schemas import MCPToolDefinition
        tool = MCPToolDefinition(
            name="deploy_production",
            description="",
            input_schema={},
            output_schema={},
            risk_level=RISK_DANGEROUS_BLOCKED,
        )
        allowed, reason = risk_policy.check_access(tool, None)
        assert allowed is False
        assert "blocked" in reason.lower()

    def test_check_access_approval(self):
        from app.mcp.schemas import MCPToolDefinition
        tool = MCPToolDefinition(
            name="change_product_price",
            description="",
            input_schema={},
            output_schema={},
            risk_level=RISK_APPROVAL_REQUIRED,
        )
        allowed, reason = risk_policy.check_access(tool, MCPAuthContext.system())
        assert allowed is False
        assert "approval" in reason.lower()

    def test_check_access_readonly_without_auth(self):
        from app.mcp.schemas import MCPToolDefinition
        tool = MCPToolDefinition(
            name="list_products",
            description="",
            input_schema={},
            output_schema={},
            risk_level=RISK_READ_ONLY,
        )
        # Read-only should be allowed even without auth
        allowed, _ = risk_policy.check_access(tool, None)
        assert allowed is True


# ── Auth Tests ────────────────────────────────────────────────────────────


class TestAuth:
    def test_org_match(self):
        org_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        auth = MCPAuthContext(organization_id=org_id)
        assert validate_org_context(auth, org_id) is True

    def test_org_mismatch(self):
        auth = MCPAuthContext(
            organization_id=uuid.UUID("00000000-0000-0000-0000-000000000001")
        )
        other = uuid.UUID("00000000-0000-0000-0000-000000000002")
        assert validate_org_context(auth, other) is False

    def test_system_bypass(self):
        auth = MCPAuthContext.system()
        assert validate_org_context(auth, None) is True

    def test_no_auth_public_ok(self):
        assert validate_org_context(None, None) is True

    def test_no_auth_private_fail(self):
        org_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        assert validate_org_context(None, org_id) is False


# ── Error Tests ───────────────────────────────────────────────────────────


class TestErrors:
    def test_safe_error_response(self):
        resp = safe_error_response(
            code=ERR_TOOL_NOT_FOUND,
            request_id="req-1",
            organization_id="org-1",
        )
        assert resp.ok is False
        assert resp.error.code == ERR_TOOL_NOT_FOUND
        assert "not found" in resp.error.message.lower()

    def test_handle_tool_error(self):
        resp = handle_tool_error(
            tool_name="test_tool",
            exc=ValueError("bad value"),
            request_id="req-1",
        )
        assert resp.ok is False
        assert resp.error.code == "HANDLER_ERROR"
        # Should NOT contain the raw error message
        assert "bad value" not in resp.error.message
        assert "test_tool" in resp.error.message


# ── Registry Tests ────────────────────────────────────────────────────────


class TestRegistry:
    def test_registry_list_no_tools(self):
        # The mcp_registry should have tools pre-registered from system.py and funnel.py
        tools = mcp_registry.list_tools()
        assert len(tools) > 0

    def test_registry_has_system_tools(self):
        tools = mcp_registry.list_tools()
        names = [t["name"] for t in tools]
        assert "get_system_status" in names
        assert "get_latest_test_status" in names
        assert "get_token_optimizer_status" in names
        assert "get_funnel_phase_status" in names

    def test_registry_has_funnel_tools(self):
        tools = mcp_registry.list_tools()
        names = [t["name"] for t in tools]
        assert "list_products" in names
        assert "get_product" in names
        assert "list_delivery_assets" in names
        assert "get_orders_summary" in names
        assert "get_recent_orders" in names
        assert "get_revenue_summary" in names
        assert "get_conversion_summary" in names
        assert "get_checkout_abandonment" in names
        assert "get_delivery_open_rate" in names
        assert "get_pending_approvals" in names

    def test_registry_filter_by_risk(self):
        read_only = mcp_registry.list_tools(risk_level=RISK_READ_ONLY)
        for t in read_only:
            assert t["risk_level"] == RISK_READ_ONLY

    def test_registry_get_definition(self):
        tdef = mcp_registry.get_definition("get_system_status")
        assert tdef is not None
        assert tdef.description != ""

    def test_registry_unknown_tool(self):
        tdef = mcp_registry.get_definition("nonexistent_tool")
        assert tdef is None

    @pytest.mark.asyncio
    async def test_call_unknown_tool(self):
        resp = await mcp_registry.call_tool("nonexistent_tool", {})
        assert resp.ok is False
        assert resp.error.code == ERR_TOOL_NOT_FOUND

    @pytest.mark.asyncio
    async def test_call_system_status(self):
        auth = MCPAuthContext.system()
        resp = await mcp_registry.call_tool(
            "get_system_status",
            {},
            auth=auth,
        )
        assert resp.ok is True
        assert resp.data is not None
        assert resp.data["status"] == "operational"


# ── Audit Tests ───────────────────────────────────────────────────────────


class TestAudit:
    @pytest.mark.asyncio
    async def test_log_mcp_tool_call(self):
        entry = await log_mcp_tool_call(
            organization_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            actor_type="system",
            actor_id="test",
            tool_name="test_tool",
            risk_level="READ_ONLY",
            status="success",
            request_id="req-1",
        )
        assert entry is not None
        assert entry["tool_name"] == "test_tool"
        assert entry["status"] == "success"
        assert "raw" not in str(entry).lower()

    def test_redact_for_audit_ok(self):
        resp = MCPResponse.ok_response(data={"key": "value"})
        redacted = redact_for_audit(resp)
        assert "value" not in redacted  # Values should be redacted

    def test_redact_for_audit_error(self):
        resp = MCPResponse.error_response(code="ERR", message="error")
        redacted = redact_for_audit(resp)
        assert "ERR" in redacted  # Error codes are safe to include
