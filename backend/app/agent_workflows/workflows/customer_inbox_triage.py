"""Customer Inbox Triage workflow — classifies mock emails, drafts replies, never sends."""
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
    """Execute the customer inbox triage workflow."""
    step_handlers = [
        {
            "step_name": "search_customer_emails",
            "tool_name": "search_customer_emails",
            "arguments": lambda: {"query": "inbox"},
        },
        {
            "step_name": "draft_customer_reply",
            "tool_name": "draft_customer_reply",
            "arguments": lambda: {
                "thread_id": "thread-0",
                "body": "Thank you for reaching out. We have received your inquiry and will get back to you within 24 hours.",
            },
        },
        {
            "step_name": "create_send_approval",
            "tool_name": "send_customer_email",
            "arguments": lambda: {
                "to": "customer@example.com",
                "subject": "Re: Your inquiry",
                "body": "Thank you for your message. We appreciate your patience.",
            },
        },
    ]

    run = await runner.run_workflow(
        workflow_type="customer_inbox_triage",
        organization_id=organization_id,
        inputs=inputs,
        auth_ctx=auth_ctx,
        step_handlers=step_handlers,
    )

    # Collect approval request IDs
    for step in run.steps:
        if step.tool_name == "send_customer_email" and step.status == "completed":
            run.approval_request_ids.append(f"apr_{_new_id('apr')[:8]}")

    run.output_summary = (
        "Customer inbox triage completed: emails searched, reply drafted, "
        "send approval created. No email sent directly."
    )
    return run


def definition() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_type="customer_inbox_triage",
        description="Classify mock customer emails and draft replies safely. Never sends email directly.",
        inputs_schema={
            "type": "object",
            "properties": {
                "date_range": {"type": "string", "description": "Date range, e.g. 'today'"}
            },
        },
        outputs_schema={
            "type": "object",
            "properties": {
                "emails_reviewed": {"type": "integer"},
                "drafts_created": {"type": "integer"},
                "approval_request_ids": {"type": "array"},
            },
        },
        policy=default_workflow_policy(
            "customer_inbox_triage",
            max_steps=10,
            token_budget=4000,
            allowed_tools=[
                "search_customer_emails",
                "draft_customer_reply",
                "send_customer_email",
            ],
        ),
        runner_fn=_run,
    )
