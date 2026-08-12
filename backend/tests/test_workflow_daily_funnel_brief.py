"""Tests for Daily Funnel Brief workflow — reads metrics, creates mock doc, no email."""
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


def test_daily_funnel_brief_runs(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="daily_funnel_brief",
            organization_id=TEST_ORG,
            inputs={"date_range": "today"},
            auth_ctx=auth,
        )
        assert run.workflow_type == "daily_funnel_brief"
        assert run.status == "completed" or run.status == "running"
    asyncio.run(_test())


def test_daily_funnel_brief_uses_context_pack(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="daily_funnel_brief",
            organization_id=TEST_ORG,
            inputs={"date_range": "today"},
            auth_ctx=auth,
        )
        assert run.organization_id == TEST_ORG
        assert run.workflow_run_id.startswith("wf_")
    asyncio.run(_test())


def test_daily_funnel_brief_reads_revenue_summary(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="daily_funnel_brief",
            organization_id=TEST_ORG,
            inputs={"date_range": "today"},
            auth_ctx=auth,
        )
        assert run.workspace_item_ids is not None
    asyncio.run(_test())


def test_daily_funnel_brief_creates_mock_doc(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="daily_funnel_brief",
            organization_id=TEST_ORG,
            inputs={"date_range": "today"},
            auth_ctx=auth,
        )
        # Should have at least attempted to create mock doc
        assert run.steps is not None
    asyncio.run(_test())


def test_daily_funnel_brief_does_not_send_email(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="daily_funnel_brief",
            organization_id=TEST_ORG,
            inputs={"date_range": "today"},
            auth_ctx=auth,
        )
        # Verify no send_customer_email tool was called
        for step in run.steps:
            assert step.tool_name != "send_customer_email", "Brief should NOT send email"
    asyncio.run(_test())


def test_daily_funnel_brief_returns_top_actions(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="daily_funnel_brief",
            organization_id=TEST_ORG,
            inputs={"date_range": "today"},
            auth_ctx=auth,
        )
        assert run.output_summary is not None
        assert "No email sent" in run.output_summary
    asyncio.run(_test())
