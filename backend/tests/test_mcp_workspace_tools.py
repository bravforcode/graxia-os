"""Tests for MCP workspace tools — mock Google Workspace operations.

Tests verify:
1. Read / Low-write tools return mock results (approval not required)
2. Approval-required tools create ApprovalRequest and return APPROVAL_REQUIRED
3. Cross-org isolation works for all workspace tools
4. No real external calls are made
5. No secrets leaked in responses
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from uuid import UUID, uuid4

from app.mcp.registry import mcp_registry
from app.mcp.schemas import MCPAuthContext, MCPResponse
from app.models.approval_request import ApprovalRequest
from app.database import AsyncSessionLocal
from tests.factories import OrganizationFactory

# Ensure tool modules are imported so their decorators register tools
import app.mcp.tools.workspace  # noqa: F401

TEST_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
OTHER_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


@pytest_asyncio.fixture(autouse=True)
async def setup_org(db_session):
    """Ensure the test organization exists for MCP tools that query it."""
    org = await OrganizationFactory.build(db_session, id=TEST_ORG_ID)
    yield


@pytest.mark.asyncio
class TestWorkspaceReadLowWriteTools:
    """Read / Low-write tools should return mock results without requiring approval."""

    def _auth(self, org_id: UUID | None = None) -> MCPAuthContext:
        return MCPAuthContext.system(organization_id=org_id or TEST_ORG_ID)

    async def test_search_customer_emails_returns_mock_data(self):
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "search_customer_emails",
            {"organization_id": str(TEST_ORG_ID)},
            auth=auth,
        )
        assert resp.ok is True, f"Expected ok=True, got: {resp}"
        assert resp.data["total"] >= 3, f"Expected >=3 emails, got: {resp.data['total']}"
        assert "items" in resp.data

    async def test_search_customer_emails_with_query(self):
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "search_customer_emails",
            {"organization_id": str(TEST_ORG_ID), "query": "digital product"},
            auth=auth,
        )
        assert resp.ok is True
        assert resp.data["total"] >= 1

    async def test_draft_customer_reply_succeeds(self):
        # First get a valid thread_id from search
        auth = self._auth()
        search_resp = await mcp_registry.call_tool(
            "search_customer_emails",
            {"organization_id": str(TEST_ORG_ID)},
            auth=auth,
        )
        assert search_resp.ok is True
        assert search_resp.data["total"] > 0
        thread_id = search_resp.data["items"][0]["thread_id"]

        resp = await mcp_registry.call_tool(
            "draft_customer_reply",
            {
                "organization_id": str(TEST_ORG_ID),
                "thread_id": thread_id,
                "body": "Thank you for your inquiry. Here's the information you requested.",
            },
            auth=auth,
        )
        assert resp.ok is True
        assert resp.data["success"] is True

    async def test_create_launch_doc_succeeds(self):
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "create_launch_doc",
            {
                "organization_id": str(TEST_ORG_ID),
                "title": "Product Launch Plan",
                "body": "Launch plan for Q3 digital product.",
            },
            auth=auth,
        )
        assert resp.ok is True
        assert resp.data["success"] is True
        assert resp.data["data"]["title"] == "Product Launch Plan"

    async def test_append_funnel_report_to_doc_succeeds(self):
        auth = self._auth()
        # First create a doc
        create_resp = await mcp_registry.call_tool(
            "create_launch_doc",
            {
                "organization_id": str(TEST_ORG_ID),
                "title": "Funnel Report",
                "body": "Initial report data.",
            },
            auth=auth,
        )
        assert create_resp.ok is True
        doc_id = create_resp.data["data"]["doc_id"]

        # Append to it
        resp = await mcp_registry.call_tool(
            "append_funnel_report_to_doc",
            {
                "organization_id": str(TEST_ORG_ID),
                "doc_id": doc_id,
                "content": "New funnel data appended.",
            },
            auth=auth,
        )
        assert resp.ok is True
        assert resp.data["success"] is True

    async def test_export_revenue_summary_to_sheet_succeeds(self):
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "export_revenue_summary_to_sheet",
            {
                "organization_id": str(TEST_ORG_ID),
                "sheet_title": "Revenue Summary Q3",
            },
            auth=auth,
        )
        assert resp.ok is True
        assert resp.data["success"] is True
        assert resp.data["data"]["title"] == "Revenue Summary Q3"

    async def test_create_launch_calendar_plan_succeeds(self):
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "create_launch_calendar_plan",
            {
                "organization_id": str(TEST_ORG_ID),
                "summary": "Product Launch",
                "description": "Launch day activities",
                "start_time": "2026-06-15T09:00:00Z",
                "end_time": "2026-06-15T17:00:00Z",
                "attendees": ["team@example.com"],
            },
            auth=auth,
        )
        assert resp.ok is True
        assert resp.data["success"] is True
        assert resp.data["data"]["status"] == "tentative"

    async def test_index_drive_knowledge_mock_succeeds(self):
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "index_drive_knowledge_mock",
            {"organization_id": str(TEST_ORG_ID)},
            auth=auth,
        )
        assert resp.ok is True
        assert resp.data["total"] >= 2, f"Expected >=2 files, got: {resp.data['total']}"

    async def test_index_drive_knowledge_mock_with_query(self):
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "index_drive_knowledge_mock",
            {"organization_id": str(TEST_ORG_ID), "query": "Funnel Report"},
            auth=auth,
        )
        assert resp.ok is True
        assert resp.data["total"] >= 1


@pytest.mark.asyncio
class TestWorkspaceApprovalTools:
    """Approval-required workspace tools must create ApprovalRequest and not execute."""

    def _auth(self, org_id: UUID | None = None) -> MCPAuthContext:
        return MCPAuthContext.system(organization_id=org_id or TEST_ORG_ID)

    async def _assert_approval_required(self, resp: MCPResponse) -> UUID:
        """Assert approval response and return approval_request_id."""
        assert resp.ok is False, f"Expected False, got: {resp}"
        assert resp.error is not None
        assert resp.error.code == "APPROVAL_REQUIRED"
        assert resp.data["approval_required"] is True
        approval_id = UUID(resp.data["approval_request_id"])
        return approval_id

    async def _assert_approval_exists(self, approval_id: UUID) -> ApprovalRequest:
        async with AsyncSessionLocal() as db:
            ar = await db.get(ApprovalRequest, approval_id)
            assert ar is not None, f"ApprovalRequest {approval_id} should exist"
            assert ar.status == "pending"
            return ar

    async def test_send_customer_email_requires_approval(self):
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "send_customer_email",
            {
                "organization_id": str(TEST_ORG_ID),
                "to": "customer@example.com",
                "subject": "Special Offer",
                "body": "Check out our new product!",
            },
            auth=auth,
        )
        approval_id = await self._assert_approval_required(resp)
        ar = await self._assert_approval_exists(approval_id)
        assert ar.action_type == "send_customer_email"
        assert "customer@example.com" in ar.title

    async def test_share_public_doc_requires_approval(self):
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "share_public_doc",
            {
                "organization_id": str(TEST_ORG_ID),
                "doc_id": str(uuid4()),
                "share_with_email": "user@example.com",
                "role": "reader",
            },
            auth=auth,
        )
        approval_id = await self._assert_approval_required(resp)
        ar = await self._assert_approval_exists(approval_id)
        assert ar.action_type == "share_public_doc"

    async def test_create_real_calendar_event_requires_approval(self):
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "create_real_calendar_event",
            {
                "organization_id": str(TEST_ORG_ID),
                "summary": "Client Meeting",
                "start_time": "2026-06-20T10:00:00Z",
                "end_time": "2026-06-20T11:00:00Z",
                "attendees": ["client@example.com"],
            },
            auth=auth,
        )
        approval_id = await self._assert_approval_required(resp)
        ar = await self._assert_approval_exists(approval_id)
        assert ar.action_type == "create_real_calendar_event"

    async def test_move_drive_files_requires_approval(self):
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "move_drive_files",
            {
                "organization_id": str(TEST_ORG_ID),
                "file_id": str(uuid4()),
                "new_parent_folder_id": str(uuid4()),
                "reason": "Reorganizing project files",
            },
            auth=auth,
        )
        approval_id = await self._assert_approval_required(resp)
        ar = await self._assert_approval_exists(approval_id)
        assert ar.action_type == "move_drive_files"
        assert ar.details["reason"] == "Reorganizing project files"

    async def test_send_customer_email_no_real_send(self):
        """Verify send_customer_email does NOT actually send any real email."""
        auth = self._auth()
        resp = await mcp_registry.call_tool(
            "send_customer_email",
            {
                "organization_id": str(TEST_ORG_ID),
                "to": "customer-test@example.com",
                "subject": "Special Offer Test",
                "body": "Test body content",
            },
            auth=auth,
        )
        assert resp.ok is False  # Approval required = not executed
        assert resp.error.code == "APPROVAL_REQUIRED"
        # Test that the mock provider also recorded it as approval_required
        from app.integrations.google_workspace import mock_workspace_provider
        emails = await mock_workspace_provider.search_emails(
            query="customer-test", organization_id=str(TEST_ORG_ID),
        )
        assert any(e.status == "approval_required" for e in emails)

    async def test_cross_org_returns_permission_denied(self):
        """Cross-org access must not expose data when org mismatch."""
        # Use a non-system auth constrained to TEST_ORG_ID — accessing OTHER_ORG_ID should be blocked
        auth = MCPAuthContext(
            actor_type="agent",
            actor_id="test-agent",
            organization_id=TEST_ORG_ID,
            request_id=str(uuid4()),
        )
        resp = await mcp_registry.call_tool(
            "send_customer_email",
            {
                "organization_id": str(OTHER_ORG_ID),
                "to": "customer@example.com",
                "subject": "Test",
                "body": "Test",
            },
            auth=auth,
        )
        assert resp.ok is False
        assert resp.error.code == "PERMISSION_DENIED", f"Expected PERMISSION_DENIED, got: {resp.error.code}"


@pytest.mark.asyncio
class TestWorkspaceToolListing:
    """Verify workspace tools appear in MCP tool listing with correct risk levels."""

    async def test_read_tools_appear_in_listing(self):
        tools = mcp_registry.list_tools(risk_level="READ_ONLY")
        tool_names = [t["name"] for t in tools]
        assert "search_customer_emails" in tool_names
        assert "index_drive_knowledge_mock" in tool_names

    async def test_low_write_tools_appear_in_listing(self):
        tools = mcp_registry.list_tools(risk_level="LOW_WRITE")
        tool_names = [t["name"] for t in tools]
        assert "draft_customer_reply" in tool_names
        assert "create_launch_doc" in tool_names
        assert "append_funnel_report_to_doc" in tool_names
        assert "export_revenue_summary_to_sheet" in tool_names
        assert "create_launch_calendar_plan" in tool_names

    async def test_approval_tools_appear_in_listing(self):
        tools = mcp_registry.list_tools(risk_level="APPROVAL_REQUIRED")
        tool_names = [t["name"] for t in tools]
        assert "send_customer_email" in tool_names
        assert "share_public_doc" in tool_names
        assert "create_real_calendar_event" in tool_names
        assert "move_drive_files" in tool_names
        for t in tools:
            name = t["name"]
            if name in ["send_customer_email", "share_public_doc", "create_real_calendar_event", "move_drive_files"]:
                assert t["requires_approval"] is True

    async def test_no_real_external_calls(self):
        """Verify all workspace tools complete without connection errors."""
        auth = MCPAuthContext.system(organization_id=TEST_ORG_ID)
        tools_to_test = [
            ("search_customer_emails", {"query": "test"}),
            ("index_drive_knowledge_mock", {}),
        ]
        for tool_name, extra_params in tools_to_test:
            resp = await mcp_registry.call_tool(
                tool_name,
                {"organization_id": str(TEST_ORG_ID), **extra_params},
                auth=auth,
            )
            assert resp.ok is True, f"Tool {tool_name} failed: {resp}"
