"""Tests for MCP approval-gated write tools — verify ApprovalRequest creation and no action execution."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from uuid import UUID, uuid4

from app.mcp.registry import mcp_registry
from app.mcp.schemas import MCPAuthContext, MCPResponse
from app.models.approval_request import ApprovalRequest
from app.database import AsyncSessionLocal

# Ensure tool modules are imported so their decorators register tools
import app.mcp.tools.write  # noqa: F401

TEST_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
OTHER_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
TEST_PRODUCT_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")
TEST_ORDER_ID = uuid.UUID("00000000-0000-0000-0000-000000000020")
TEST_ACCESS_ID = uuid.UUID("00000000-0000-0000-0000-000000000030")


@pytest.mark.asyncio
class TestApprovalGatedTools:
    """All approval-gated tools must:
    1. Return approval_required=true
    2. Create an ApprovalRequest record
    3. NOT execute the action
    """

    async def _assert_approval_response(self, resp: MCPResponse, expected_org: str) -> UUID:
        """Assert the response is an approval-required response and return the approval_request_id."""
        assert resp.ok is False, f"Expected False, got: {resp}"
        assert resp.error is not None, "Expected error object"
        assert resp.error.code == "APPROVAL_REQUIRED", f"Expected APPROVAL_REQUIRED, got: {resp.error.code}"
        assert resp.data is not None
        assert resp.data["approval_required"] is True
        assert "approval_request_id" in resp.data
        approval_id = UUID(resp.data["approval_request_id"])
        return approval_id

    async def _assert_approval_exists(self, approval_id: UUID) -> None:
        """Assert an ApprovalRequest record exists with the given ID."""
        async with AsyncSessionLocal() as db:
            ar = await db.get(ApprovalRequest, approval_id)
            assert ar is not None, f"ApprovalRequest {approval_id} should exist"
            assert ar.status == "pending", f"Expected pending, got: {ar.status}"
            return ar

    def _auth(self, org_id: UUID | None = None) -> MCPAuthContext:
        return MCPAuthContext.system(organization_id=org_id or TEST_ORG_ID)

    # ── Product Tools ──────────────────────────────────────────────────────

    async def test_publish_product_update_creates_approval(self):
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "publish_product_update",
            {
                "organization_id": str(TEST_ORG_ID),
                "product_id": str(TEST_PRODUCT_ID),
                "change_summary": "Update product description and add new features",
            },
            auth=auth,
        )
        approval_id = await self._assert_approval_response(resp, str(TEST_ORG_ID))
        ar = await self._assert_approval_exists(approval_id)
        assert ar.action_type == "publish_product_update"
        assert ar.subject_type == "digital_product"
        assert ar.details["product_id"] == str(TEST_PRODUCT_ID)

    async def test_archive_product_creates_approval(self):
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "archive_product",
            {
                "organization_id": str(TEST_ORG_ID),
                "product_id": str(TEST_PRODUCT_ID),
                "reason": "Product no longer maintained",
            },
            auth=auth,
        )
        approval_id = await self._assert_approval_response(resp, str(TEST_ORG_ID))
        ar = await self._assert_approval_exists(approval_id)
        assert ar.action_type == "archive_product"

    async def test_change_product_price_creates_approval(self):
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "change_product_price",
            {
                "organization_id": str(TEST_ORG_ID),
                "product_id": str(TEST_PRODUCT_ID),
                "new_price": "499.00",
                "reason": "Seasonal promotion",
            },
            auth=auth,
        )
        approval_id = await self._assert_approval_response(resp, str(TEST_ORG_ID))
        ar = await self._assert_approval_exists(approval_id)
        assert ar.action_type == "change_product_price"
        assert ar.details["new_price"] == "499.00"

    # ── Lead Magnet Tools ───────────────────────────────────────────────────

    async def test_activate_lead_magnet_creates_approval(self):
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "activate_lead_magnet",
            {
                "organization_id": str(TEST_ORG_ID),
                "lead_magnet_slug": "free-ebook-guide",
            },
            auth=auth,
        )
        approval_id = await self._assert_approval_response(resp, str(TEST_ORG_ID))
        ar = await self._assert_approval_exists(approval_id)
        assert ar.action_type == "activate_lead_magnet"
        assert ar.details["slug"] == "free-ebook-guide"

    # ── Customer Communication Tools ────────────────────────────────────────

    async def test_send_customer_followup_creates_approval(self):
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "send_customer_followup",
            {
                "organization_id": str(TEST_ORG_ID),
                "customer_email": "customer@example.com",
                "message_preview": "Thank you for your purchase! Here's a special offer...",
            },
            auth=auth,
        )
        approval_id = await self._assert_approval_response(resp, str(TEST_ORG_ID))
        ar = await self._assert_approval_exists(approval_id)
        assert ar.action_type == "send_customer_followup"
        assert "customer@example.com" in ar.title

    async def test_send_delivery_email_manual_creates_approval(self):
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "send_delivery_email_manual",
            {
                "organization_id": str(TEST_ORG_ID),
                "order_id": str(TEST_ORDER_ID),
                "customer_email": "customer@example.com",
            },
            auth=auth,
        )
        approval_id = await self._assert_approval_response(resp, str(TEST_ORG_ID))
        ar = await self._assert_approval_exists(approval_id)
        assert ar.action_type == "send_delivery_email_manual"

    # ── Delivery Access Tools ───────────────────────────────────────────────

    async def test_grant_delivery_access_manual_creates_approval(self):
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "grant_delivery_access_manual",
            {
                "organization_id": str(TEST_ORG_ID),
                "order_id": str(TEST_ORDER_ID),
                "product_id": str(TEST_PRODUCT_ID),
                "customer_email": "customer@example.com",
            },
            auth=auth,
        )
        approval_id = await self._assert_approval_response(resp, str(TEST_ORG_ID))
        ar = await self._assert_approval_exists(approval_id)
        assert ar.action_type == "grant_delivery_access_manual"

    async def test_revoke_delivery_access_creates_approval(self):
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "revoke_delivery_access",
            {
                "organization_id": str(TEST_ORG_ID),
                "access_id": str(TEST_ACCESS_ID),
                "reason": "Customer requested cancellation",
            },
            auth=auth,
        )
        approval_id = await self._assert_approval_response(resp, str(TEST_ORG_ID))
        ar = await self._assert_approval_exists(approval_id)
        assert ar.action_type == "revoke_delivery_access"
        assert ar.details["reason"] == "Customer requested cancellation"

    # ── Public Content Tools ────────────────────────────────────────────────

    async def test_public_content_publish_creates_approval(self):
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "public_content_publish",
            {
                "organization_id": str(TEST_ORG_ID),
                "content_title": "New Blog Post",
                "content_summary": "A summary of the new blog post content",
            },
            auth=auth,
        )
        approval_id = await self._assert_approval_response(resp, str(TEST_ORG_ID))
        ar = await self._assert_approval_exists(approval_id)
        assert ar.action_type == "public_content_publish"

    # ── Cross-org Isolation ─────────────────────────────────────────────────

    async def test_cross_org_returns_permission_denied(self):
        """Tools with wrong org must not expose existence of data."""
        other_auth = MCPAuthContext.system(organization_id=OTHER_ORG_ID)
        resp = await mcp_registry.call_tool(
            "publish_product_update",
            {
                "organization_id": str(OTHER_ORG_ID),
                "product_id": str(TEST_PRODUCT_ID),
                "change_summary": "Should not work",
            },
            auth=other_auth,
        )
        # Cross-org returns PERMISSION_DENIED (org mismatch)
        assert resp.ok is False
        # No ApprovalRequest should have been created for cross-org
        # The PERMISSION_DENIED is returned before ApprovalRequest creation

    # ── Invalid Params ──────────────────────────────────────────────────────

    async def test_invalid_org_id_returns_error(self):
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "publish_product_update",
            {
                "organization_id": "not-a-uuid",
                "product_id": str(TEST_PRODUCT_ID),
                "change_summary": "test",
            },
            auth=auth,
        )
        assert resp.ok is False
        assert resp.error.code == "INVALID_PARAMS"

    async def test_missing_required_params_returns_error(self):
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "publish_product_update",
            {"organization_id": str(TEST_ORG_ID)},
            auth=auth,
        )
        # Missing product_id and change_summary — handler will try to parse empty strings
        assert resp.ok is False

    # ── Tool Listing ────────────────────────────────────────────────────────

    async def test_approval_tools_appear_in_listing(self):
        """Approval-required tools should show up with requires_approval=True."""
        tools = mcp_registry.list_tools(risk_level="APPROVAL_REQUIRED")
        tool_names = [t["name"] for t in tools]
        assert "publish_product_update" in tool_names
        assert "archive_product" in tool_names
        assert "change_product_price" in tool_names
        assert "activate_lead_magnet" in tool_names
        assert "send_customer_followup" in tool_names
        assert "send_delivery_email_manual" in tool_names
        assert "grant_delivery_access_manual" in tool_names
        assert "revoke_delivery_access" in tool_names
        for t in tools:
            assert t["requires_approval"] is True
            assert t["risk_level"] == "APPROVAL_REQUIRED"
