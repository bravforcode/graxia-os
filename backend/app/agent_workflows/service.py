"""WorkflowEngineService — orchestrates workflow lifecycle."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.agent_workflows.errors import (
    WorkflowNotFoundError,
    WorkflowOrgMismatchError,
    WorkflowPolicyViolationError,
)
from app.agent_workflows.policies import default_workflow_policy
from app.agent_workflows.registry import workflow_registry
from app.agent_workflows.runner import WorkflowRunner
from app.agent_workflows.schemas import WorkflowRun, WorkflowStatusSummary
from app.agent_workflows.state import workflow_store
from app.agent_workflows.workflows import (
    content_plan_draft,
    customer_inbox_triage,
    daily_funnel_brief,
    delivery_failure_monitor,
    experiment_planner,
    failure_analysis_review,
    launch_plan_builder,
    opportunity_scout,
    token_benchmark_review,
    weekly_revenue_review,
)
from app.mcp.auth import MCPAuthContext
from app.auth.permissions import normalize_permissions
from app.audit.security_events import emit_security_event_from_context

# Import MCP tools to register tool handlers with the global registry.
# The @mcp_registry.register decorators fire at import time.
import app.mcp.tools  # noqa: F401


WORKFLOW_REQUIRED_PERMISSIONS: dict[str, set[str]] = {
    "opportunity_scout": {"workflow:run", "analytics:read"},
    "failure_analysis_review": {"workflow:run", "analytics:read"},
    "daily_funnel_brief": {"workflow:run", "analytics:read"},
    "weekly_revenue_review": {"workflow:run", "analytics:read"},
    "content_plan_draft": {"workflow:run"},
    "experiment_planner": {"workflow:run"},
    "launch_plan_builder": {"workflow:run"},
    "customer_inbox_triage": {"workflow:run"},
    "delivery_failure_monitor": {"workflow:run"},
    "token_benchmark_review": {"workflow:run"},
}


class WorkflowEngineService:
    """Orchestrates workflow lifecycle."""

    def __init__(self) -> None:
        self._register_all()

    def _register_all(self) -> None:
        """Register all workflow definitions."""
        workflows = [
            daily_funnel_brief.definition(),
            launch_plan_builder.definition(),
            customer_inbox_triage.definition(),
            token_benchmark_review.definition(),
            delivery_failure_monitor.definition(),
            weekly_revenue_review.definition(),
            opportunity_scout.definition(),
            experiment_planner.definition(),
            content_plan_draft.definition(),
            failure_analysis_review.definition(),
        ]
        for wf in workflows:
            workflow_registry.register(wf)

    @staticmethod
    def _is_system_bypass(auth_ctx: MCPAuthContext) -> bool:
        return auth_ctx.actor_type == "system" and auth_ctx.actor_id == "system"

    def _require_workflow_access(
        self,
        workflow_type: str,
        organization_id: str,
        auth_ctx: MCPAuthContext,
    ) -> None:
        if auth_ctx.organization_id is None:
            raise WorkflowPolicyViolationError("Workflow auth context requires organization scope.")
        if str(auth_ctx.organization_id) != str(organization_id) and not self._is_system_bypass(auth_ctx):
            raise WorkflowOrgMismatchError("Resource not found.")
        if self._is_system_bypass(auth_ctx):
            return
        permissions = normalize_permissions(auth_ctx.permissions)
        required = WORKFLOW_REQUIRED_PERMISSIONS.get(workflow_type, {"workflow:run"})
        missing = sorted(required.difference(permissions))
        if missing:
            raise WorkflowPolicyViolationError(
                f"Workflow permission denied: missing {', '.join(missing)}."
            )

    async def _emit_workflow_denied(
        self,
        workflow_type: str,
        organization_id: str,
        auth_ctx: MCPAuthContext,
        reason: str,
    ) -> None:
        _req = getattr(auth_ctx, '_request', None)
        if _req is not None:
            await emit_security_event_from_context(
                _req,
                event_type="workflow.permission.denied",
                reason_code=reason,
                decision="blocked",
                route_or_tool=workflow_type,
                risk_level="LOW_WRITE",
                redacted_payload={"workflow_type": workflow_type, "organization_id": str(organization_id)[:8] + "..."},
            )

    async def run_workflow(
        self,
        workflow_type: str,
        organization_id: str,
        inputs: dict[str, Any],
        auth_ctx: MCPAuthContext,
    ) -> WorkflowRun:
        """Run a workflow by type."""
        self._require_workflow_access(workflow_type, organization_id, auth_ctx)
        definition = workflow_registry.get(workflow_type)

        # Merge inputs into WorkflowInputs-compatible dict
        merged = {
            "date_range": inputs.get("date_range", "today"),
            "product_id": inputs.get("product_id"),
            "product_name": inputs.get("product_name"),
            "target_customer": inputs.get("target_customer"),
            "offer_price": inputs.get("offer_price"),
            "metadata": inputs.get("metadata", {}),
        }

        runner = WorkflowRunner(policy=definition.policy)
        run = await definition.runner_fn(
            runner=runner,
            organization_id=organization_id,
            inputs=merged,
            auth_ctx=auth_ctx,
        )
        return run

    def list_workflows(self) -> list[dict[str, Any]]:
        return workflow_registry.list()

    def get_run(
        self, workflow_run_id: str, organization_id: str
    ) -> WorkflowRun:
        return workflow_store.get_run(workflow_run_id, organization_id)

    def get_status(self, organization_id: str) -> WorkflowStatusSummary:
        return workflow_store.get_status(organization_id)

    def get_policy(self, workflow_type: str) -> dict[str, Any] | None:
        try:
            definition = workflow_registry.get(workflow_type)
            return definition.policy.to_dict() if hasattr(definition.policy, "to_dict") else {
                "workflow_type": definition.workflow_type,
                "allowed_tools": definition.policy.allowed_tools,
                "blocked_tools": definition.policy.blocked_tools,
                "max_steps": definition.policy.max_steps,
                "token_budget": definition.policy.token_budget,
                "allow_real_external_calls": definition.policy.allow_real_external_calls,
                "allow_customer_send": definition.policy.allow_customer_send,
                "allow_publish": definition.policy.allow_publish,
            }
        except WorkflowNotFoundError:
            return None


# Global singleton service
workflow_engine_service = WorkflowEngineService()
