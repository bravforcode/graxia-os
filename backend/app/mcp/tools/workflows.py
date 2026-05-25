"""MCP workflow tools — list, run, and query agent workflows."""
from __future__ import annotations

import uuid
from typing import Any

from app.agent_workflows.errors import WorkflowNotFoundError
from app.mcp.auth import MCPAuthContext, safe_org_not_found, validate_org_context
from app.mcp.registry import mcp_registry
from app.mcp.schemas import MCPResponse, MCPError, MCPResponseMeta


def _new_id(prefix: str = "req") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


async def _resolve_org(org_id: str) -> str | None:
    """Resolve and validate organization ID."""
    from uuid import UUID
    if not org_id:
        return None
    ctx = MCPAuthContext.system(organization_id=org_id)
    try:
        org_uuid = UUID(org_id)
    except (ValueError, TypeError):
        return None
    if not validate_org_context(ctx, org_uuid):
        safe_org_not_found()
    return org_id


# ── Common Schemas ───────────────────────────────────────────────────────────

TOOL_INPUT_ORG = {
    "type": "object",
    "properties": {
        "organization_id": {"type": "string", "description": "UUID of the organization"},
    },
    "required": ["organization_id"],
    "additionalProperties": False,
}

TOOL_OUTPUT_WORKFLOW_LIST = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": {"type": "object"}},
        "total": {"type": "integer"},
    },
    "additionalProperties": False,
}

TOOL_OUTPUT_WORKFLOW_RUN = {
    "type": "object",
    "properties": {
        "workflow_run_id": {"type": "string"},
        "workflow_type": {"type": "string"},
        "status": {"type": "string"},
        "summary": {"type": "string"},
        "context_pack_ids": {"type": "array", "items": {"type": "string"}},
        "approval_request_ids": {"type": "array", "items": {"type": "string"}},
        "workspace_item_ids": {"type": "array", "items": {"type": "string"}},
        "steps_completed": {"type": "integer"},
        "steps_failed": {"type": "integer"},
    },
    "additionalProperties": False,
}

TOOL_OUTPUT_WORKFLOW_STATUS = {
    "type": "object",
    "properties": {
        "total_runs": {"type": "integer"},
        "completed": {"type": "integer"},
        "failed": {"type": "integer"},
        "blocked": {"type": "integer"},
        "running": {"type": "integer"},
        "latest_run_id": {"type": "string"},
    },
    "additionalProperties": False,
}

TOOL_OUTPUT_POLICY = {
    "type": "object",
    "properties": {
        "workflow_type": {"type": "string"},
        "allowed_tools": {"type": "array", "items": {"type": "string"}},
        "blocked_tools": {"type": "array", "items": {"type": "string"}},
        "max_steps": {"type": "integer"},
        "token_budget": {"type": "integer"},
        "allow_real_external_calls": {"type": "boolean"},
        "allow_customer_send": {"type": "boolean"},
        "allow_publish": {"type": "boolean"},
    },
    "additionalProperties": False,
}

