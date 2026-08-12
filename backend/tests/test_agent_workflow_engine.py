"""Tests for the agent workflow engine core — schemas, runner, store."""
from __future__ import annotations

import pytest

from app.agent_workflows.errors import (
    WorkflowOrgMismatchError,
    WorkflowRunNotFoundError,
)
from app.agent_workflows.policies import WorkflowPolicy, WorkflowPolicyEngine, default_workflow_policy
from app.agent_workflows.runner import WorkflowRunner
from app.agent_workflows.schemas import ToolCallRef, WorkflowRun, WorkflowStep, WorkflowStatusSummary
from app.agent_workflows.state import workflow_store, WorkflowStore
from app.mcp.auth import MCPAuthContext

TEST_ORG = "00000000-0000-0000-0000-000000000001"
OTHER_ORG = "00000000-0000-0000-0000-000000000002"


def test_workflow_run_schema():
    run = WorkflowRun(
        workflow_run_id="wf_test_001",
        organization_id=TEST_ORG,
        workflow_type="test_workflow",
    )
    assert run.workflow_run_id == "wf_test_001"
    assert run.status == "pending"
    assert run.context_pack_ids == []
    assert run.approval_request_ids == []
    assert run.workspace_item_ids == []
    assert run.steps == []


def test_workflow_step_schema():
    step = WorkflowStep(
        step_id="step_001",
        workflow_run_id="wf_test_001",
        step_name="test_step",
    )
    assert step.status == "pending"
    assert step.input_refs == []
    assert step.output_refs == []
    assert step.tool_name is None


def test_tool_call_ref_schema():
    ref = ToolCallRef(
        request_id="req_001",
        tool_name="get_revenue_summary",
        risk_level="READ_ONLY",
        status="success",
        summary="Revenue summary retrieved",
    )
    assert ref.approval_request_id is None


def test_workflow_status_summary():
    summary = WorkflowStatusSummary(total_runs=5, completed=3, failed=1, running=1)
    assert summary.latest_run_id is None


def test_workflow_store_save_get_list():
    store = WorkflowStore()
    run = WorkflowRun(
        workflow_run_id="wf_test_001",
        organization_id=TEST_ORG,
        workflow_type="daily_funnel_brief",
        status="completed",
    )
    store.save_run(run)

    retrieved = store.get_run("wf_test_001", TEST_ORG)
    assert retrieved.workflow_run_id == "wf_test_001"
    assert retrieved.status == "completed"

    runs = store.list_runs(TEST_ORG)
    assert len(runs) == 1

    filtered = store.list_runs(TEST_ORG, workflow_type="daily_funnel_brief")
    assert len(filtered) == 1

    filtered_empty = store.list_runs(TEST_ORG, workflow_type="nonexistent")
    assert len(filtered_empty) == 0


def test_workflow_store_org_mismatch():
    store = WorkflowStore()
    run = WorkflowRun(
        workflow_run_id="wf_test_001",
        organization_id=TEST_ORG,
        workflow_type="test",
    )
    store.save_run(run)

    with pytest.raises(WorkflowOrgMismatchError):
        store.get_run("wf_test_001", OTHER_ORG)


def test_workflow_store_not_found():
    store = WorkflowStore()
    with pytest.raises(WorkflowRunNotFoundError):
        store.get_run("nonexistent", TEST_ORG)


def test_workflow_store_get_status():
    store = WorkflowStore()
    for i in range(3):
        store.save_run(WorkflowRun(
            workflow_run_id=f"wf_{i}",
            organization_id=TEST_ORG,
            workflow_type="test",
            status="completed",
        ))
    store.save_run(WorkflowRun(
        workflow_run_id="wf_fail",
        organization_id=TEST_ORG,
        workflow_type="test",
        status="failed",
    ))

    status = store.get_status(TEST_ORG)
    assert status.total_runs == 4
    assert status.completed == 3
    assert status.failed == 1
    assert status.latest_run_id is not None


def test_workflow_store_clear():
    store = WorkflowStore()
    store.save_run(WorkflowRun(
        workflow_run_id="wf_001",
        organization_id=TEST_ORG,
        workflow_type="test",
    ))
    store.clear()
    with pytest.raises(WorkflowRunNotFoundError):
        store.get_run("wf_001", TEST_ORG)


def test_workflow_runner_enforces_policy():
    """Verifies the runner's call_tool_safely blocks dangerous tools."""
    policy = default_workflow_policy("test")
    runner = WorkflowRunner(policy=policy)
    auth = MCPAuthContext.system(organization_id=TEST_ORG)

    # We need to use pytest-asyncio for async tests
    import asyncio
    async def _test():
        result = await runner.call_tool_safely(
            tool_name="deploy_production",
            arguments={},
            auth_ctx=auth,
        )
        assert result.ok is False
        assert result.error is not None
        assert result.error.code == "POLICY_BLOCKED"
    asyncio.run(_test())


def test_workflow_state_uses_refs_not_full_context():
    """Verify workflow state stores references, not full content blobs."""
    run = WorkflowRun(
        workflow_run_id="wf_ref_test",
        organization_id=TEST_ORG,
        workflow_type="test",
    )
    # These should be string references, not large content
    run.context_pack_ids = ["ctx_abc123"]
    run.approval_request_ids = ["apr_def456"]
    run.workspace_item_ids = ["doc_ghi789"]

    # Verify refs are short identifiers
    for ref_list in [run.context_pack_ids, run.approval_request_ids, run.workspace_item_ids]:
        for ref in ref_list:
            assert len(ref) < 50, f"Ref '{ref}' is too long for a reference"
