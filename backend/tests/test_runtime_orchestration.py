from __future__ import annotations

from uuid import UUID

import pytest
import pytest_asyncio

from app.agent_workflows.state import workflow_store
from app.database import AsyncSessionLocal
from app.mcp.schemas import MCPAuthContext
from app.models.organization import Organization
from app.runtime.orchestration import (
    QueueDispatchReceipt,
    RuntimeOrchestrationService,
    RuntimeWorkflowDispatcher,
    workflow_trace_store,
)

TEST_ORG = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def _clear_runtime_state():
    workflow_store.clear()
    workflow_trace_store.clear()


@pytest_asyncio.fixture(autouse=True)
async def _seed_org():
    async with AsyncSessionLocal() as db:
        org_id = UUID(TEST_ORG)
        existing = await db.get(Organization, org_id)
        if existing is None:
            db.add(
                Organization(
                    id=org_id,
                    name="Runtime Workflow Org",
                    slug="runtime-workflow-org",
                    status="active",
                )
            )
            await db.commit()


@pytest.fixture
def auth() -> MCPAuthContext:
    return MCPAuthContext.system(organization_id=UUID(TEST_ORG))


def test_runtime_orchestration_lists_expected_workflows():
    service = RuntimeOrchestrationService()
    names = [item["workflow_name"] for item in service.list_workflows()]
    assert "daily_funnel_brief" in names
    assert "lead_followup_draft" in names
    assert "checkout_abandonment_monitor" in names
    assert "delivery_failure_monitor" in names
    assert "weekly_revenue_review" in names
    assert "token_benchmark_review" in names


@pytest.mark.asyncio
async def test_local_workflow_run_preserves_trace_context(auth: MCPAuthContext):
    service = RuntimeOrchestrationService()
    workflow = await service.run_workflow(
        workflow_name="daily_funnel_brief",
        organization_id=TEST_ORG,
        inputs={"date_range": "today"},
        auth_ctx=auth,
        correlation_id="corr-runtime-1",
        business_event_id="evt-123",
        context_packet_id="ctx-456",
    )
    traces = service.list_traces(organization_id=TEST_ORG, correlation_id="corr-runtime-1")

    assert workflow.workflow_name == "daily_funnel_brief"
    assert workflow.business_event_id == "evt-123"
    assert workflow.context_packet_id == "ctx-456"
    assert len(traces) == 1
    assert traces[0].workflow.workflow_run_id == workflow.workflow_run_id
    assert traces[0].business_event_id == "evt-123"
    assert traces[0].context_packet_id == "ctx-456"
    assert traces[0].execution_mode == "local"


@pytest.mark.asyncio
async def test_queue_mode_dispatches_without_local_execution(auth: MCPAuthContext):
    seen: list[tuple[str, str, str | None, str | None]] = []

    async def fake_queue_executor(request):
        seen.append(
            (
                request.workflow_name,
                request.correlation_id,
                request.business_event_id,
                request.context_packet_id,
            )
        )
        return QueueDispatchReceipt(workflow_run_id="wf_queue_1234", status="queued")

    service = RuntimeOrchestrationService(
        execution_mode="queue",
        queue_enabled=True,
        dispatcher=RuntimeWorkflowDispatcher(queue_executor=fake_queue_executor),
    )
    workflow = await service.run_workflow(
        workflow_name="weekly_revenue_review",
        organization_id=TEST_ORG,
        inputs={},
        auth_ctx=auth,
        correlation_id="corr-runtime-queue",
        business_event_id="evt-q",
        context_packet_id="ctx-q",
    )

    assert workflow.workflow_run_id == "wf_queue_1234"
    assert workflow.status == "pending"
    assert seen == [("weekly_revenue_review", "corr-runtime-queue", "evt-q", "ctx-q")]
    traces = service.list_traces(correlation_id="corr-runtime-queue")
    assert traces[0].execution_mode == "queue"


@pytest.mark.asyncio
async def test_placeholder_workflow_creates_local_boundary_trace(auth: MCPAuthContext):
    service = RuntimeOrchestrationService()
    workflow = await service.run_workflow(
        workflow_name="checkout_abandonment_monitor",
        organization_id=TEST_ORG,
        inputs={},
        auth_ctx=auth,
        correlation_id="corr-runtime-placeholder",
        business_event_id=None,
        context_packet_id=None,
    )

    assert workflow.workflow_name == "checkout_abandonment_monitor"
    assert workflow.status == "completed"
    fetched = service.get_workflow_run(workflow.workflow_run_id, TEST_ORG)
    assert fetched.workflow_run_id == workflow.workflow_run_id


@pytest.mark.asyncio
async def test_alias_workflow_routes_to_existing_engine(auth: MCPAuthContext):
    service = RuntimeOrchestrationService()
    workflow = await service.run_workflow(
        workflow_name="lead_followup_draft",
        organization_id=TEST_ORG,
        inputs={},
        auth_ctx=auth,
        correlation_id="corr-runtime-alias",
        business_event_id="evt-alias",
        context_packet_id=None,
    )

    assert workflow.workflow_name == "lead_followup_draft"
    traces = service.list_traces(correlation_id="corr-runtime-alias")
    assert traces[0].metadata["backend_workflow_type"] == "customer_inbox_triage"
