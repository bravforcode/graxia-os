from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.agent_workflows.schemas import WorkflowRun
from app.agent_workflows.service import workflow_engine_service
from app.agent_workflows.state import workflow_store
from app.mcp.schemas import MCPAuthContext
from app.runtime.adapters.workflow_adapter import workflow_run_to_ref
from app.runtime.contracts import WorkflowRunRef, WorkflowRunStatus
from app.runtime.orchestration.dispatcher import (
    QueueDispatchReceipt,
    QueueDispatchRequest,
    RuntimeWorkflowDispatcher,
)
from app.runtime.orchestration.trace_store import WorkflowTraceRecord, workflow_trace_store
from app.runtime.orchestration.workflow_registry import (
    RuntimeWorkflowDefinition,
    runtime_workflow_registry,
)


def _iso_to_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _new_workflow_run_id(prefix: str = "wf") -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


class RuntimeOrchestrationService:
    def __init__(
        self,
        *,
        execution_mode: str = "local",
        queue_enabled: bool = False,
        dispatcher: RuntimeWorkflowDispatcher | None = None,
    ) -> None:
        self.execution_mode = execution_mode
        self.queue_enabled = queue_enabled
        self.dispatcher = dispatcher or RuntimeWorkflowDispatcher()

    def list_workflows(self) -> list[dict[str, Any]]:
        return [
            {
                "workflow_name": item.workflow_name,
                "description": item.description,
                "backend_workflow_type": item.backend_workflow_type,
                "requires_approval": item.requires_approval,
                "queue_supported": item.queue_supported,
            }
            for item in runtime_workflow_registry.list()
        ]

    async def run_workflow(
        self,
        *,
        workflow_name: str,
        organization_id: str,
        inputs: dict[str, Any],
        auth_ctx: MCPAuthContext,
        correlation_id: str,
        business_event_id: str | None = None,
        context_packet_id: str | None = None,
    ) -> WorkflowRunRef:
        definition = runtime_workflow_registry.get(workflow_name)
        if self.execution_mode == "queue" and self.queue_enabled:
            receipt = await self.dispatcher.dispatch_to_queue(
                QueueDispatchRequest(
                    workflow_name=workflow_name,
                    organization_id=organization_id,
                    correlation_id=correlation_id,
                    business_event_id=business_event_id,
                    context_packet_id=context_packet_id,
                    inputs=inputs,
                )
            )
            workflow_ref = WorkflowRunRef.model_validate(
                {
                    "organizationId": organization_id,
                    "correlationId": correlation_id,
                    "source": "runtime_orchestration_queue",
                    "workflowRunId": receipt.workflow_run_id,
                    "workflowName": workflow_name,
                    "status": WorkflowRunStatus.PENDING,
                    "startedAt": None,
                    "completedAt": None,
                    "businessEventId": business_event_id,
                    "contextPacketId": context_packet_id,
                }
            )
            self._save_trace(
                workflow=workflow_ref,
                organization_id=organization_id,
                correlation_id=correlation_id,
                workflow_name=workflow_name,
                execution_mode="queue",
                business_event_id=business_event_id,
                context_packet_id=context_packet_id,
                summary=receipt.summary,
                metadata={"status": receipt.status},
            )
            return workflow_ref

        run = await self._run_local_definition(
            definition=definition,
            organization_id=organization_id,
            inputs=inputs,
            auth_ctx=auth_ctx,
            correlation_id=correlation_id,
            business_event_id=business_event_id,
            context_packet_id=context_packet_id,
        )
        workflow_ref = workflow_run_to_ref(
            run,
            correlation_id=correlation_id,
            source="runtime_orchestration",
        )
        if workflow_ref.workflow_name != workflow_name:
            workflow_ref = WorkflowRunRef.model_validate(
                {
                    **workflow_ref.model_dump(by_alias=True),
                    "workflowName": workflow_name,
                    "businessEventId": business_event_id,
                    "contextPacketId": context_packet_id,
                }
            )
        self._save_trace(
            workflow=workflow_ref,
            organization_id=organization_id,
            correlation_id=correlation_id,
            workflow_name=workflow_name,
            execution_mode="local",
            business_event_id=business_event_id,
            context_packet_id=context_packet_id,
            summary=run.output_summary or "",
            metadata={"backend_workflow_type": definition.backend_workflow_type},
        )
        return workflow_ref

    def get_workflow_run(self, workflow_run_id: str, organization_id: str) -> WorkflowRunRef:
        run = workflow_store.get_run(workflow_run_id, organization_id)
        correlation_id = str(run.metadata.get("correlation_id") or f"corr-{workflow_run_id}")
        return workflow_run_to_ref(
            run,
            correlation_id=correlation_id,
            source="runtime_orchestration",
        )

    def list_traces(
        self,
        *,
        organization_id: str | None = None,
        correlation_id: str | None = None,
        workflow_name: str | None = None,
        limit: int = 20,
    ) -> list[WorkflowTraceRecord]:
        return workflow_trace_store.list(
            organization_id=organization_id,
            correlation_id=correlation_id,
            workflow_name=workflow_name,
            limit=limit,
        )

    async def _run_local_definition(
        self,
        *,
        definition: RuntimeWorkflowDefinition,
        organization_id: str,
        inputs: dict[str, Any],
        auth_ctx: MCPAuthContext,
        correlation_id: str,
        business_event_id: str | None,
        context_packet_id: str | None,
    ) -> WorkflowRun:
        if definition.backend_workflow_type is None:
            run = WorkflowRun(
                workflow_run_id=_new_workflow_run_id(),
                organization_id=organization_id,
                workflow_type=definition.workflow_name,
                status="completed",
                actor_type=auth_ctx.actor_type or "system",
                actor_id=auth_ctx.actor_id,
                completed_at=datetime.now(UTC).isoformat(),
                output_summary=(
                    "Boundary placeholder completed locally. "
                    "No real external workflow execution occurred."
                ),
                metadata={
                    "correlation_id": correlation_id,
                    "business_event_id": business_event_id,
                    "context_packet_id": context_packet_id,
                    "boundary_placeholder": True,
                },
            )
            workflow_store.save_run(run)
            return run

        run = await workflow_engine_service.run_workflow(
            workflow_type=definition.backend_workflow_type,
            organization_id=organization_id,
            inputs=inputs,
            auth_ctx=auth_ctx,
        )
        run.metadata["correlation_id"] = correlation_id
        if business_event_id:
            run.metadata["business_event_id"] = business_event_id
        if context_packet_id:
            run.metadata["context_packet_id"] = context_packet_id
            if context_packet_id not in run.context_pack_ids:
                run.context_pack_ids.append(context_packet_id)
        workflow_store.save_run(run)
        return run

    def _save_trace(
        self,
        *,
        workflow: WorkflowRunRef,
        organization_id: str,
        correlation_id: str,
        workflow_name: str,
        execution_mode: str,
        business_event_id: str | None,
        context_packet_id: str | None,
        summary: str,
        metadata: dict[str, Any],
    ) -> None:
        workflow_trace_store.save(
            WorkflowTraceRecord(
                workflow=workflow,
                organizationId=organization_id,
                correlationId=correlation_id,
                workflowName=workflow_name,
                executionMode=execution_mode,
                businessEventId=business_event_id,
                contextPacketId=context_packet_id,
                summary=summary,
                metadata=metadata,
            )
        )


runtime_orchestration_service = RuntimeOrchestrationService()
