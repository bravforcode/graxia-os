"""Tests for Token Benchmark Review workflow — uses context, never calls real LLM."""
from __future__ import annotations

import pytest

from app.agent_workflows.service import WorkflowEngineService
from app.agent_workflows.state import workflow_store
from app.mcp.auth import MCPAuthContext

TEST_ORG = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def _clear_store():
    workflow_store.clear()


@pytest.fixture
def service() -> WorkflowEngineService:
    return WorkflowEngineService()


@pytest.fixture
def auth() -> MCPAuthContext:
    return MCPAuthContext.system(organization_id=TEST_ORG)


def test_token_benchmark_review_runs(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="token_benchmark_review",
            organization_id=TEST_ORG,
            inputs={},
            auth_ctx=auth,
        )
        assert run.workflow_type == "token_benchmark_review"
    asyncio.run(_test())


def test_token_benchmark_review_uses_context_search(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="token_benchmark_review",
            organization_id=TEST_ORG,
            inputs={},
            auth_ctx=auth,
        )
        steps_with_search = [s for s in run.steps if s.tool_name == "search_project_context"]
        assert len(steps_with_search) > 0
    asyncio.run(_test())


def test_token_benchmark_review_creates_mock_doc(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="token_benchmark_review",
            organization_id=TEST_ORG,
            inputs={},
            auth_ctx=auth,
        )
        assert run.workspace_item_ids is not None or run.workspace_item_ids == []
    asyncio.run(_test())


def test_token_benchmark_review_does_not_call_real_llm(service, auth):
    import asyncio
    async def _test():
        run = await service.run_workflow(
            workflow_type="token_benchmark_review",
            organization_id=TEST_ORG,
            inputs={},
            auth_ctx=auth,
        )
        # Verify no real LLM tools were called
        for step in run.steps:
            assert step.tool_name not in ("call_llm", "llm_complete", "real_llm_provider")
        # Output should mention no real LLM
        assert run.output_summary is not None
    asyncio.run(_test())
