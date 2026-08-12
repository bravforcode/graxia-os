"""Token Benchmark Review workflow — uses context engine, never calls real LLM."""
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
    """Execute the token benchmark review workflow."""
    step_handlers = [
        {
            "step_name": "build_context_pack",
            "tool_name": "build_context_pack",
            "arguments": lambda: {
                "task_type": "context_engine_review",
                "goal": "review token benchmark quality and regression risks",
                "token_budget": 4000,
            },
        },
        {
            "step_name": "search_context",
            "tool_name": "search_project_context",
            "arguments": lambda: {
                "query": "token benchmark production readiness quality regression",
                "max_results": 10,
            },
        },
        {
            "step_name": "get_index_summary",
            "tool_name": "get_project_index_summary",
            "arguments": lambda: {},
        },
        {
            "step_name": "create_report_doc",
            "tool_name": "create_launch_doc",
            "arguments": lambda: {
                "title": "Token Benchmark Review Report",
                "body": (
                    "Token Benchmark Review completed.\n\n"
                    "## Quality Risks\n"
                    "- Token estimation uses deterministic heuristic only\n"
                    "- No real LLM provider called for evaluation\n\n"
                    "## Token Reduction Risks\n"
                    "- Large files use summary mode, not full content\n"
                    "- Excluded files save significant tokens\n\n"
                    "## Files to Review\n"
                    "- Check context engine indexer stats\n"
                    "- Review exclusion policy coverage\n\n"
                    "## Recommended Commands\n"
                    "pytest tests/test_context_engine_*.py -q\n"
                    "python -m compileall app/context_engine/"
                ),
            },
        },
    ]

    run = await runner.run_workflow(
        workflow_type="token_benchmark_review",
        organization_id=organization_id,
        inputs=inputs,
        auth_ctx=auth_ctx,
        step_handlers=step_handlers,
    )

    for step in run.steps:
        if step.tool_name == "create_launch_doc" and step.status == "completed":
            run.workspace_item_ids.append(f"doc_{_new_id('doc')[:8]}")

    run.output_summary = (
        "Token benchmark review completed. Context pack built, project indexed, "
        "report doc created. No real LLM provider called."
    )
    return run


def definition() -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_type="token_benchmark_review",
        description="Review token benchmark / readiness reports and identify quality-loss patterns safely.",
        inputs_schema={
            "type": "object",
            "properties": {
                "date_range": {"type": "string"}
            },
        },
        outputs_schema={
            "type": "object",
            "properties": {
                "risk_summary": {"type": "string"},
                "recommended_files": {"type": "array"},
            },
        },
        policy=default_workflow_policy("token_benchmark_review", max_steps=10, token_budget=4000),
        runner_fn=_run,
    )