TOOL_OUTPUT_RUN_DETAIL = {
    "type": "object",
    "properties": {
        "workflow_run_id": {"type": "string"},
        "workflow_type": {"type": "string"},
        "status": {"type": "string"},
        "summary": {"type": "string"},
        "steps": {"type": "array", "items": {"type": "object"}},
        "context_pack_ids": {"type": "array", "items": {"type": "string"}},
        "approval_request_ids": {"type": "array", "items": {"type": "string"}},
        "workspace_item_ids": {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": False,
}


# ── Tool Handlers ─────────────────────────────────────────────────────


@mcp_registry.register(
    name="list_agent_workflows",
    description="List all registered agent workflows with descriptions and risk levels.",
    input_schema=TOOL_INPUT_ORG,
    output_schema=TOOL_OUTPUT_WORKFLOW_LIST,
    risk_level="READ_ONLY",
)
async def handle_list_agent_workflows(
    organization_id: str,
    auth: MCPAuthContext | None = None,
    **kwargs: Any,
) -> MCPResponse:
    from app.agent_workflows.service import workflow_engine_service
    request_id = _new_id("req")
    try:
        org = await _resolve_org(organization_id)
        if org is None:
            return MCPResponse.error_response(
                code="ORG_NOT_FOUND",
                message=f"Organization {organization_id} not found",
                request_id=request_id,
                organization_id=organization_id,
            )

        items = workflow_engine_service.list_workflows()
        return MCPResponse.ok_response(
            data={"items": items, "total": len(items)},
            organization_id=organization_id,
            request_id=request_id,
        )
    except Exception as e:
        return MCPResponse.error_response(
            code="HANDLER_ERROR",
            message=str(e),
            request_id=request_id,
            organization_id=organization_id,
        )


@mcp_registry.register(
    name="run_agent_workflow",
    description="Run an agent workflow. Creates local state and mock workspace outputs. Never sends real email or publishes.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "workflow_type": {"type": "string", "description": "Type of workflow to run"},
            "inputs": {"type": "object", "description": "Workflow input parameters"},
        },
        "required": ["organization_id", "workflow_type"],
        "additionalProperties": False,
    },
    output_schema=TOOL_OUTPUT_WORKFLOW_RUN,
    risk_level="LOW_WRITE",
)
async def handle_run_agent_workflow(
    organization_id: str,
    workflow_type: str,
    inputs: dict[str, Any] | None = None,
    auth: MCPAuthContext | None = None,
    **kwargs: Any,
) -> MCPResponse:
    from app.agent_workflows.service import workflow_engine_service
    request_id = _new_id("req")
    try:
        org = await _resolve_org(organization_id)
        if org is None:
            return MCPResponse.error_response(
                code="ORG_NOT_FOUND",
                message=f"Organization {organization_id} not found",
                request_id=request_id,
                organization_id=organization_id,
            )

        auth_ctx = auth or MCPAuthContext.system(organization_id=organization_id)
        run = await workflow_engine_service.run_workflow(
            workflow_type=workflow_type,
            organization_id=organization_id,
            inputs=inputs or {},
            auth_ctx=auth_ctx,
        )

        return MCPResponse.ok_response(
            data={
                "workflow_run_id": run.workflow_run_id,
                "workflow_type": run.workflow_type,
                "status": run.status,
                "summary": run.output_summary or f"Workflow {workflow_type} {run.status}",
                "context_pack_ids": run.context_pack_ids,
                "approval_request_ids": run.approval_request_ids,
                "workspace_item_ids": run.workspace_item_ids,
                "steps_completed": sum(1 for s in run.steps if s.status == "completed"),
                "steps_failed": sum(1 for s in run.steps if s.status == "failed"),
            },
            organization_id=organization_id,
            request_id=request_id,
        )
    except WorkflowNotFoundError as e:
        return MCPResponse.error_response(
            code="WORKFLOW_NOT_FOUND",
            message=str(e),
            request_id=request_id,
            organization_id=organization_id,
        )
    except Exception as e:
        return MCPResponse.error_response(
            code="HANDLER_ERROR",
            message=str(e),
            request_id=request_id,
            organization_id=organization_id,
        )


