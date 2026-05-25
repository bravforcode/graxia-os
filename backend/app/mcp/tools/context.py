"""MCP context engine tools — build/search/index/diff/estimate context packs.

All tools are READ_ONLY except invalidate_context_cache (LOW_WRITE).
Require MCPAuthContext and organization_id.
Never include secret files. Never read .env or keys.
"""
from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from app.context_engine.service import ContextEngineService
from app.mcp.auth import safe_org_not_found, validate_org_context
from app.mcp.registry import mcp_registry
from app.mcp.schemas import MCPAuthContext, MCPResponse

logger = logging.getLogger(__name__)

# Shared service instance (lazy init, no secret access)
_service: ContextEngineService | None = None


def _get_service() -> ContextEngineService:
    """Get or create the context engine service."""
    global _service
    if _service is None:
        _service = ContextEngineService()
    return _service


async def _resolve_org(
    auth: MCPAuthContext | None,
    organization_id: str,
    request_id: str = "",
) -> UUID | None:
    """Validate organization_id and auth context. Returns UUID or None on error."""
    try:
        org_uuid = UUID(organization_id)
    except (ValueError, TypeError):
        return None

    try:
        if not validate_org_context(auth, org_uuid):
            safe_org_not_found()
    except PermissionError:
        return None

    return org_uuid


def _error_response(
    code: str,
    message: str,
    request_id: str = "",
    organization_id: str = "",
) -> MCPResponse:
    return MCPResponse.error_response(
        code=code,
        message=message,
        request_id=request_id,
        organization_id=organization_id,
    )


# ── Common schemas ────────────────────────────────────────────────────────────

TOOL_INPUT_ORG_ONLY = {
    "type": "object",
    "properties": {
        "organization_id": {"type": "string", "description": "UUID of the organization"},
    },
    "required": ["organization_id"],
    "additionalProperties": False,
}


# ── Tool: build_context_pack ──────────────────────────────────────────────────


@mcp_registry.register(
    name="build_context_pack",
    description="Build a token-efficient context pack for a task type. Selects relevant files within a token budget. Never includes secret files.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "task_type": {
                "type": "string",
                "description": "Task type: funnel_review, mcp_review, workspace_review, context_engine_review, security_review, test_failure_debug, implementation_plan, release_review",
                "default": "mcp_review",
            },
            "goal": {"type": "string", "description": "Goal description for the context pack"},
            "token_budget": {"type": "integer", "description": "Maximum tokens for the context pack", "default": 4000},
            "query": {"type": "string", "description": "Optional keyword query", "default": ""},
            "include_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional specific file paths to include",
                "default": [],
            },
            "must_preserve": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Critical rules that must be preserved",
                "default": ["no secrets", "no raw tokens"],
            },
        },
        "required": ["organization_id"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "context_pack_id": {"type": "string"},
            "task_type": {"type": "string"},
            "goal": {"type": "string"},
            "estimated_tokens": {"type": "integer"},
            "token_budget": {"type": "integer"},
            "included_files": {"type": "array", "items": {"type": "object"}},
            "excluded_count": {"type": "integer"},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "cache_key": {"type": "string"},
        },
        "additionalProperties": False,
    },
    risk_level="READ_ONLY",
)
async def handle_build_context_pack(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    task_type: str = "mcp_review",
    goal: str = "",
    token_budget: int = 4000,
    query: str = "",
    include_paths: list[str] | None = None,
    must_preserve: list[str] | None = None,
) -> MCPResponse:
    """Build a context pack for the given task type."""
    request_id = auth.request_id if auth else ""

    org_uuid = await _resolve_org(auth, organization_id, request_id)
    if org_uuid is None:
        return _error_response(
            "INVALID_PARAMS", "Invalid organization_id.",
            request_id=request_id, organization_id=organization_id,
        )

    try:
        service = _get_service()
        pack = service.build_context_pack(
            task_type=task_type,
            goal=goal or f"Context pack for {task_type}",
            token_budget=token_budget,
            query=query if query else None,
            include_paths=include_paths if include_paths else None,
            must_preserve=must_preserve or ["no secrets", "no raw tokens"],
        )

        return MCPResponse.ok_response(
            data={
                "context_pack_id": pack.context_pack_id,
                "task_type": pack.task_type,
                "goal": pack.goal,
                "estimated_tokens": pack.estimated_tokens,
                "token_budget": pack.token_budget,
                "included_files": [
                    {
                        "path": f.path,
                        "content_mode": f.content_mode,
                        "estimated_tokens": f.estimated_tokens,
                        "inclusion_reason": f.inclusion_reason,
                    }
                    for f in pack.included_files[:20]
                ],
                "excluded_count": len(pack.excluded_files),
                "warnings": pack.warnings,
                "cache_key": pack.cache_key,
            },
            organization_id=organization_id,
            estimated_tokens=pack.estimated_tokens,
            request_id=request_id,
        )
    except Exception as exc:
        logger.warning("build_context_pack error: %s", exc)
        return _error_response(
            "HANDLER_ERROR", "Context pack build error.",
            request_id=request_id, organization_id=organization_id,
        )


