"""Workflow runner — calls MCP registry safely with policy enforcement."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.agent_workflows.errors import (
    WorkflowMaxStepsExceededError,
    WorkflowPolicyViolationError,
    WorkflowStepFailedError,
)
from app.agent_workflows.policies import WorkflowPolicy, WorkflowPolicyEngine
from app.agent_workflows.schemas import ToolCallRef, WorkflowRun, WorkflowStep
from app.agent_workflows.state import workflow_store
from app.mcp.auth import MCPAuthContext
from app.mcp.registry import mcp_registry
from app.mcp.schemas import MCPResponse, MCPError, MCPResponseMeta


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str = "wf") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class WorkflowRunner:
    """Runs workflows through MCP registry with policy enforcement."""

    def __init__(self, policy: WorkflowPolicy) -> None:
        self.policy = policy
        self.policy_engine = WorkflowPolicyEngine(policy)

    async def run_workflow(
        self,
        workflow_type: str,
        organization_id: str,
        inputs: dict[str, Any],
        auth_ctx: MCPAuthContext,
        step_handlers: list[dict[str, Any]],
    ) -> WorkflowRun:
        """Execute a sequence of steps with policy enforcement.

        Args:
            workflow_type: Registered workflow type name.
            organization_id: Org UUID string.
            inputs: Workflow input parameters.
            auth_ctx: Authenticated MCP auth context.
            step_handlers: List of step dicts with keys:
                - step_name: str
                - tool_name: str
                - arguments: dict or callable returning dict
                - required: bool (default True)
                - skip_if: callable or None

        Returns:
            The completed WorkflowRun with ref-based state.
        """
        run_id = _new_id("wf")
        run = WorkflowRun(
            workflow_run_id=run_id,
            organization_id=organization_id,
            workflow_type=workflow_type,
            status="running",
            actor_type=auth_ctx.actor_type or "system",
            actor_id=auth_ctx.actor_id,
        )
        workflow_store.save_run(run)

        for i, handler in enumerate(step_handlers):
            step_name = handler.get("step_name", f"step_{i}")
            tool_name = handler.get("tool_name", "")
            arguments_raw = handler.get("arguments", {})
            required = handler.get("required", True)
            skip_if = handler.get("skip_if", None)

            # Resolve callable arguments (lambdas)
            if callable(arguments_raw):
                arguments = arguments_raw()
            else:
                arguments = dict(arguments_raw)

            # Check max steps
            allowed, reason = self.policy_engine.check_max_steps(i)
            if not allowed:
                run.status = "failed"
                run.error_code = "MAX_STEPS_EXCEEDED"
                run.error_message = reason
                workflow_store.save_run(run)
                raise WorkflowMaxStepsExceededError(reason or "max steps exceeded")

            # Skip check
            if skip_if and skip_if(inputs):
                step = WorkflowStep(
                    step_id=_new_id("step"),
                    workflow_run_id=run_id,
                    step_name=step_name,
                    status="skipped",
                    tool_name=tool_name,
                )
                run.steps.append(step)
                run.current_step = step_name
                workflow_store.save_run(run)
                continue

            step = WorkflowStep(
                step_id=_new_id("step"),
                workflow_run_id=run_id,
                step_name=step_name,
                status="running",
                started_at=_now(),
                tool_name=tool_name,
            )
            run.current_step = step_name
            workflow_store.save_run(run)

            # Call tool safely through MCP registry
            result = await self.call_tool_safely(
                tool_name=tool_name,
                arguments=arguments,
                auth_ctx=auth_ctx,
                step=step,
            )

            # Determine status from MCPResponse
            if result.ok:
                step.status = "completed"
                step.tool_result_summary = _summarize_result(result)
                step.completed_at = _now()
            elif not result.ok and result.error and result.error.code == "APPROVAL_REQUIRED":
                # Approval created is a valid workflow outcome
                step.status = "completed"
                step.tool_result_summary = _summarize_result(result)
                step.completed_at = _now()
            else:
                step.status = "failed" if required else "skipped"
                step.error_code = result.error.code if result.error else "TOOL_FAILED"
                step.tool_result_summary = _summarize_result(result)
                step.completed_at = _now()
                if required and self.policy.stop_on_tool_failure:
                    run.status = "failed"
                    run.error_code = "REQUIRED_STEP_FAILED"
                    run.error_message = f"Required step '{step_name}' failed"
                    run.completed_at = _now()
                    workflow_store.save_run(run)
                    raise WorkflowStepFailedError(
                        f"Required step '{step_name}' failed: {step.tool_result_summary}"
                    )

            run.steps.append(step)
            workflow_store.save_run(run)

        # Complete run
        run.status = "completed"
        run.completed_at = _now()
        workflow_store.save_run(run)
        return run

    async def call_tool_safely(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        auth_ctx: MCPAuthContext,
        step: WorkflowStep | None = None,
    ) -> MCPResponse:
        """Call a tool through MCP registry with policy enforcement."""
        # 1. Policy check: tool allowed
        allowed, reason = self.policy_engine.check_tool_allowed(tool_name)
        if not allowed:
            return MCPResponse.error_response(
                code="POLICY_BLOCKED",
                message=reason or f"Tool {tool_name} blocked by policy",
                request_id=_new_id("req"),
                organization_id=str(auth_ctx.organization_id) if auth_ctx.organization_id else "",
            )

        # 2. Policy check: external calls
        is_external_tool = self._is_external_tool(tool_name)
        if is_external_tool:
            allowed, reason = self.policy_engine.check_external_calls_allowed()
            if not allowed:
                return MCPResponse.error_response(
                    code="EXTERNAL_CALLS_DISABLED",
                    message=reason or "Real external calls disabled by policy",
                    request_id=_new_id("req"),
                    organization_id=str(auth_ctx.organization_id) if auth_ctx.organization_id else "",
                )

        # 3. Dispatch through MCP registry
        arguments = dict(arguments)
        arguments["organization_id"] = str(auth_ctx.organization_id) if auth_ctx.organization_id else ""
        response = await mcp_registry.call_tool(
            name=tool_name,
            params=arguments,
            auth=auth_ctx,
        )

        return response

    def _is_external_tool(self, tool_name: str) -> bool:
        """Check if a tool makes real external calls.

        NOTE: APPROVAL_REQUIRED mock tools (send_customer_email, share_public_doc,
        create_real_calendar_event, etc.) are NOT real external calls — they create
        ApprovalRequests without executing. Only tools that truly make external
        calls or access secrets are blocked here.

        This check will need updating when real providers are introduced.
        """
        external_tools = {
            "deploy_production",
            "read_env",
            "print_secrets",
        }
        return tool_name in external_tools


def _summarize_result(result: MCPResponse) -> str:
    """Short summary of MCP response — stores ref, not full content."""
    parts = []
    if result.error:
        parts.append(f"[{result.error.code}] {result.error.message[:100]}")
    elif result.ok:
        parts.append("ok")
    if result.data:
        # Only include non-sensitive keys
        safe_keys = {k for k in result.data.keys()
                     if k.lower() not in ("secret", "token", "password", "key", "credentials")}
        parts.append(f"data_keys={list(safe_keys)}")
    return "; ".join(parts) if parts else "no summary"
