"""Tests for Customer Inbox Triage workflow — classifies, drafts, never sends."""
from __future__ import annotations

import pytest

from app.agent_workflows.service import WorkflowEngineService
from app.agent_workflows.state import workflow_store
from app.mcp.auth import MCPAuthContext

TEST_ORG = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def _clear_store():
    workflow_store.clear()


@pytest.fixture
def service() -> WorkflowEngineService:
    return WorkflowEngineService()


@pytest.fixture
def auth() -> MCPAuthContext:
    return MCPAuthContext.system(organization_id=TEST_ORG)


def test_customer_inbox_triage_runs(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="customer_inbox_triage",
            organization_id=TEST_ORG,
            inputs={},
            auth_ctx=auth,
        )
        assert run.workflow_type == "customer_inbox_triage"
    asyncio.run(_test())


def test_customer_inbox_triage_searches_mock_emails(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="customer_inbox_triage",
            organization_id=TEST_ORG,
            inputs={},
            auth_ctx=auth,
        )
        steps_with_search = [s for s in run.steps if s.tool_name == "search_customer_emails"]
        assert len(steps_with_search) > 0
    asyncio.run(_test())


def test_customer_inbox_triage_drafts_replies(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="customer_inbox_triage",
            organization_id=TEST_ORG,
            inputs={},
            auth_ctx=auth,
        )
        steps_with_draft = [s for s in run.steps if s.tool_name == "draft_customer_reply"]
        assert len(steps_with_draft) > 0
    asyncio.run(_test())


def test_customer_inbox_triage_creates_send_approvals(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="customer_inbox_triage",
            organization_id=TEST_ORG,
            inputs={},
            auth_ctx=auth,
        )
        assert run.approval_request_ids is not None
    asyncio.run(_test())


def test_customer_inbox_triage_never_sends_email_directly(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="customer_inbox_triage",
            organization_id=TEST_ORG,
            inputs={},
            auth_ctx=auth,
        )
        output = run.output_summary or ""
        assert "No email sent" in output
    asyncio.run(_test())
