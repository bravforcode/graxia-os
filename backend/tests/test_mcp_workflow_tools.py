"""Tests for MCP workflow tools — list, run, get, status, policy."""
from __future__ import annotations

import pytest
from uuid import UUID

from app.agent_workflows.service import WorkflowEngineService
from app.agent_workflows.state import workflow_store
from app.mcp.auth import MCPAuthContext
from app.mcp.schemas import MCPResponse
from app.mcp.tools.workflows import (
    handle_list_agent_workflows,
    handle_get_agent_workflow_status,
    handle_get_agent_workflow_policy,
)

TEST_ORG = "00000000-0000-0000-0000-000000000001"
OTHER_ORG = "00000000-0000-0000-0000-000000000002"


@pytest.fixture(autouse=True)
def _clear_store():
    workflow_store.clear()


def test_list_agent_workflows_tool():
    import asyncio
    async def _test():
        result = await handle_list_agent_workflows(
            organization_id=TEST_ORG,
        )
        assert result.ok is True
        assert result.data is not None
        items = result.data.get("items", [])
        assert len(items) >= 6  # At least 6 registered workflows
        types = [i["workflow_type"] for i in items]
        assert "daily_funnel_brief" in types
        assert "launch_plan_builder" in types
        assert "customer_inbox_triage" in types
        assert "token_benchmark_review" in types
        assert "delivery_failure_monitor" in types
        assert "weekly_revenue_review" in types
    asyncio.run(_test())


def test_run_agent_workflow_tool_daily_brief():
    import asyncio
    async def _test():
        from app.mcp.tools.workflows import handle_run_agent_workflow
        result = await handle_run_agent_workflow(
            organization_id=TEST_ORG,
            workflow_type="daily_funnel_brief",
            inputs={"date_range": "today"},
        )
        assert result.ok is True
        assert result.data is not None
        data = result.data
        assert data["workflow_type"] == "daily_funnel_brief"
        assert len(data["workspace_item_ids"]) >= 0
    asyncio.run(_test())


def test_run_agent_workflow_tool_launch_plan():
    import asyncio
    async def _test():
        from app.mcp.tools.workflows import handle_run_agent_workflow
        result = await handle_run_agent_workflow(
            organization_id=TEST_ORG,
            workflow_type="launch_plan_builder",
            inputs={"product_name": "Test Course", "offer_price": "$97"},
        )
        assert result.ok is True
        assert result.data is not None
        assert result.data["workflow_type"] == "launch_plan_builder"
    asyncio.run(_test())


def test_get_agent_workflow_status_tool():
    import asyncio
    async def _test():
        # First run a workflow
        from app.mcp.tools.workflows import handle_run_agent_workflow
        await handle_run_agent_workflow(
            organization_id=TEST_ORG,
            workflow_type="daily_funnel_brief",
            inputs={},
        )
        # Then check status
        result = await handle_get_agent_workflow_status(
            organization_id=TEST_ORG,
        )
        assert result.ok is True
        assert result.data is not None
        assert result.data["total_runs"] >= 1
    asyncio.run(_test())


def test_get_agent_workflow_policy_tool():
    import asyncio
    async def _test():
        result = await handle_get_agent_workflow_policy(
            organization_id=TEST_ORG,
            workflow_type="daily_funnel_brief",
        )
        assert result.ok is True
        assert result.data is not None
        assert result.data["workflow_type"] == "daily_funnel_brief"
        assert result.data["allow_real_external_calls"] is False
        assert result.data["allow_customer_send"] is False
        assert result.data["allow_publish"] is False
    asyncio.run(_test())


def test_run_unknown_workflow_fails_safely():
    import asyncio
    async def _test():
        from app.mcp.tools.workflows import handle_run_agent_workflow
        result = await handle_run_agent_workflow(
            organization_id=TEST_ORG,
            workflow_type="nonexistent_workflow",
            inputs={},
        )
        assert result.ok is False
        assert result.error is not None
        assert result.error.code == "WORKFLOW_NOT_FOUND"
    asyncio.run(_test())


def test_workflow_tools_require_org_context():
    """Tools require organization_id to function."""
    import asyncio
    async def _test():
        result = await handle_list_agent_workflows(
            organization_id="",
        )
        assert result.ok is False
    asyncio.run(_test())


def test_workflow_tool_cross_org_blocked():
    """Cross-org access is blocked — workflow for OTHER_ORG not accessible from TEST_ORG."""
    import asyncio
    async def _test():
        from app.mcp.tools.workflows import handle_get_agent_workflow_status
        # Run a workflow under TEST_ORG first
        from app.mcp.tools.workflows import handle_run_agent_workflow
        await handle_run_agent_workflow(
            organization_id=TEST_ORG,
            workflow_type="daily_funnel_brief",
            inputs={},
        )
        # Check status for OTHER_ORG — should see 0 runs (isolated store)
        result = await handle_get_agent_workflow_status(
            organization_id=OTHER_ORG,
        )
        assert result.ok is True
        assert result.data is not None
        assert result.data["total_runs"] == 0
    asyncio.run(_test())
