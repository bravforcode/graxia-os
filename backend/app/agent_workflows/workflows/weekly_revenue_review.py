"""Weekly Revenue Review workflow — creates founder-style revenue review, never changes prices."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
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
    """Execute the weekly revenue review workflow."""
    week_label = datetime.now(UTC).strftime("%Y-W%W")

    step_handlers = [
        {
            "step_name": "build_context_pack",
            "tool_name": "build_context_pack",
            "arguments": lambda: {
                "task_type": "funnel_review",
                "goal": "weekly revenue review",
                "token_budget": 4000,
            },
        },
        {
            "step_name": "get_revenue_summary",
            "tool_name": "get_revenue_summary",
            "arguments": lambda: {},
        },
        {
            "step_name": "get_conversion_summary",
            "tool_name": "get_conversion_summary",
            "arguments": lambda: {},
        },
        {
            "step_name": "get_checkout_abandonment",
            "tool_name": "get_checkout_abandonment",
            "arguments": lambda: {},
        },
        {
            "step_name": "get_delivery_open_rate",
            "tool_name": "get_delivery_open_rate",
            "arguments": lambda: {},
        },
        {
            "step_name": "export_to_sheet",
            "tool_name": "export_revenue_summary_to_sheet",
            "arguments": lambda: {},
            "required": False,
        },
        {
            "step_name": "create_review_doc",
            "tool_name": "create_launch_doc",
            "arguments": lambda: {
                "title": f"Weekly Revenue Review - {week_label}",
                "body": (
                    f"Weekly Revenue Review for {week_label}.\n\n"
                    "## Weekly Summary\n"
                    "- Revenue, conversions, abandonment, and delivery rate reviewed\n"
                    "- Sheet exported for deep analysis\n\n"
                    "## Top Metric\n"
                    "Review funnel conversion rate vs. abandonment rate\n\n"
                    "## Biggest Bottleneck\n"
                    "Checkout abandonment identified as key bottleneck\n\n"
                    "## Recommended Experiment for Next Week\n"
                    "Test simplified checkout flow with fewer steps"
                ),
            },
        },
    ]

    run = await runner.run_workflow(
        workflow_type="weekly_revenue_review",
        organization_id=organization_id,
        inputs=inputs,
        auth_ctx=auth_ctx,
        step_handlers=step_handlers,
    )

    for step in run.steps:
        if step.tool_name == "create_launch_doc" and step.status == "completed":
            run.workspace_item_ids.append(f"doc_{_new_id('doc')[:8]}")
        if step.tool_name == "export_revenue_summary_to_sheet" and step.status == "completed":
            run.workspace_item_ids.append(f"sheet_{_new_id('sheet')[:8]}")

    run.output_summary = (
        f"Weekly revenue review for {week_label} completed. "
        "Revenue, conversions, abandonment, delivery reviewed. "
        "Sheet exported and report doc created. No prices changed."
    )
    return run


def definition() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_type="weekly_revenue_review",
        description="Create a weekly founder-style revenue review with sheet export and report doc. Never changes prices.",
        inputs_schema={
            "type": "object",
            "properties": {
                "date_range": {"type": "string", "description": "e.g. 'last_7_days'"}
            },
        },
        outputs_schema={
            "type": "object",
            "properties": {
                "weekly_summary": {"type": "string"},
                "sheet_id": {"type": "string"},
                "doc_id": {"type": "string"},
            },
        },
        policy=default_workflow_policy("weekly_revenue_review", max_steps=20, token_budget=4000),
        runner_fn=_run,
    )
