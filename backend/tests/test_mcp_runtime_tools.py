"""Tests for MCP runtime-aligned tools."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from app.database import AsyncSessionLocal
from app.models.approval_request import ApprovalRequest
from app.models.organization import Organization
from app.mcp.schemas import MCPAuthContext
from app.runtime.contracts import TaskEnvelope
from app.runtime.events import business_event_service
from app.mcp.tools.runtime import (
    _get_gateway_service,
    _reset_runtime_services_for_tests,
    handle_build_runtime_context_packet,
    handle_get_business_event,
    handle_get_runtime_status,
    handle_get_runtime_task,
    handle_get_token_roi_summary,
    handle_list_business_events,
    handle_list_dead_letters,
    handle_list_runtime_tasks,
    handle_request_dead_letter_requeue,
    handle_run_safe_workflow,
)

TEST_ORG_ID = UUID("00000000-0000-0000-0000-000000000001")
TEST_AUTH = MCPAuthContext.system(organization_id=TEST_ORG_ID)


def _task(**overrides: object) -> TaskEnvelope:
    return TaskEnvelope(
        organizationId=TEST_ORG_ID,
        correlationId=str(overrides.pop("correlationId", f"corr-{uuid4().hex[:8]}")),
        source="mcp-runtime-test",
        target=overrides.pop("target", "workflow"),
        taskType=overrides.pop("taskType", "daily_funnel_brief"),
        priority=overrides.pop("priority", "normal"),
        status=overrides.pop("status", "pending"),
        payload=overrides.pop("payload", {}),
        **overrides,
    )


@pytest_asyncio.fixture(autouse=True)
async def _setup_runtime_tools():
    _reset_runtime_services_for_tests()
    async with AsyncSessionLocal() as db:
        existing = await db.get(Organization, TEST_ORG_ID)
        if existing is None:
            db.add(
                Organization(
                    id=TEST_ORG_ID,
                    name="Runtime Test Org",
                    slug="runtime-test-org",
                    status="active",
                )
            )
            await db.commit()
        approvals = await db.execute(
            ApprovalRequest.__table__.delete().where(
                ApprovalRequest.organization_id == TEST_ORG_ID
            )
        )
        await db.commit()
    yield
    _reset_runtime_services_for_tests()


@pytest.mark.asyncio
async def test_get_runtime_status_reports_runtime_surfaces() -> None:
    response = await handle_get_runtime_status(
        auth=TEST_AUTH,
        organization_id=str(TEST_ORG_ID),
    )

    assert response.ok is True
    assert response.data["worker_capability_count"] == 6
    assert "draft_customer_reply" in response.data["worker_capabilities"]


@pytest.mark.asyncio
async def test_list_and_get_runtime_task_tools() -> None:
    gateway = _get_gateway_service()
    dispatch = await gateway.dispatch_task(_task())

    list_response = await handle_list_runtime_tasks(
        auth=TEST_AUTH,
        organization_id=str(TEST_ORG_ID),
    )
    get_response = await handle_get_runtime_task(
        auth=TEST_AUTH,
        organization_id=str(TEST_ORG_ID),
        task_id=str(dispatch.task_id),
    )

    assert list_response.ok is True
    assert list_response.data["total"] == 1
    assert list_response.data["items"][0]["task_id"] == str(dispatch.task_id)

    assert get_response.ok is True
    assert get_response.data["task"]["task_id"] == str(dispatch.task_id)
    assert get_response.data["task"]["status"] == "completed"


@pytest.mark.asyncio
async def test_list_and_get_business_events() -> None:
    event = await business_event_service.emit(
        organization_id=str(TEST_ORG_ID),
        event_type="workflow.completed",
        subject_type="workflow_run",
        subject_id="wf-123",
        payload={"summary": "done"},
        source="runtime-test",
        correlation_id="corr-event-1",
    )

    list_response = await handle_list_business_events(
        auth=TEST_AUTH,
        organization_id=str(TEST_ORG_ID),
    )
    get_response = await handle_get_business_event(
        auth=TEST_AUTH,
        organization_id=str(TEST_ORG_ID),
        event_id=str(event.event_id),
    )

    assert list_response.ok is True
    assert list_response.data["total"] >= 1
    assert list_response.data["items"][0]["event_id"] == str(event.event_id)

    assert get_response.ok is True
    assert get_response.data["event"]["event_id"] == str(event.event_id)
    assert get_response.data["event"]["event_type"] == "workflow.completed"


@pytest.mark.asyncio
async def test_build_runtime_context_packet_and_token_roi_summary() -> None:
    context_response = await handle_build_runtime_context_packet(
        auth=TEST_AUTH,
        organization_id=str(TEST_ORG_ID),
        task_type="runtime_review",
        goal="inspect runtime bridges safely",
        token_budget=1500,
    )
    roi_response = await handle_get_token_roi_summary(
        auth=TEST_AUTH,
        organization_id=str(TEST_ORG_ID),
        tokens_saved=2000,
        retry_count=1,
        retry_token_cost=150,
        human_correction_count=1,
        human_correction_cost=200,
        quality_gate_passed=True,
        critical_context_lost=False,
    )

    assert context_response.ok is True
    assert context_response.data["context_pack_id"] != ""
    assert context_response.data["task_type"] == "runtime_review"

    assert roi_response.ok is True
    assert roi_response.data["profitable"] is True
    assert roi_response.data["net_roi"] == 1650


@pytest.mark.asyncio
async def test_request_dead_letter_requeue_creates_approval_request() -> None:
    gateway = _get_gateway_service()
    await gateway.dispatch_task(
        _task(payload={"force_failure": True}, taskType="replay_candidate")
    )
    dead_letters = await gateway.list_dead_letters()
    assert len(dead_letters) == 1

    response = await handle_request_dead_letter_requeue(
        auth=TEST_AUTH,
        organization_id=str(TEST_ORG_ID),
        dead_letter_id=str(dead_letters[0].dead_letter_id),
    )

    assert response.ok is False
    assert response.error is not None
    assert response.error.code == "APPROVAL_REQUIRED"
    approval_id = UUID(response.data["approval_request_id"])
    async with AsyncSessionLocal() as db:
        approval = await db.get(ApprovalRequest, approval_id)
        assert approval is not None
        assert approval.action_type == "request_dead_letter_requeue"


@pytest.mark.asyncio
async def test_run_safe_workflow_runs_safe_and_blocks_approval_required() -> None:
    safe_response = await handle_run_safe_workflow(
        auth=TEST_AUTH,
        organization_id=str(TEST_ORG_ID),
        workflow_name="daily_funnel_brief",
        inputs={"date_range": "today"},
    )
    blocked_response = await handle_run_safe_workflow(
        auth=TEST_AUTH,
        organization_id=str(TEST_ORG_ID),
        workflow_name="lead_followup_draft",
        inputs={},
    )

    assert safe_response.ok is True
    assert safe_response.data["workflow_name"] == "daily_funnel_brief"

    assert blocked_response.ok is False
    assert blocked_response.error is not None
    assert blocked_response.error.code == "APPROVAL_REQUIRED"


@pytest.mark.asyncio
async def test_list_dead_letters_empty_state() -> None:
    response = await handle_list_dead_letters(
        auth=TEST_AUTH,
        organization_id=str(TEST_ORG_ID),
    )

    assert response.ok is True
    assert response.data["items"] == []
