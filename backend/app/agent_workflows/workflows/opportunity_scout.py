"""Opportunity Scout workflow — surfaces top opportunities and drafts an operator brief."""
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
    """Execute the opportunity scout workflow."""
    step_handlers = [
        {
            "step_name": "build_context_pack",
            "tool_name": "build_context_pack",
            "arguments": lambda: {
                "task_type": "implementation_plan",
                "goal": "opportunity scout brief",
                "token_budget": 3500,
                "must_preserve": ["no secrets", "no raw tokens", "top opportunities only"],
            },
        },
        {
            "step_name": "get_high_score_opportunities",
            "tool_name": "get_high_score_opportunities",
            "arguments": lambda: {
                "threshold": float(inputs.get("metadata", {}).get("threshold", 7.5)),
                "limit": int(inputs.get("metadata", {}).get("limit", 15)),
            },
        },
        {
            "step_name": "create_operator_brief",
            "tool_name": "create_launch_doc",
            "arguments": lambda: {
                "title": f"Opportunity Scout Brief - {datetime.now(UTC).strftime('%Y-%m-%d')}",
                "body": (
                    "Opportunity Scout brief.\n\n"
                    "Review only the highest-scoring opportunities.\n"
                    "Do not submit, publish, or contact anyone directly.\n"
                    "Operator should approve any public-facing follow-up.\n"
                ),
            },
        },
    ]

    run = await runner.run_workflow(
        workflow_type="opportunity_scout",
        organization_id=organization_id,
        inputs=inputs,
        auth_ctx=auth_ctx,
        step_handlers=step_handlers,
    )

    for step in run.steps:
        if step.tool_name == "create_launch_doc" and step.status == "completed":
            run.workspace_item_ids.append(f"doc_{_new_id('doc')[:8]}")

    run.output_summary = (
        "Opportunity scout completed. Top-scoring opportunities were surfaced and "
        "an operator brief draft was created. No submission or outreach executed."
    )
    return run


def definition() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_type="opportunity_scout",
        description="Surface top-scoring opportunities and draft an operator brief. Draft-only, approval-safe.",
        inputs_schema={
            "type": "object",
            "properties": {
                "metadata": {
                    "type": "object",
                    "properties": {
                        "threshold": {"type": "number"},
                        "limit": {"type": "integer"},
                    },
                }
            },
        },
        outputs_schema={
            "type": "object",
            "properties": {
                "opportunity_summary": {"type": "string"},
                "brief_doc_id": {"type": "string"},
            },
        },
        policy=default_workflow_policy("opportunity_scout", max_steps=10, token_budget=3500),
        runner_fn=_run,
    )
