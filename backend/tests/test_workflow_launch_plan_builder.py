"""Tests for Launch Plan Builder workflow — creates mock docs, never publishes."""
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


def test_launch_plan_builder_runs(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="launch_plan_builder",
            organization_id=TEST_ORG,
            inputs={"product_name": "Test Product", "offer_price": "$47"},
            auth_ctx=auth,
        )
        assert run.workflow_type == "launch_plan_builder"
    asyncio.run(_test())


def test_launch_plan_builder_creates_mock_doc(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="launch_plan_builder",
            organization_id=TEST_ORG,
            inputs={"product_name": "Test Course"},
            auth_ctx=auth,
        )
        assert run.workspace_item_ids is not None
    asyncio.run(_test())


def test_launch_plan_builder_does_not_publish(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="launch_plan_builder",
            organization_id=TEST_ORG,
            inputs={},
            auth_ctx=auth,
        )
        # Verify no publish-related tools were called
        for step in run.steps:
            assert step.tool_name not in ("deploy_production", "publish_product_update", "change_product_price")
    asyncio.run(_test())


def test_launch_plan_builder_returns_actions(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="launch_plan_builder",
            organization_id=TEST_ORG,
            inputs={},
            auth_ctx=auth,
        )
        assert run.output_summary is not None
        assert "No publishing" in run.output_summary
    asyncio.run(_test())
