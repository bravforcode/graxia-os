import uuid
from datetime import UTC, datetime

from app.agent_workflows.schemas import WorkflowRun
from app.context_engine.schemas import ContextPack, ContextPackFile
from app.mcp.schemas import MCPResponse
from app.models.approval_request import ApprovalRequest
from app.models.audit_log import AuditLog
from app.runtime.adapters import (
    approval_request_to_contract,
    audit_log_to_event,
    context_pack_to_ref,
    funnel_action_to_business_event,
    mcp_response_to_tool_result,
    readiness_payload_to_status,
    workflow_run_to_ref,
)


def _org_id() -> uuid.UUID:
    return uuid.uuid4()


def test_approval_request_to_contract_maps_existing_model():
    approval = ApprovalRequest(
        organization_id=_org_id(),
        title="Approve publish",
        action_type="publish",
        subject_type="product",
        subject_id=uuid.uuid4(),
        status="pending",
        policy_class="PUBLISH_POLICY",
        requested_by="agent:publisher",
        preview={"title": "Offer"},
        details={"channel": "public"},
        created_at=datetime.now(UTC),
    )
    approval.id = uuid.uuid4()

    contract = approval_request_to_contract(approval, correlation_id="corr-approval")

    assert contract.action_type == "publish"
    assert contract.policy_reason == "PUBLISH_POLICY"
    assert contract.execution_plan == {"channel": "public"}


def test_mcp_response_to_tool_result_maps_meta_and_error_state():
    response = MCPResponse.ok_response(
        data={"approvalRequestId": "apr-1", "status": "queued"},
        request_id="req-1",
        organization_id=str(_org_id()),
        estimated_tokens=123,
    )

    result = mcp_response_to_tool_result(
        response,
        tool_name="request_approval",
        correlation_id="corr-tool",
        risk_level="APPROVAL_REQUIRED",
    )

    assert result.meta.approval_request_id == "apr-1"
    assert result.meta.estimated_tokens == 123
    assert result.tool_name == "request_approval"


def test_workflow_run_to_ref_extracts_metadata_and_context():
    run = WorkflowRun(
        workflow_run_id="wf_1",
        organization_id=str(_org_id()),
        workflow_type="daily_funnel_brief",
        status="running",
        actor_type="system",
        started_at=datetime.now(UTC).isoformat(),
        context_pack_ids=["ctx-1"],
        metadata={"business_event_id": "evt-1"},
    )

    ref = workflow_run_to_ref(run, correlation_id="corr-workflow")

    assert ref.workflow_run_id == "wf_1"
    assert ref.business_event_id == "evt-1"
    assert ref.context_packet_id == "ctx-1"


def test_context_pack_to_ref_maps_file_hashes():
    pack = ContextPack(
        context_pack_id="ctx-1",
        task_type="review",
        goal="Investigate approval flow",
        estimated_tokens=321,
        generated_at=datetime.now(UTC).isoformat(),
        included_files=[
            ContextPackFile(
                path="backend/app/api/approvals.py",
                sha256="abc123",
                estimated_tokens=100,
            )
        ],
    )

    ref = context_pack_to_ref(
        pack,
        organization_id=_org_id(),
        correlation_id="corr-context",
    )

    assert ref.file_hashes == {"backend/app/api/approvals.py": "abc123"}
    assert ref.estimated_tokens == 321


def test_funnel_action_to_business_event_preserves_ids_and_risk():
    event = funnel_action_to_business_event(
        organization_id=str(_org_id()),
        correlation_id="corr-funnel",
        event_type="checkout.started",
        subject_type="checkout_session",
        subject_id="chk_1",
        payload={"product_id": "prod_1"},
        actor_type="customer",
        risk_level="READ_ONLY",
        idempotency_key="idem-1",
    )

    assert event.event_type == "checkout.started"
    assert event.idempotency_key == "idem-1"
    assert event.payload["product_id"] == "prod_1"


def test_audit_log_to_event_redacts_sensitive_metadata():
    audit = AuditLog(
        organization_id=_org_id(),
        action="send_customer_email",
        details="queued",
        metadata_json={
            "actor_type": "agent",
            "actor_id": "worker-1",
            "risk_level": "APPROVAL_REQUIRED",
            "token": "secret-token",
        },
        created_at=datetime.now(UTC),
    )
    audit.id = uuid.uuid4()

    event = audit_log_to_event(audit, correlation_id="corr-audit")

    assert event.risk_level == "APPROVAL_REQUIRED"
    assert event.redacted_payload["metadata"]["token"] == "[REDACTED]"


def test_readiness_payload_to_status_builds_checks_and_blockers():
    status = readiness_payload_to_status(
        {
            "status": "degraded",
            "service": "Graxia OS API",
            "readiness": {
                "database": {"ready": True, "status": "ok"},
                "queue": {"ready": False, "status": "down"},
            },
        },
        organization_id=str(_org_id()),
        correlation_id="corr-ready",
    )

    assert status.ready is False
    assert status.blockers == ["queue"]
    assert len(status.checks) == 2
