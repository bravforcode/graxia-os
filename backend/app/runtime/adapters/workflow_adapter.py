from __future__ import annotations

from app.agent_workflows.schemas import WorkflowRun
from app.runtime.contracts import WorkflowRunRef


def workflow_run_to_ref(
    run: WorkflowRun,
    *,
    correlation_id: str,
    source: str = "workflow-engine",
) -> WorkflowRunRef:
    return WorkflowRunRef.model_validate(
        {
            "organizationId": run.organization_id,
            "correlationId": correlation_id,
            "createdAt": run.started_at,
            "source": source,
            "workflowRunId": run.workflow_run_id,
            "workflowName": run.workflow_type,
            "status": run.status,
            "startedAt": run.started_at,
            "completedAt": run.completed_at,
            "businessEventId": run.metadata.get("business_event_id"),
            "contextPacketId": run.context_pack_ids[0] if run.context_pack_ids else None,
        }
    )

