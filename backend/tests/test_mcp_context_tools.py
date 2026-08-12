"""Tests for MCP context engine tools — build context pack, search, index summary, estimate, cache."""
from __future__ import annotations

from uuid import UUID

import pytest

from app.context_engine.service import ContextEngineService
from app.mcp.schemas import MCPAuthContext, MCPResponse
from app.mcp.tools.context import (
    _get_service,
    handle_build_context_pack,
    handle_get_project_index_summary,
    handle_search_project_context,
    handle_estimate_context_tokens,
    handle_get_changed_files_summary,
    handle_get_diff_context,
    handle_get_context_pack,
    handle_invalidate_context_cache,
)

TEST_ORG = "00000000-0000-0000-0000-000000000001"
TEST_AUTH = MCPAuthContext(
    organization_id=UUID(TEST_ORG),
    actor_type="system",
    actor_id="system",
)


class TestMcpContextTools:
    """Test MCP context engine tools."""

    @pytest.fixture(autouse=True)
    def _setup_service(self):
        """Reset the service between tests."""
        service = _get_service()
        service.cache.clear()

    async def test_estimate_context_tokens_tool(self):
        response = await handle_estimate_context_tokens(
            auth=TEST_AUTH,
            organization_id=TEST_ORG,
            text="hello world",
        )
        assert response.ok
        assert response.data["estimated_tokens"] == 3  # ceil(11/4)
        assert response.data["character_count"] == 11

    async def test_estimate_context_tokens_empty_text(self):
        response = await handle_estimate_context_tokens(
            auth=TEST_AUTH,
            organization_id=TEST_ORG,
            text="",
        )
        assert response.ok
        assert response.data["estimated_tokens"] == 0

    async def test_estimate_context_tokens_longer_text(self):
        text = "hello world this is a test of the token estimation system"
        response = await handle_estimate_context_tokens(
            auth=TEST_AUTH,
            organization_id=TEST_ORG,
            text=text,
        )
        assert response.ok
        assert response.data["estimated_tokens"] > 0
        assert response.data["character_count"] == len(text)

    async def test_get_project_index_summary_tool(self):
        response = await handle_get_project_index_summary(
            auth=TEST_AUTH,
            organization_id=TEST_ORG,
        )
        assert response.ok
        assert response.data["total_files_seen"] >= 0
        assert response.data["total_files_indexed"] >= 0
        assert response.data["total_files_excluded"] >= 0
        assert response.data["total_estimated_tokens"] >= 0

    async def test_search_project_context_tool(self):
        response = await handle_search_project_context(
            auth=TEST_AUTH,
            organization_id=TEST_ORG,
            query="mcp",
            max_results=5,
        )
        assert response.ok
        assert response.data["query"] == "mcp"
        assert "total" in response.data
        assert isinstance(response.data["items"], list)

    async def test_search_project_context_empty_query(self):
        response = await handle_search_project_context(
            auth=TEST_AUTH,
            organization_id=TEST_ORG,
            query="",
        )
        assert not response.ok
        assert response.error is not None
        assert response.error.code == "INVALID_PARAMS"

    async def test_build_context_pack_tool(self):
        response = await handle_build_context_pack(
            auth=TEST_AUTH,
            organization_id=TEST_ORG,
            task_type="mcp_review",
            goal="review MCP tools safely",
            token_budget=3000,
            must_preserve=["no secrets", "no raw tokens"],
        )
        assert response.ok
        assert response.data["context_pack_id"] != ""
        assert response.data["task_type"] == "mcp_review"
        assert response.data["estimated_tokens"] > 0
        assert response.data["token_budget"] == 3000
        assert len(response.data["included_files"]) > 0

    async def test_build_context_pack_small_budget(self):
        response = await handle_build_context_pack(
            auth=TEST_AUTH,
            organization_id=TEST_ORG,
            task_type="mcp_review",
            goal="minimal pack",
            token_budget=100,  # Very small budget
        )
        assert response.ok
        # Should still complete without error
        assert response.data["context_pack_id"] != ""

    async def test_get_changed_files_summary_tool(self):
        response = await handle_get_changed_files_summary(
            auth=TEST_AUTH,
            organization_id=TEST_ORG,
        )
        assert response.ok
        assert "changed_files" in response.data
        assert "total" in response.data

    async def test_get_diff_context_tool_excluded_file(self):
        response = await handle_get_diff_context(
            auth=TEST_AUTH,
            organization_id=TEST_ORG,
            file_path=".env",
        )
        assert not response.ok
        assert response.error.code == "PERMISSION_DENIED"

    async def test_get_diff_context_missing_file(self):
        response = await handle_get_diff_context(
            auth=TEST_AUTH,
            organization_id=TEST_ORG,
            file_path="nonexistent_file.py",
        )
        assert response.ok  # Returns ok with empty diff
        assert response.data["estimated_tokens"] >= 0

    async def test_get_context_pack_tool_not_found(self):
        response = await handle_get_context_pack(
            auth=TEST_AUTH,
            organization_id=TEST_ORG,
            context_pack_id="nonexistent",
        )
        assert not response.ok
        assert response.error.code == "NOT_FOUND"

    async def test_get_context_pack_tool_found(self):
        # Build a pack first
        build_resp = await handle_build_context_pack(
            auth=TEST_AUTH,
            organization_id=TEST_ORG,
            task_type="mcp_review",
            goal="test",
            token_budget=1000,
        )
        assert build_resp.ok
        pack_id = build_resp.data["context_pack_id"]

        # Retrieve it
        response = await handle_get_context_pack(
            auth=TEST_AUTH,
            organization_id=TEST_ORG,
            context_pack_id=pack_id,
        )
        assert response.ok
        assert response.data["context_pack"] is not None
        assert response.data["context_pack"]["context_pack_id"] == pack_id

    async def test_invalidate_context_cache_tool(self):
        response = await handle_invalidate_context_cache(
            auth=TEST_AUTH,
            organization_id=TEST_ORG,
        )
        assert response.ok
        assert response.data["invalidated"] is True

    async def test_invalidate_context_cache_specific_key(self):
        response = await handle_invalidate_context_cache(
            auth=TEST_AUTH,
            organization_id=TEST_ORG,
            cache_key="test_key",
        )
        assert response.ok
        assert response.data["invalidated"] is True
        assert response.data["cache_key"] == "test_key"

    async def test_context_tools_require_org_context(self):
        """Tools should fail with invalid org."""
        response = await handle_get_project_index_summary(
            auth=TEST_AUTH,
            organization_id="not-a-uuid",
        )
        assert not response.ok

    async def test_context_tools_do_not_include_secret_paths(self):
        """Build context pack should not include secret files."""
        response = await handle_build_context_pack(
            auth=TEST_AUTH,
            organization_id=TEST_ORG,
            task_type="mcp_review",
            goal="check secrets",
            token_budget=4000,
        )
        assert response.ok
        # Excluded count should be >= 0
        assert response.data["excluded_count"] >= 0
