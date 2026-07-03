"""Tests for Delivery Failure Monitor workflow — detects issues, never grants/revokes directly."""
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


def test_delivery_failure_monitor_runs(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="delivery_failure_monitor",
            organization_id=TEST_ORG,
            inputs={},
            auth_ctx=auth,
        )
        assert run.workflow_type == "delivery_failure_monitor"
    asyncio.run(_test())


def test_delivery_failure_monitor_reads_delivery_open_rate(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="delivery_failure_monitor",
            organization_id=TEST_ORG,
            inputs={},
            auth_ctx=auth,
        )
        steps_with_delivery = [s for s in run.steps if s.tool_name == "get_delivery_open_rate"]
        assert len(steps_with_delivery) > 0
    asyncio.run(_test())


def test_delivery_failure_monitor_does_not_grant_access_directly(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="delivery_failure_monitor",
            organization_id=TEST_ORG,
            inputs={},
            auth_ctx=auth,
        )
        # Verify no grant/revoke tools were called
        for step in run.steps:
            assert step.tool_name not in (
                "grant_delivery_access_manual",
                "revoke_delivery_access",
            )
    asyncio.run(_test())


def test_delivery_failure_monitor_returns_recommendations(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="delivery_failure_monitor",
            organization_id=TEST_ORG,
            inputs={},
            auth_ctx=auth,
        )
        assert run.output_summary is not None
        assert "No direct access grant" in run.output_summary
    asyncio.run(_test())
