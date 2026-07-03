"""Experiment Planner workflow — drafts a revenue experiment brief from funnel metrics."""
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
    """Execute the experiment planner workflow."""
    date_range = inputs.get("date_range", "last_7_days")
    step_handlers = [
        {
            "step_name": "build_context_pack",
            "tool_name": "build_context_pack",
            "arguments": lambda: {
                "task_type": "funnel_review",
                "goal": "experiment planner",
                "token_budget": 4000,
                "must_preserve": ["no secrets", "no raw tokens", "prices", "dates"],
            },
        },
        {"step_name": "get_revenue_summary", "tool_name": "get_revenue_summary", "arguments": lambda: {}},
        {"step_name": "get_conversion_summary", "tool_name": "get_conversion_summary", "arguments": lambda: {}},
        {"step_name": "get_checkout_abandonment", "tool_name": "get_checkout_abandonment", "arguments": lambda: {}},
        {
            "step_name": "create_experiment_doc",
            "tool_name": "create_launch_doc",
            "arguments": lambda: {
                "title": f"Experiment Planner - {datetime.now(UTC).strftime('%Y-%m-%d')}",
                "body": (
                    f"Revenue experiment planner for {date_range}.\n\n"
                    "Draft only.\n"
                    "Review revenue, conversion, and checkout abandonment.\n"
                    "Recommend up to 5 operator-reviewed experiments.\n"
                    "Do not change prices or publish content automatically.\n"
                ),
            },
        },
    ]

    run = await runner.run_workflow(
        workflow_type="experiment_planner",
        organization_id=organization_id,
        inputs=inputs,
        auth_ctx=auth_ctx,
        step_handlers=step_handlers,
    )

    for step in run.steps:
        if step.tool_name == "create_launch_doc" and step.status == "completed":
            run.workspace_item_ids.append(f"doc_{_new_id('doc')[:8]}")

    run.output_summary = (
        "Experiment planner completed. Funnel metrics were reviewed and a draft "
        "experiment brief was created for operator approval."
    )
    return run


def definition() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_type="experiment_planner",
        description="Draft a revenue experiment brief from funnel metrics. Never changes prices or publishes.",
        inputs_schema={
            "type": "object",
            "properties": {
                "date_range": {"type": "string", "description": "e.g. 'last_7_days'"},
            },
        },
        outputs_schema={
            "type": "object",
            "properties": {
                "experiment_summary": {"type": "string"},
                "brief_doc_id": {"type": "string"},
            },
        },
        policy=default_workflow_policy("experiment_planner", max_steps=12, token_budget=4000),
        runner_fn=_run,
    )
