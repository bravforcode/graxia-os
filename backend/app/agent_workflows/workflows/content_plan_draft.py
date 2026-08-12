"""Content Plan Draft workflow — prepares a draft content plan and mock calendar milestone."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
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
    """Execute the content plan draft workflow."""
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(days=1)
    end = start + timedelta(hours=1)
    step_handlers = [
        {
            "step_name": "build_context_pack",
            "tool_name": "build_context_pack",
            "arguments": lambda: {
                "task_type": "workspace_review",
                "goal": "content plan draft",
                "token_budget": 3500,
                "must_preserve": ["no secrets", "no raw tokens", "dates"],
            },
        },
        {"step_name": "get_revenue_summary", "tool_name": "get_revenue_summary", "arguments": lambda: {}},
        {"step_name": "get_conversion_summary", "tool_name": "get_conversion_summary", "arguments": lambda: {}},
        {
            "step_name": "create_calendar_plan",
            "tool_name": "create_launch_calendar_plan",
            "arguments": lambda: {
                "summary": f"Draft Content Plan Review - {start.strftime('%Y-%m-%d')}",
                "description": "Mock milestone for operator review of the draft content plan.",
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
            },
        },
        {
            "step_name": "create_content_doc",
            "tool_name": "create_launch_doc",
            "arguments": lambda: {
                "title": f"Content Plan Draft - {datetime.now(UTC).strftime('%Y-%m-%d')}",
                "body": (
                    "Content plan draft.\n\n"
                    "Use funnel metrics to prioritize the top 15% content opportunities.\n"
                    "Draft only. Operator approval required before any public posting.\n"
                ),
            },
        },
    ]

    run = await runner.run_workflow(
        workflow_type="content_plan_draft",
        organization_id=organization_id,
        inputs=inputs,
        auth_ctx=auth_ctx,
        step_handlers=step_handlers,
    )

    for step in run.steps:
        if step.tool_name == "create_launch_doc" and step.status == "completed":
            run.workspace_item_ids.append(f"doc_{_new_id('doc')[:8]}")
        if step.tool_name == "create_launch_calendar_plan" and step.status == "completed":
            run.workspace_item_ids.append(f"calendar_{_new_id('cal')[:8]}")

    run.output_summary = (
        "Content plan draft completed. A draft content brief and mock calendar milestone "
        "were created. No public posting executed."
    )
    return run


def definition() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_type="content_plan_draft",
        description="Draft a content plan and mock calendar milestone from funnel metrics. Approval-safe and publish-free.",
        inputs_schema={"type": "object", "properties": {}},
        outputs_schema={
            "type": "object",
            "properties": {
                "content_plan_summary": {"type": "string"},
                "doc_id": {"type": "string"},
                "calendar_item_id": {"type": "string"},
            },
        },
        policy=default_workflow_policy("content_plan_draft", max_steps=12, token_budget=3500),
        runner_fn=_run,
    )