@mcp_registry.register(
    name="get_agent_workflow_run",
    description="Get details of a specific workflow run by ID.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "workflow_run_id": {"type": "string", "description": "UUID of the workflow run"},
        },
        "required": ["organization_id", "workflow_run_id"],
        "additionalProperties": False,
    },
    output_schema=TOOL_OUTPUT_RUN_DETAIL,
    risk_level="READ_ONLY",
)
async def handle_get_agent_workflow_run(
    organization_id: str,
    workflow_run_id: str,
    auth: MCPAuthContext | None = None,
    **kwargs: Any,
) -> MCPResponse:
    from app.agent_workflows.service import workflow_engine_service
    request_id = _new_id("req")
    try:
        org = await _resolve_org(organization_id)
        if org is None:
            return MCPResponse.error_response(
                code="ORG_NOT_FOUND",
                message=f"Organization {organization_id} not found",
                request_id=request_id,
                organization_id=organization_id,
            )

        run = workflow_engine_service.get_run(workflow_run_id, organization_id)
        return MCPResponse.ok_response(
            data={
                "workflow_run_id": run.workflow_run_id,
                "workflow_type": run.workflow_type,
                "status": run.status,
                "summary": run.output_summary,
                "steps": [
                    {
                        "step_name": s.step_name,
                        "status": s.status,
                        "tool_name": s.tool_name,
                        "tool_result_summary": s.tool_result_summary,
                    }
                    for s in run.steps
                ],
                "context_pack_ids": run.context_pack_ids,
                "approval_request_ids": run.approval_request_ids,
                "workspace_item_ids": run.workspace_item_ids,
            },
            organization_id=organization_id,
            request_id=request_id,
        )
    except Exception as e:
        return MCPResponse.error_response(
            code="HANDLER_ERROR",
            message=str(e),
            request_id=request_id,
            organization_id=organization_id,
        )


@mcp_registry.register(
    name="get_agent_workflow_status",
    description="Get overall workflow engine status for an organization.",
    input_schema=TOOL_INPUT_ORG,
    output_schema=TOOL_OUTPUT_WORKFLOW_STATUS,
    risk_level="READ_ONLY",
)
async def handle_get_agent_workflow_status(
    organization_id: str,
    auth: MCPAuthContext | None = None,
    **kwargs: Any,
) -> MCPResponse:
    from app.agent_workflows.service import workflow_engine_service
    request_id = _new_id("req")
    try:
        org = await _resolve_org(organization_id)
        if org is None:
            return MCPResponse.error_response(
                code="ORG_NOT_FOUND",
                message=f"Organization {organization_id} not found",
                request_id=request_id,
                organization_id=organization_id,
            )

        status = workflow_engine_service.get_status(organization_id)
        return MCPResponse.ok_response(
            data={
                "total_runs": status.total_runs,
                "completed": status.completed,
                "failed": status.failed,
                "blocked": status.blocked,
                "running": status.running,
                "latest_run_id": status.latest_run_id,
            },
            organization_id=organization_id,
            request_id=request_id,
        )
    except Exception as e:
        return MCPResponse.error_response(
            code="HANDLER_ERROR",
            message=str(e),
            request_id=request_id,
            organization_id=organization_id,
        )


@mcp_registry.register(
    name="get_agent_workflow_policy",
    description="Get the policy configuration for a specific workflow type.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "workflow_type": {"type": "string", "description": "Type of workflow"},
        },
        "required": ["organization_id", "workflow_type"],
        "additionalProperties": False,
    },
    output_schema=TOOL_OUTPUT_POLICY,
    risk_level="READ_ONLY",
)
async def handle_get_agent_workflow_policy(
    organization_id: str,
    workflow_type: str,
    auth: MCPAuthContext | None = None,
    **kwargs: Any,
) -> MCPResponse:
    from app.agent_workflows.service import workflow_engine_service
    request_id = _new_id("req")
    try:
        org = await _resolve_org(organization_id)
        if org is None:
            return MCPResponse.error_response(
                code="ORG_NOT_FOUND",
                message=f"Organization {organization_id} not found",
                request_id=request_id,
                organization_id=organization_id,
            )

        policy = workflow_engine_service.get_policy(workflow_type)
        if policy is None:
            return MCPResponse.error_response(
                code="WORKFLOW_NOT_FOUND",
                message=f"Workflow type '{workflow_type}' not found",
                request_id=request_id,
                organization_id=organization_id,
            )

        return MCPResponse.ok_response(
            data=policy,
            organization_id=organization_id,
            request_id=request_id,
        )
    except Exception as e:
        return MCPResponse.error_response(
            code="HANDLER_ERROR",
            message=str(e),
            request_id=request_id,
            organization_id=organization_id,
        )