# ── Tool: search_project_context ──────────────────────────────────────────────


@mcp_registry.register(
    name="search_project_context",
    description="Search project files by keyword. Returns matching files with summaries and estimated tokens.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "query": {"type": "string", "description": "Search keyword"},
            "max_results": {"type": "integer", "description": "Maximum results to return", "default": 10},
        },
        "required": ["organization_id", "query"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "items": {"type": "array", "items": {"type": "object"}},
            "total": {"type": "integer"},
        },
        "additionalProperties": False,
    },
    risk_level="READ_ONLY",
)
async def handle_search_project_context(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    query: str = "",
    max_results: int = 10,
) -> MCPResponse:
    """Search project context by keyword."""
    request_id = auth.request_id if auth else ""

    org_uuid = await _resolve_org(auth, organization_id, request_id)
    if org_uuid is None:
        return _error_response(
            "INVALID_PARAMS", "Invalid organization_id.",
            request_id=request_id, organization_id=organization_id,
        )

    if not query:
        return _error_response(
            "INVALID_PARAMS", "Query is required.",
            request_id=request_id, organization_id=organization_id,
        )

    try:
        service = _get_service()
        items = service.search_context(query=query, max_results=max_results)

        return MCPResponse.ok_response(
            data={
                "query": query,
                "items": items,
                "total": len(items),
            },
            organization_id=organization_id,
            estimated_tokens=max(10, len(items) * 15),
            request_id=request_id,
        )
    except Exception as exc:
        logger.warning("search_project_context error: %s", exc)
        return _error_response(
            "HANDLER_ERROR", "Search error.",
            request_id=request_id, organization_id=organization_id,
        )


# ── Tool: get_project_index_summary ───────────────────────────────────────────


