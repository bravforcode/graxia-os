"""WorkflowEngineService — orchestrates workflow lifecycle."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.agent_workflows.errors import WorkflowNotFoundError
from app.agent_workflows.policies import default_workflow_policy
from app.agent_workflows.registry import workflow_registry
from app.agent_workflows.runner import WorkflowRunner
from app.agent_workflows.schemas import WorkflowRun, WorkflowStatusSummary
from app.agent_workflows.state import workflow_store
from app.agent_workflows.workflows import (
    customer_inbox_triage,
    daily_funnel_brief,
    delivery_failure_monitor,
    launch_plan_builder,
    token_benchmark_review,
    weekly_revenue_review,
)
from app.mcp.auth import MCPAuthContext

# Import MCP tools to register tool handlers with the global registry.
# The @mcp_registry.register decorators fire at import time.
import app.mcp.tools  # noqa: F401


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
        ]
        for wf in workflows:
            workflow_registry.register(wf)

    async def run_workflow(
        self,
        workflow_type: str,
        organization_id: str,
        inputs: dict[str, Any],
        auth_ctx: MCPAuthContext,
    ) -> WorkflowRun:
        """Run a workflow by type."""
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
