"""MCP runtime tools — expose additive runtime state through the existing MCP stack."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.context_engine import TokenRoiInput, evaluate_token_roi
from app.context_engine.service import ContextEngineService
from app.mcp.audit import log_mcp_tool_call
from app.mcp.registry import mcp_registry
from app.mcp.schemas import MCPAuthContext, MCPResponse
from app.mcp.tools.context import _error_response
from app.mcp.tools.write import _approval_response, _create_approval_request, _validate_org
from app.runtime.gateway import GatewayService
from app.runtime.workers import RuntimeWorkerService

if TYPE_CHECKING:
    from app.runtime.orchestration import RuntimeOrchestrationService
    from app.runtime.events.repository import InMemoryBusinessEventRepository

_gateway_service: GatewayService | None = None
_context_service: ContextEngineService | None = None
_orchestration_service: Any = None
_worker_service: RuntimeWorkerService | None = None
_business_event_repository: Any = None


def _get_gateway_service() -> GatewayService:
    global _gateway_service
    if _gateway_service is None:
        _gateway_service = GatewayService()
    return _gateway_service


def _get_context_service() -> ContextEngineService:
    global _context_service
    if _context_service is None:
        _context_service = ContextEngineService()
    return _context_service


def _get_orchestration_service() -> "RuntimeOrchestrationService":
    global _orchestration_service
    if _orchestration_service is None:
        from app.runtime.orchestration import RuntimeOrchestrationService

        _orchestration_service = RuntimeOrchestrationService()
    return _orchestration_service


def _get_worker_service() -> RuntimeWorkerService:
    global _worker_service
    if _worker_service is None:
        _worker_service = RuntimeWorkerService()
    return _worker_service


def _get_business_event_repository() -> "InMemoryBusinessEventRepository":
    global _business_event_repository
    if _business_event_repository is None:
        from app.runtime.events.service import business_event_repository

        _business_event_repository = business_event_repository
    return _business_event_repository


def _reset_runtime_services_for_tests() -> None:
    global _gateway_service, _context_service, _orchestration_service, _worker_service, _business_event_repository
    from app.runtime.orchestration import RuntimeOrchestrationService

    _gateway_service = GatewayService()
    _context_service = ContextEngineService()
    _orchestration_service = RuntimeOrchestrationService()
    _worker_service = RuntimeWorkerService()
    _business_event_repository = None


TOOL_INPUT_ORG_ONLY = {
    "type": "object",
    "properties": {
        "organization_id": {"type": "string", "description": "UUID of the organization"},
    },
    "required": ["organization_id"],
    "additionalProperties": False,
}


@mcp_registry.register(
    name="get_runtime_status",
    description="Get runtime status across gateway, events, workflows, context, and workers.",
    input_schema=TOOL_INPUT_ORG_ONLY,
    output_schema={"type": "object", "properties": {}, "additionalProperties": True},
    risk_level="READ_ONLY",
)
async def handle_get_runtime_status(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
) -> MCPResponse:
    request_id = auth.request_id if auth else ""
    _, err = await _validate_org(auth, organization_id, request_id)
    if err:
        return err
    gateway = _get_gateway_service()
    orchestration = _get_orchestration_service()
    worker = _get_worker_service()
    business_event_repository = _get_business_event_repository()
    tasks = await gateway.list_task_statuses(limit=100)
    dead_letters = await gateway.list_dead_letters(limit=100)
    traces = orchestration.list_traces(organization_id=organization_id, limit=100)
    events = await business_event_repository.list(organization_id=organization_id)
    return MCPResponse.ok_response(
        data={
            "gateway_task_count": len(tasks),
            "dead_letter_count": len(dead_letters),
            "workflow_trace_count": len(traces),
            "business_event_count": len(events),
            "worker_capability_count": len(worker.list_capabilities()),
            "worker_capabilities": worker.list_capabilities(),
            "execution_modes": ["local", "queue"],
        },
        organization_id=organization_id,
        request_id=request_id,
        estimated_tokens=40,
    )


@mcp_registry.register(
    name="list_runtime_tasks",
    description="List runtime task statuses tracked by the gateway.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string"},
            "limit": {"type": "integer", "default": 20},
        },
        "required": ["organization_id"],
        "additionalProperties": False,
    },
    output_schema={"type": "object", "properties": {}, "additionalProperties": True},
    risk_level="READ_ONLY",
)
async def handle_list_runtime_tasks(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    limit: int = 20,
) -> MCPResponse:
    request_id = auth.request_id if auth else ""
    _, err = await _validate_org(auth, organization_id, request_id)
    if err:
        return err
    items = await _get_gateway_service().list_task_statuses(limit=limit)
    return MCPResponse.ok_response(
        data={
            "items": [
                {
                    "task_id": str(item.task_id),
                    "correlation_id": item.correlation_id,
                    "target": item.target,
                    "status": item.status,
                    "risk_level": item.risk_level,
                    "dead_lettered": item.dead_lettered,
                }
                for item in items
            ],
            "total": len(items),
        },
        organization_id=organization_id,
        request_id=request_id,
        estimated_tokens=max(10, len(items) * 12),
    )


@mcp_registry.register(
    name="get_runtime_task",
    description="Get one runtime task by task ID.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "required": ["organization_id", "task_id"],
        "additionalProperties": False,
    },
    output_schema={"type": "object", "properties": {}, "additionalProperties": True},
    risk_level="READ_ONLY",
)
async def handle_get_runtime_task(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    task_id: str = "",
) -> MCPResponse:
    request_id = auth.request_id if auth else ""
    _, err = await _validate_org(auth, organization_id, request_id)
    if err:
        return err
    try:
        item = await _get_gateway_service().get_task_status(UUID(task_id))
    except (ValueError, TypeError):
        return _error_response("INVALID_PARAMS", "Invalid task_id.", request_id, organization_id)
    if item is None:
        return _error_response("NOT_FOUND", "Runtime task not found.", request_id, organization_id)
    return MCPResponse.ok_response(
        data={
            "task": {
                "task_id": str(item.task_id),
                "correlation_id": item.correlation_id,
                "target": item.target,
                "status": item.status,
                "risk_level": item.risk_level,
                "dead_lettered": item.dead_lettered,
            }
        },
        organization_id=organization_id,
        request_id=request_id,
        estimated_tokens=20,
    )


@mcp_registry.register(
    name="list_dead_letters",
    description="List gateway dead-letter records.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string"},
            "limit": {"type": "integer", "default": 20},
        },
        "required": ["organization_id"],
        "additionalProperties": False,
    },
    output_schema={"type": "object", "properties": {}, "additionalProperties": True},
    risk_level="READ_ONLY",
)
async def handle_list_dead_letters(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    limit: int = 20,
) -> MCPResponse:
    request_id = auth.request_id if auth else ""
    _, err = await _validate_org(auth, organization_id, request_id)
    if err:
        return err
    items = await _get_gateway_service().list_dead_letters(limit=limit)
    return MCPResponse.ok_response(
        data={
            "items": [
                {
                    "dead_letter_id": str(item.dead_letter_id),
                    "task_id": str(item.task_id),
                    "reason": item.reason,
                    "replay_count": item.replay_count,
                }
                for item in items
            ],
            "total": len(items),
        },
        organization_id=organization_id,
        request_id=request_id,
        estimated_tokens=max(10, len(items) * 15),
    )


@mcp_registry.register(
    name="request_dead_letter_requeue",
    description="Create ApprovalRequest to requeue a dead-letter task. Does not requeue immediately.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string"},
            "dead_letter_id": {"type": "string"},
        },
        "required": ["organization_id", "dead_letter_id"],
        "additionalProperties": False,
    },
    output_schema={"type": "object", "properties": {}, "additionalProperties": True},
    risk_level="APPROVAL_REQUIRED",
    requires_approval=True,
)
async def handle_request_dead_letter_requeue(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    dead_letter_id: str = "",
) -> MCPResponse:
    request_id = auth.request_id if auth else ""
    org_uuid, err = await _validate_org(auth, organization_id, request_id)
    if err:
        return err
    items = await _get_gateway_service().list_dead_letters(limit=100)
    dead_letter = next((item for item in items if str(item.dead_letter_id) == dead_letter_id), None)
    if dead_letter is None:
        return _error_response("NOT_FOUND", "Dead letter not found.", request_id, organization_id)
    ar = await _create_approval_request(
        organization_id=org_uuid,
        action_type="request_dead_letter_requeue",
        title=f"Requeue dead letter {dead_letter_id[:12]}...",
        subject_type="runtime_dead_letter",
        subject_id=None,
        details={
            "dead_letter_id": dead_letter_id,
            "task_id": str(dead_letter.task_id),
            "reason": dead_letter.reason,
        },
        preview={
            "action": "requeue_dead_letter",
            "dead_letter_id": dead_letter_id,
            "task_id": str(dead_letter.task_id),
            "reason": dead_letter.reason,
        },
    )
    await log_mcp_tool_call(
        organization_id=org_uuid,
        actor_type=auth.actor_type if auth else "system",
        actor_id=auth.actor_id if auth else "system",
        tool_name="request_dead_letter_requeue",
        risk_level="APPROVAL_REQUIRED",
        status="approval_required",
        request_id=request_id,
    )
    return _approval_response(ar, organization_id, request_id)


@mcp_registry.register(
    name="list_business_events",
    description="List canonical runtime business events.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string"},
            "event_type": {"type": "string", "default": ""},
        },
        "required": ["organization_id"],
        "additionalProperties": False,
    },
    output_schema={"type": "object", "properties": {}, "additionalProperties": True},
    risk_level="READ_ONLY",
)
async def handle_list_business_events(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    event_type: str = "",
) -> MCPResponse:
    request_id = auth.request_id if auth else ""
    _, err = await _validate_org(auth, organization_id, request_id)
    if err:
        return err
    business_event_repository = _get_business_event_repository()
    items = await business_event_repository.list(
        organization_id=organization_id,
        event_type=event_type or None,
    )
    return MCPResponse.ok_response(
        data={
            "items": [
                {
                    "event_id": str(item.event_id),
                    "event_type": item.event_type,
                    "subject_type": item.subject_type,
                    "subject_id": item.subject_id,
                    "correlation_id": item.correlation_id,
                }
                for item in items
            ],
            "total": len(items),
        },
        organization_id=organization_id,
        request_id=request_id,
        estimated_tokens=max(10, len(items) * 12),
    )


@mcp_registry.register(
    name="get_business_event",
    description="Get one canonical runtime business event.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string"},
            "event_id": {"type": "string"},
        },
        "required": ["organization_id", "event_id"],
        "additionalProperties": False,
    },
    output_schema={"type": "object", "properties": {}, "additionalProperties": True},
    risk_level="READ_ONLY",
)
async def handle_get_business_event(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    event_id: str = "",
) -> MCPResponse:
    request_id = auth.request_id if auth else ""
    _, err = await _validate_org(auth, organization_id, request_id)
    if err:
        return err
    business_event_repository = _get_business_event_repository()
    items = await business_event_repository.list(organization_id=organization_id)
    event = next((item for item in items if str(item.event_id) == event_id), None)
    if event is None:
        return _error_response("NOT_FOUND", "Business event not found.", request_id, organization_id)
    return MCPResponse.ok_response(
        data={
            "event": {
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "subject_type": event.subject_type,
                "subject_id": event.subject_id,
                "correlation_id": event.correlation_id,
                "payload": event.payload,
            }
        },
        organization_id=organization_id,
        request_id=request_id,
        estimated_tokens=30,
    )


@mcp_registry.register(
    name="build_runtime_context_packet",
    description="Build a runtime-focused context packet with the existing context engine.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string"},
            "task_type": {"type": "string", "default": "runtime_review"},
            "goal": {"type": "string", "default": "runtime review"},
            "token_budget": {"type": "integer", "default": 4000},
        },
        "required": ["organization_id"],
        "additionalProperties": False,
    },
    output_schema={"type": "object", "properties": {}, "additionalProperties": True},
    risk_level="READ_ONLY",
)
async def handle_build_runtime_context_packet(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    task_type: str = "runtime_review",
    goal: str = "runtime review",
    token_budget: int = 4000,
) -> MCPResponse:
    request_id = auth.request_id if auth else ""
    _, err = await _validate_org(auth, organization_id, request_id)
    if err:
        return err
    pack = _get_context_service().build_context_pack(
        task_type=task_type,
        goal=goal,
        token_budget=token_budget,
        must_preserve=["no secrets", "no raw tokens", "runtime correctness"],
    )
    return MCPResponse.ok_response(
        data={
            "context_pack_id": pack.context_pack_id,
            "task_type": pack.task_type,
            "goal": pack.goal,
            "estimated_tokens": pack.estimated_tokens,
            "warnings": pack.warnings,
        },
        organization_id=organization_id,
        request_id=request_id,
        estimated_tokens=pack.estimated_tokens,
    )


@mcp_registry.register(
    name="get_token_roi_summary",
    description="Evaluate token ROI with deterministic runtime-safe metrics.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string"},
            "tokens_saved": {"type": "integer"},
            "retry_count": {"type": "integer", "default": 0},
            "retry_token_cost": {"type": "integer", "default": 0},
            "human_correction_count": {"type": "integer", "default": 0},
            "human_correction_cost": {"type": "integer", "default": 0},
            "quality_gate_passed": {"type": "boolean", "default": True},
            "critical_context_lost": {"type": "boolean", "default": False},
            "compression_ratio": {"type": "number", "default": 0.0},
            "cache_hit_rate": {"type": "number", "default": 0.0},
            "quality_gate_failures": {"type": "integer", "default": 0},
            "auto_escalations": {"type": "integer", "default": 0},
            "stale_context_incidents": {"type": "integer", "default": 0},
        },
        "required": ["organization_id", "tokens_saved"],
        "additionalProperties": False,
    },
    output_schema={"type": "object", "properties": {}, "additionalProperties": True},
    risk_level="READ_ONLY",
)
async def handle_get_token_roi_summary(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    tokens_saved: int = 0,
    retry_count: int = 0,
    retry_token_cost: int = 0,
    human_correction_count: int = 0,
    human_correction_cost: int = 0,
    quality_gate_passed: bool = True,
    critical_context_lost: bool = False,
    compression_ratio: float = 0.0,
    cache_hit_rate: float = 0.0,
    quality_gate_failures: int = 0,
    auto_escalations: int = 0,
    stale_context_incidents: int = 0,
) -> MCPResponse:
    request_id = auth.request_id if auth else ""
    _, err = await _validate_org(auth, organization_id, request_id)
    if err:
        return err
    result = evaluate_token_roi(
        TokenRoiInput(
            tokens_saved=tokens_saved,
            retry_count=retry_count,
            retry_token_cost=retry_token_cost,
            human_correction_count=human_correction_count,
            human_correction_cost=human_correction_cost,
            quality_gate_passed=quality_gate_passed,
            critical_context_lost=critical_context_lost,
            compression_ratio=compression_ratio,
            cache_hit_rate=cache_hit_rate,
            quality_gate_failures=quality_gate_failures,
            auto_escalations=auto_escalations,
            stale_context_incidents=stale_context_incidents,
        )
    )
    return MCPResponse.ok_response(
        data={
            "tokens_saved": result.tokens_saved,
            "retry_cost": result.retry_cost,
            "correction_cost": result.correction_cost,
            "quality_penalty": result.quality_penalty,
            "escalation_penalty": result.escalation_penalty,
            "stale_context_penalty": result.stale_context_penalty,
            "cache_credit": result.cache_credit,
            "net_roi": result.net_roi,
            "profitable": result.profitable,
            "recommendation": result.recommendation,
            "compression_ratio": result.compression_ratio,
            "cache_hit_rate": result.cache_hit_rate,
            "quality_gate_failures": result.quality_gate_failures,
            "auto_escalations": result.auto_escalations,
            "stale_context_incidents": result.stale_context_incidents,
        },
        organization_id=organization_id,
        request_id=request_id,
        estimated_tokens=20,
    )


@mcp_registry.register(
    name="run_safe_workflow",
    description="Run safe runtime workflows only. Approval-gated workflows create ApprovalRequest instead.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string"},
            "workflow_name": {"type": "string"},
            "inputs": {"type": "object", "default": {}},
        },
        "required": ["organization_id", "workflow_name"],
        "additionalProperties": False,
    },
    output_schema={"type": "object", "properties": {}, "additionalProperties": True},
    risk_level="LOW_WRITE",
)
async def handle_run_safe_workflow(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    workflow_name: str = "",
    inputs: dict | None = None,
) -> MCPResponse:
    request_id = auth.request_id if auth else ""
    org_uuid, err = await _validate_org(auth, organization_id, request_id)
    if err:
        return err
    try:
        from app.runtime.orchestration import runtime_workflow_registry

        definition = runtime_workflow_registry.get(workflow_name)
    except KeyError:
        return _error_response("WORKFLOW_NOT_FOUND", "Runtime workflow not found.", request_id, organization_id)
    if definition.requires_approval:
        ar = await _create_approval_request(
            organization_id=org_uuid,
            action_type="run_safe_workflow",
            title=f"Run approval-gated workflow: {workflow_name}",
            subject_type="runtime_workflow",
            subject_id=None,
            details={"workflow_name": workflow_name, "inputs": inputs or {}},
            preview={"workflow_name": workflow_name, "inputs": inputs or {}},
        )
        await log_mcp_tool_call(
            organization_id=org_uuid,
            actor_type=auth.actor_type if auth else "system",
            actor_id=auth.actor_id if auth else "system",
            tool_name="run_safe_workflow",
            risk_level="APPROVAL_REQUIRED",
            status="approval_required",
            request_id=request_id,
        )
        return _approval_response(ar, organization_id, request_id)
    workflow = await _get_orchestration_service().run_workflow(
        workflow_name=workflow_name,
        organization_id=organization_id,
        inputs=inputs or {},
        auth_ctx=auth or MCPAuthContext.system(organization_id=org_uuid),
        correlation_id=request_id or f"runtime-wf:{workflow_name}",
    )
    return MCPResponse.ok_response(
        data={
            "workflow_run_id": workflow.workflow_run_id,
            "workflow_name": workflow.workflow_name,
            "status": workflow.status,
        },
        organization_id=organization_id,
        request_id=request_id,
        estimated_tokens=25,
    )