@mcp_registry.register(
    name="get_project_index_summary",
    description="Get summary of the current project index — total files, excluded, estimated tokens, top categories.",
    input_schema=TOOL_INPUT_ORG_ONLY,
    output_schema={
        "type": "object",
        "properties": {
            "total_files_seen": {"type": "integer"},
            "total_files_indexed": {"type": "integer"},
            "total_files_excluded": {"type": "integer"},
            "total_estimated_tokens": {"type": "integer"},
            "top_categories": {"type": "object"},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
    },
    risk_level="READ_ONLY",
)
async def handle_get_project_index_summary(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
) -> MCPResponse:
    """Get project index summary."""
    request_id = auth.request_id if auth else ""

    org_uuid = await _resolve_org(auth, organization_id, request_id)
    if org_uuid is None:
        return _error_response(
            "INVALID_PARAMS", "Invalid organization_id.",
            request_id=request_id, organization_id=organization_id,
        )

    try:
        service = _get_service()
        summary = service.get_index_summary()

        return MCPResponse.ok_response(
            data=summary,
            organization_id=organization_id,
            estimated_tokens=30,
            request_id=request_id,
        )
    except Exception as exc:
        logger.warning("get_project_index_summary error: %s", exc)
        return _error_response(
            "HANDLER_ERROR", "Index summary error.",
            request_id=request_id, organization_id=organization_id,
        )


# ── Tool: get_changed_files_summary ───────────────────────────────────────────


@mcp_registry.register(
    name="get_changed_files_summary",
    description="Get summary of changed files from git (unstaged + uncommitted).",
    input_schema=TOOL_INPUT_ORG_ONLY,
    output_schema={
        "type": "object",
        "properties": {
            "changed_files": {"type": "array", "items": {"type": "string"}},
            "total": {"type": "integer"},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
    },
    risk_level="READ_ONLY",
)
async def handle_get_changed_files_summary(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
) -> MCPResponse:
    """Get changed files summary."""
    request_id = auth.request_id if auth else ""

    org_uuid = await _resolve_org(auth, organization_id, request_id)
    if org_uuid is None:
        return _error_response(
            "INVALID_PARAMS", "Invalid organization_id.",
            request_id=request_id, organization_id=organization_id,
        )

    try:
        service = _get_service()
        changed = service.get_changed_files()
        warnings = []
        if not service.diff_protocol.is_git_available:
            warnings.append("Git is not available. No diff data.")

        return MCPResponse.ok_response(
            data={
                "changed_files": changed,
                "total": len(changed),
                "warnings": warnings,
            },
            organization_id=organization_id,
            estimated_tokens=20,
            request_id=request_id,
        )
    except Exception as exc:
        logger.warning("get_changed_files_summary error: %s", exc)
        return _error_response(
            "HANDLER_ERROR", "Changed files error.",
            request_id=request_id, organization_id=organization_id,
        )


# ── Tool: get_diff_context ────────────────────────────────────────────────────


@mcp_registry.register(
    name="get_diff_context",
    description="Get diff context for a specific file. Returns diff summary and diff text within token limit.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "file_path": {"type": "string", "description": "File path relative to project root"},
            "max_tokens": {"type": "integer", "description": "Maximum tokens for diff output", "default": 2000},
        },
        "required": ["organization_id", "file_path"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "estimated_tokens": {"type": "integer"},
            "diff_summary": {"type": "string"},
            "diff_text": {"type": "string"},
            "truncated": {"type": "boolean"},
        },
        "additionalProperties": False,
    },
    risk_level="READ_ONLY",
)
async def handle_get_diff_context(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    file_path: str = "",
    max_tokens: int = 2000,
) -> MCPResponse:
    """Get diff context for a file."""
    request_id = auth.request_id if auth else ""

    org_uuid = await _resolve_org(auth, organization_id, request_id)
    if org_uuid is None:
        return _error_response(
            "INVALID_PARAMS", "Invalid organization_id.",
            request_id=request_id, organization_id=organization_id,
        )

    if not file_path:
        return _error_response(
            "INVALID_PARAMS", "file_path is required.",
            request_id=request_id, organization_id=organization_id,
        )

    # Security: never show diffs for excluded files
    from app.context_engine.exclusions import ExclusionPolicy
    excluded, reason = ExclusionPolicy().should_exclude(Path(file_path))
    if excluded:
        return _error_response(
            "PERMISSION_DENIED", "File is excluded from context.",
            request_id=request_id, organization_id=organization_id,
        )

    try:
        service = _get_service()
        diff = service.get_diff_context(file_path)
        if diff is None:
            # Check if git is available
            if not service.diff_protocol.is_git_available:
                return _error_response(
                    "SERVICE_UNAVAILABLE", "Git is not available for diff operations.",
                    request_id=request_id, organization_id=organization_id,
                )
            return MCPResponse.ok_response(
                data={
                    "path": file_path,
                    "estimated_tokens": 0,
                    "diff_summary": "No changes detected.",
                    "diff_text": "",
                    "truncated": False,
                },
                organization_id=organization_id,
                estimated_tokens=10,
                request_id=request_id,
            )

        return MCPResponse.ok_response(
            data=diff,
            organization_id=organization_id,
            estimated_tokens=diff.get("estimated_tokens", 0),
            request_id=request_id,
        )
    except Exception as exc:
        logger.warning("get_diff_context error: %s", exc)
        return _error_response(
            "HANDLER_ERROR", "Diff context error.",
            request_id=request_id, organization_id=organization_id,
        )


# ── Tool: estimate_context_tokens ─────────────────────────────────────────────


@mcp_registry.register(
    name="estimate_context_tokens",
    description="Estimate tokens for a text string. Uses deterministic heuristic (ceil(character_count/4)).",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "text": {"type": "string", "description": "Text to estimate tokens for"},
        },
        "required": ["organization_id", "text"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "estimated_tokens": {"type": "integer"},
            "character_count": {"type": "integer"},
        },
        "additionalProperties": False,
    },
    risk_level="READ_ONLY",
)
async def handle_estimate_context_tokens(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    text: str = "",
) -> MCPResponse:
    """Estimate tokens for a text string."""
    request_id = auth.request_id if auth else ""

    org_uuid = await _resolve_org(auth, organization_id, request_id)
    if org_uuid is None:
        return _error_response(
            "INVALID_PARAMS", "Invalid organization_id.",
            request_id=request_id, organization_id=organization_id,
        )

    if not text:
        return MCPResponse.ok_response(
            data={"estimated_tokens": 0, "character_count": 0},
            organization_id=organization_id,
            estimated_tokens=5,
            request_id=request_id,
        )

    try:
        service = _get_service()
        result = service.estimate_tokens(text)

        return MCPResponse.ok_response(
            data=result,
            organization_id=organization_id,
            estimated_tokens=5,
            request_id=request_id,
        )
    except Exception as exc:
        logger.warning("estimate_context_tokens error: %s", exc)
        return _error_response(
            "HANDLER_ERROR", "Token estimation error.",
            request_id=request_id, organization_id=organization_id,
        )


