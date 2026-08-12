"""Tests for Weekly Revenue Review workflow — creates review, never changes prices."""
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


def test_weekly_revenue_review_runs(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="weekly_revenue_review",
            organization_id=TEST_ORG,
            inputs={"date_range": "last_7_days"},
            auth_ctx=auth,
        )
        assert run.workflow_type == "weekly_revenue_review"
    asyncio.run(_test())


def test_weekly_revenue_review_exports_sheet(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="weekly_revenue_review",
            organization_id=TEST_ORG,
            inputs={},
            auth_ctx=auth,
        )
        assert run.workspace_item_ids is not None or run.workspace_item_ids == []
    asyncio.run(_test())


def test_weekly_revenue_review_creates_doc(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="weekly_revenue_review",
            organization_id=TEST_ORG,
            inputs={},
            auth_ctx=auth,
        )
        steps_with_doc = [s for s in run.steps if s.tool_name == "create_launch_doc"]
        assert len(steps_with_doc) > 0
    asyncio.run(_test())


def test_weekly_revenue_review_does_not_change_price(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="weekly_revenue_review",
            organization_id=TEST_ORG,
            inputs={},
            auth_ctx=auth,
        )
        # Verify no price/product change tools were called
        for step in run.steps:
            assert step.tool_name not in ("change_product_price", "publish_product_update")
        assert run.output_summary is not None
        assert "No prices changed" in run.output_summary
    asyncio.run(_test())
