"""Launch Plan Builder workflow — creates mock launch doc, sheet, calendar. Never publishes."""
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
    """Execute the launch plan builder workflow."""
    product_name = inputs.get("product_name", "Digital Product")
    offer_price = inputs.get("offer_price", "$47")

    step_handlers = [
        {
            "step_name": "build_context_pack",
            "tool_name": "build_context_pack",
            "arguments": lambda: {
                "task_type": "workspace_review",
                "goal": "launch plan for digital product",
                "token_budget": 4000,
            },
        },
        {
            "step_name": "list_products",
            "tool_name": "list_products",
            "arguments": lambda: {},
            "required": False,
        },
        {
            "step_name": "create_launch_doc",
            "tool_name": "create_launch_doc",
            "arguments": lambda: {
                "title": f"Launch Plan - {product_name}",
                "body": (
                    f"Launch plan for {product_name} at {offer_price}.\n\n"
                    "## Offer Summary\n"
                    f"Product: {product_name}\n"
                    f"Price: {offer_price}\n\n"
                    "## Sales Page Outline\n"
                    "- Headline with transformation promise\n"
                    "- Problem/Agitate/Solution\n"
                    "- Offer + bonuses\n"
                    "- Testimonials\n"
                    "- Guarantee + CTA\n\n"
                    "## Lead Magnet Idea\n"
                    "Free actionable checklist or cheat sheet\n\n"
                    "## 7-Day Content Plan\n"
                    "- Day 1: Problem post\n"
                    "- Day 2: Story post\n"
                    "- Day 3: Education post\n"
                    "- Day 4: Social proof\n"
                    "- Day 5: Offer preview\n"
                    "- Day 6: Urgency post\n"
                    "- Day 7: Launch + CTA\n\n"
                    "## 100-Outreach Plan\n"
                    "Target DM + email outreach with personalized value-first angle.\n\n"
                    "## Support/Refund Note\n"
                    "30-day money-back guarantee. Support via email within 24h."
                ),
            },
        },
        {
            "step_name": "export_revenue_summary",
            "tool_name": "export_revenue_summary_to_sheet",
            "arguments": lambda: {},
            "required": False,
        },
        {
            "step_name": "create_calendar_plan",
            "tool_name": "create_launch_calendar_plan",
            "arguments": lambda: {
                "summary": f"Launch Plan - {product_name}",
                "description": f"Launch calendar for {product_name} at {offer_price}. Pre-launch: 7 days of content.",
                "start_time": "2026-06-01T09:00:00Z",
                "end_time": "2026-06-08T09:00:00Z",
            },
            "required": False,
        },
    ]

    run = await runner.run_workflow(
        workflow_type="launch_plan_builder",
        organization_id=organization_id,
        inputs=inputs,
        auth_ctx=auth_ctx,
        step_handlers=step_handlers,
    )

    # Collect workspace refs
    for step in run.steps:
        if step.tool_name == "create_launch_doc" and step.status == "completed":
            run.workspace_item_ids.append(f"doc_{_new_id('doc')[:8]}")
        if step.tool_name == "export_revenue_summary_to_sheet" and step.status == "completed":
            run.workspace_item_ids.append(f"sheet_{_new_id('sheet')[:8]}")
        if step.tool_name == "create_launch_calendar_plan" and step.status == "completed":
            run.workspace_item_ids.append(f"calendar_{_new_id('cal')[:8]}")

    run.output_summary = (
        f"Launch plan for {product_name} at {offer_price} created. "
        "Mock doc, optional sheet, and calendar plan generated. No publishing."
    )
    return run


def definition() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_type="launch_plan_builder",
        description="Create a launch plan for a digital product with mock doc, sheet, and calendar plan.",
        inputs_schema={
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "product_name": {"type": "string"},
                "target_customer": {"type": "string"},
                "offer_price": {"type": "string"},
            },
        },
        outputs_schema={
            "type": "object",
            "properties": {
                "launch_doc_id": {"type": "string"},
                "sheet_id": {"type": "string"},
                "calendar_plan_id": {"type": "string"},
            },
        },
        policy=default_workflow_policy("launch_plan_builder", max_steps=20, token_budget=4000),
        runner_fn=_run,
    )