# ── Tool: get_context_pack ────────────────────────────────────────────────────


@mcp_registry.register(
    name="get_context_pack",
    description="Get a previously built context pack by its ID.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "context_pack_id": {"type": "string", "description": "ID of the context pack to retrieve"},
        },
        "required": ["organization_id", "context_pack_id"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "context_pack": {"type": "object"},
        },
        "additionalProperties": False,
    },
    risk_level="READ_ONLY",
)
async def handle_get_context_pack(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    context_pack_id: str = "",
) -> MCPResponse:
    """Get a context pack by ID from cache."""
    request_id = auth.request_id if auth else ""

    org_uuid = await _resolve_org(auth, organization_id, request_id)
    if org_uuid is None:
        return _error_response(
            "INVALID_PARAMS", "Invalid organization_id.",
            request_id=request_id, organization_id=organization_id,
        )

    if not context_pack_id:
        return _error_response(
            "INVALID_PARAMS", "context_pack_id is required.",
            request_id=request_id, organization_id=organization_id,
        )

    try:
        service = _get_service()
        pack = service.get_context_pack(context_pack_id)
        if pack is None:
            return _error_response(
                "NOT_FOUND", "Context pack not found.",
                request_id=request_id, organization_id=organization_id,
            )

        return MCPResponse.ok_response(
            data={
                "context_pack": {
                    "context_pack_id": pack.context_pack_id,
                    "task_type": pack.task_type,
                    "goal": pack.goal,
                    "token_budget": pack.token_budget,
                    "estimated_tokens": pack.estimated_tokens,
                    "generated_at": pack.generated_at,
                    "included_files": [
                        {
                            "path": f.path,
                            "content_mode": f.content_mode,
                            "estimated_tokens": f.estimated_tokens,
                        }
                        for f in pack.included_files
                    ],
                    "warnings": pack.warnings,
                },
            },
            organization_id=organization_id,
            estimated_tokens=30,
            request_id=request_id,
        )
    except Exception as exc:
        logger.warning("get_context_pack error: %s", exc)
        return _error_response(
            "HANDLER_ERROR", "Context pack retrieval error.",
            request_id=request_id, organization_id=organization_id,
        )


# ── Tool: invalidate_context_cache ────────────────────────────────────────────


@mcp_registry.register(
    name="invalidate_context_cache",
    description="Invalidate context cache. If cache_key is provided, invalidate only that entry. Otherwise invalidate all.",
    input_schema={
        "type": "object",
        "properties": {
            "organization_id": {"type": "string", "description": "UUID of the organization"},
            "cache_key": {"type": "string", "description": "Optional specific cache key to invalidate", "default": ""},
        },
        "required": ["organization_id"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "invalidated": {"type": "boolean"},
            "cache_key": {"type": "string"},
        },
        "additionalProperties": False,
    },
    risk_level="LOW_WRITE",
)
async def handle_invalidate_context_cache(
    auth: MCPAuthContext | None = None,
    organization_id: str = "",
    cache_key: str = "",
) -> MCPResponse:
    """Invalidate context cache."""
    request_id = auth.request_id if auth else ""

    org_uuid = await _resolve_org(auth, organization_id, request_id)
    if org_uuid is None:
        return _error_response(
            "INVALID_PARAMS", "Invalid organization_id.",
            request_id=request_id, organization_id=organization_id,
        )

    try:
        service = _get_service()
        result = service.invalidate_cache(cache_key if cache_key else None)

        return MCPResponse.ok_response(
            data=result,
            organization_id=organization_id,
            estimated_tokens=10,
            request_id=request_id,
        )
    except Exception as exc:
        logger.warning("invalidate_context_cache error: %s", exc)
        return _error_response(
            "HANDLER_ERROR", "Cache invalidation error.",
            request_id=request_id, organization_id=organization_id,
        )
