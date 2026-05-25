import uuid
from datetime import UTC, datetime

from app.mcp.schemas import VALID_RISK_LEVELS
from app.models.approval_request import ApprovalRequest
from app.runtime.contracts import (
    CURRENT_RUNTIME_SCHEMA_VERSION,
    ApprovalContract,
    AuditEvent,
    BusinessEvent,
    CompressionMode,
    ContextPacketRef,
    QualityGateStatus,
    ReadinessCheck,
    ReadinessLevel,
    ReadinessStatus,
    RiskLevel,
    TaskEnvelope,
    TaskTarget,
    ToolCallResult,
    ToolCallResultMeta,
    WorkflowRunRef,
    WorkflowRunStatus,
)


def _org_id() -> uuid.UUID:
    return uuid.uuid4()


def test_business_event_accepts_camel_case_and_defaults_schema_version():
    event = BusinessEvent.model_validate(
        {
            "organizationId": str(_org_id()),
            "correlationId": "corr-123",
            "source": "graxia-api",
            "eventType": "checkout.started",
            "actorType": "customer",
            "subjectType": "checkout_session",
            "subjectId": "chk_123",
            "riskLevel": "READ_ONLY",
            "payload": {"step": "open"},
        }
    )

    assert event.schema_version == CURRENT_RUNTIME_SCHEMA_VERSION
    assert event.redaction.contains_secrets is False
    dumped = event.model_dump(by_alias=True)
    assert dumped["schemaVersion"] == CURRENT_RUNTIME_SCHEMA_VERSION
    assert dumped["organizationId"]
    assert dumped["riskLevel"] == "READ_ONLY"


def test_task_envelope_uses_runtime_base_fields_and_aliases():
    task = TaskEnvelope.model_validate(
        {
            "organization_id": _org_id(),
            "correlation_id": "corr-task",
            "source": "runtime-gateway",
            "taskType": "draft_followup",
            "target": "workflow",
            "payload": {"lead_id": "lead-1"},
        }
    )

    assert task.target == TaskTarget.WORKFLOW
    assert task.status == "pending"
    assert task.priority == "normal"
    assert task.model_dump(by_alias=True)["taskType"] == "draft_followup"


def test_approval_contract_can_be_built_from_existing_model_shape():
    approval_request_id = uuid.uuid4()
    approval_model = ApprovalRequest(
        organization_id=_org_id(),
        title="Review launch email",
        action_type="send_email",
        subject_type="draft",
        subject_id=uuid.uuid4(),
        status="pending",
        policy_class="EMAIL_POLICY",
        requested_by="agent:worker",
        preview={"subject": "Launch"},
    )

    contract = ApprovalContract.model_validate(
        {
            "organizationId": approval_model.organization_id,
            "correlationId": "corr-approval",
            "createdAt": datetime.now(UTC).isoformat(),
            "source": "mcp",
            "approvalRequestId": approval_request_id,
            "actionType": approval_model.action_type,
            "subjectType": approval_model.subject_type,
            "subjectId": str(approval_model.subject_id),
            "status": approval_model.status,
            "requestedBy": approval_model.requested_by,
            "preview": approval_model.preview,
            "policyReason": approval_model.policy_class,
        }
    )

    assert contract.risk_level == "APPROVAL_REQUIRED"
    assert contract.subject_id == str(approval_model.subject_id)


def test_context_packet_ref_tracks_quality_gate_and_hashes():
    context_ref = ContextPacketRef.model_validate(
        {
            "organizationId": str(_org_id()),
            "correlationId": "corr-context",
            "createdAt": datetime.now(UTC).isoformat(),
            "source": "context-engine",
            "contextPacketId": "ctx-1",
            "taskType": "workflow_review",
            "goal": "Summarize checkout issue",
            "estimatedTokens": 512,
            "compressionMode": "compact",
            "qualityGateStatus": "passed",
            "fileHashes": {"backend/app/main.py": "abc123"},
            "policyVersion": "2026-05-26",
            "generatedAt": datetime.now(UTC).isoformat(),
        }
    )

    assert context_ref.compression_mode == CompressionMode.COMPACT
    assert context_ref.quality_gate_status == QualityGateStatus.PASSED
    assert context_ref.file_hashes["backend/app/main.py"] == "abc123"


def test_tool_call_result_meta_carries_redaction_and_approval_refs():
    result = ToolCallResult.model_validate(
        {
            "organizationId": str(_org_id()),
            "correlationId": "corr-tool",
            "createdAt": datetime.now(UTC).isoformat(),
            "source": "mcp",
            "requestId": "req-1",
            "toolName": "request_approval",
            "ok": True,
            "data": {"status": "queued"},
            "meta": {
                "riskLevel": "APPROVAL_REQUIRED",
                "contextPacketId": "ctx-1",
                "approvalRequestId": "apr-1",
                "redacted": True,
            },
        }
    )

    assert result.meta == ToolCallResultMeta(
        riskLevel=RiskLevel.APPROVAL_REQUIRED,
        contextPacketId="ctx-1",
        approvalRequestId="apr-1",
        redacted=True,
    )


def test_workflow_run_ref_and_readiness_status_round_trip():
    workflow = WorkflowRunRef.model_validate(
        {
            "organizationId": str(_org_id()),
            "correlationId": "corr-workflow",
            "createdAt": datetime.now(UTC).isoformat(),
            "source": "workflow-engine",
            "workflowRunId": "run-1",
            "workflowName": "daily_funnel_brief",
            "status": "running",
        }
    )
    readiness = ReadinessStatus.model_validate(
        {
            "organizationId": str(_org_id()),
            "correlationId": "corr-ready",
            "createdAt": datetime.now(UTC).isoformat(),
            "source": "readiness-gate",
            "name": "runtime-contracts",
            "ready": True,
            "level": "CONTRACT_READY",
            "checks": [
                {
                    "name": "runtime-contracts",
                    "ready": True,
                    "detail": "contracts import cleanly",
                    "evidence": ["pytest backend/tests/test_runtime_contracts.py -q"],
                }
            ],
            "blockers": [],
            "evidence": ["compileall passed"],
        }
    )

    assert workflow.status == WorkflowRunStatus.RUNNING
    assert readiness.level == ReadinessLevel.CONTRACT_READY
    assert readiness.checks == [
        ReadinessCheck(
            name="runtime-contracts",
            ready=True,
            detail="contracts import cleanly",
            evidence=["pytest backend/tests/test_runtime_contracts.py -q"],
        )
    ]


def test_audit_event_requires_redacted_payload():
    audit = AuditEvent.model_validate(
        {
            "organizationId": str(_org_id()),
            "correlationId": "corr-audit",
            "createdAt": datetime.now(UTC).isoformat(),
            "source": "approval-service",
            "auditEventId": str(uuid.uuid4()),
            "eventType": "approval.requested",
            "actorType": "agent",
            "actorId": "worker-1",
            "subjectType": "approval_request",
            "subjectId": "apr-1",
            "riskLevel": "APPROVAL_REQUIRED",
            "redactedPayload": {"preview": {"subject": "safe"}},
        }
    )

    assert audit.redacted_payload["preview"]["subject"] == "safe"


def test_runtime_risk_levels_match_mcp_foundation():
    assert {level.value for level in RiskLevel} == VALID_RISK_LEVELS
