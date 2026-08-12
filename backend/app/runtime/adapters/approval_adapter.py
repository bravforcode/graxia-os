from __future__ import annotations

from uuid import UUID

from app.models.approval_request import ApprovalRequest
from app.runtime.contracts import ApprovalContract


def approval_request_to_contract(
    approval: ApprovalRequest,
    *,
    correlation_id: str,
    source: str = "approvals-api",
) -> ApprovalContract:
    payload = {
        "organizationId": approval.organization_id,
        "correlationId": correlation_id,
        "source": source,
        "approvalRequestId": approval.id,
        "actionType": approval.action_type,
        "subjectType": approval.subject_type or "unknown",
        "subjectId": str(approval.subject_id or UUID(int=0)),
        "status": approval.status,
        "requestedBy": approval.requested_by or "unknown",
        "preview": approval.preview or {},
        "policyReason": approval.policy_class,
        "executionPlan": approval.details or None,
    }
    if approval.created_at:
        payload["createdAt"] = approval.created_at.isoformat()
    if approval.expires_at:
        payload["expiresAt"] = approval.expires_at.isoformat()
    return ApprovalContract.model_validate(payload)
