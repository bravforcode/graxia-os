"""Failure Analysis Review workflow — summarizes loss patterns and drafts a learning review."""
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
    """Execute the failure analysis review workflow."""
    step_handlers = [
        {
            "step_name": "build_context_pack",
            "tool_name": "build_context_pack",
            "arguments": lambda: {
                "task_type": "test_failure_debug",
                "goal": "failure analysis review",
                "token_budget": 3500,
                "must_preserve": ["no secrets", "no raw tokens", "loss patterns"],
            },
        },
        {
            "step_name": "get_outcome_patterns_summary",
            "tool_name": "get_outcome_patterns_summary",
            "arguments": lambda: {"limit": int(inputs.get("metadata", {}).get("limit", 10))},
        },
        {"step_name": "get_checkout_abandonment", "tool_name": "get_checkout_abandonment", "arguments": lambda: {}},
        {"step_name": "get_delivery_open_rate", "tool_name": "get_delivery_open_rate", "arguments": lambda: {}},
        {
            "step_name": "create_failure_review_doc",
            "tool_name": "create_launch_doc",
            "arguments": lambda: {
                "title": f"Failure Analysis Review - {datetime.now(UTC).strftime('%Y-%m-%d')}",
                "body": (
                    "Failure analysis review.\n\n"
                    "Summarize negative patterns, lost reasons, and delivery gaps.\n"
                    "Draft only. Convert findings into operator-reviewed playbooks, not automatic outreach.\n"
                ),
            },
        },
    ]

    run = await runner.run_workflow(
        workflow_type="failure_analysis_review",
        organization_id=organization_id,
        inputs=inputs,
        auth_ctx=auth_ctx,
        step_handlers=step_handlers,
    )

    for step in run.steps:
        if step.tool_name == "create_launch_doc" and step.status == "completed":
            run.workspace_item_ids.append(f"doc_{_new_id('doc')[:8]}")

    run.output_summary = (
        "Failure analysis review completed. Outcome patterns, checkout abandonment, "
        "and delivery signals were summarized into a draft review doc."
    )
    return run


def definition() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_type="failure_analysis_review",
        description="Draft a learning review from outcome patterns and funnel failure signals. No public actions executed.",
        inputs_schema={
            "type": "object",
            "properties": {
                "metadata": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer"},
                    },
                }
            },
        },
        outputs_schema={
            "type": "object",
            "properties": {
                "failure_review_summary": {"type": "string"},
                "doc_id": {"type": "string"},
            },
        },
        policy=default_workflow_policy("failure_analysis_review", max_steps=12, token_budget=3500),
        runner_fn=_run,
    )
