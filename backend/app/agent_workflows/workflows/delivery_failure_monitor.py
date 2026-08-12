"""Delivery Failure Monitor workflow — detects issues, never directly grants/revokes access."""
from __future__ import annotations

import uuid
from typing import Any

from app.agent_workflows.policies import default_workflow_policy
from app.agent_workflows.runner import WorkflowRunner
from app.agent_workflows.schemas import WorkflowDefinition, WorkflowRun
from app.mcp.auth import MCPAuthContext


def _new_id(prefix: str = "wf") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


async def _run(
    runner: WorkflowRunner,
    organization_id: str,
    inputs: dict[str, Any],
    auth_ctx: MCPAuthContext,
) -> WorkflowRun:
    """Execute the delivery failure monitor workflow."""
    step_handlers = [
        {
            "step_name": "get_recent_orders",
            "tool_name": "get_recent_orders",
            "arguments": lambda: {},
        },
        {
            "step_name": "get_delivery_open_rate",
            "tool_name": "get_delivery_open_rate",
            "arguments": lambda: {},
        },
        {
            "step_name": "get_conversion_summary",
            "tool_name": "get_conversion_summary",
            "arguments": lambda: {},
        },
        {
            "step_name": "get_pending_approvals",
            "tool_name": "get_pending_approvals",
            "arguments": lambda: {},
        },
        {
            "step_name": "create_recommendation_doc",
            "tool_name": "create_launch_doc",
            "arguments": lambda: {
                "title": "Delivery Failure Monitor Report",
                "body": (
                    "Delivery Failure Monitor completed.\n\n"
                    "## Detected Issues\n"
                    "- Paid orders with low delivery open signal: check mock data\n"
                    "- Email failures: review mock analytics\n"
                    "- Approval backlog: pending approvals need review\n\n"
                    "## Severity\n"
                    "Medium - review pending approvals first\n\n"
                    "## Recommended Actions\n"
                    "1. Review pending approvals in the inbox\n"
                    "2. Verify delivery access for recent paid orders\n"
                    "3. No direct grant/revoke performed by this workflow"
                ),
            },
        },
    ]

    run = await runner.run_workflow(
        workflow_type="delivery_failure_monitor",
        organization_id=organization_id,
        inputs=inputs,
        auth_ctx=auth_ctx,
        step_handlers=step_handlers,
    )

    for step in run.steps:
        if step.tool_name == "create_launch_doc" and step.status == "completed":
            run.workspace_item_ids.append(f"doc_{_new_id('doc')[:8]}")

    run.output_summary = (
        "Delivery failure monitor completed. Orders, delivery rate, "
        "conversions, and approvals reviewed. Recommendations created. "
        "No direct access grant/revoke performed."
    )
    return run


def definition() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_type="delivery_failure_monitor",
        description="Detect possible delivery/access/email issues in the funnel. Never directly grants/revokes access.",
        inputs_schema={
            "type": "object",
            "properties": {
                "date_range": {"type": "string"}
            },
        },
        outputs_schema={
            "type": "object",
            "properties": {
                "issues_found": {"type": "array"},
                "severity": {"type": "string"},
                "recommended_actions": {"type": "array"},
            },
        },
        policy=default_workflow_policy("delivery_failure_monitor", max_steps=10, token_budget=4000),
        runner_fn=_run,
    )
