"""MCP dangerous blocked tools — always blocked and cannot be executed.

These tools return a DANGEROUS_TOOL_BLOCKED response immediately.
They are registered so they show up in tool listings but can never be called.
"""
from __future__ import annotations

import logging

from app.mcp.registry import mcp_registry
from app.mcp.schemas import MCPResponse, MCPAuthContext
from app.mcp.errors import ERR_DANGEROUS_BLOCKED

logger = logging.getLogger(__name__)

TOOL_INPUT_DANGEROUS = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

TOOL_OUTPUT_BLOCKED = {
    "type": "object",
    "properties": {
        "blocked": {"type": "boolean"},
        "code": {"type": "string"},
        "message": {"type": "string"},
    },
    "required": ["blocked", "code"],
    "additionalProperties": False,
}


def _blocked_response(request_id: str = "", organization_id: str = "") -> MCPResponse:
    """Build a standard blocked response."""
    return MCPResponse.error_response(
        code=ERR_DANGEROUS_BLOCKED,
        message="This tool is intentionally blocked for safety.",
        safe_to_retry=False,
        request_id=request_id,
        organization_id=organization_id,
    )


# ── Deployment Tools ──────────────────────────────────────────────────────────


@mcp_registry.register(
    name="deploy_production",
    description="[DANGEROUS — BLOCKED] Deploy to production.",
    input_schema=TOOL_INPUT_DANGEROUS,
    output_schema=TOOL_OUTPUT_BLOCKED,
    risk_level="DANGEROUS_BLOCKED",
)
async def handle_deploy_production(
    auth: MCPAuthContext | None = None,
    **kwargs: object,
) -> MCPResponse:
    """Always blocked."""
    return _blocked_response(
        request_id=auth.request_id if auth else "",
        organization_id=str(auth.organization_id) if auth and auth.organization_id else "",
    )


# ── Secrets Tools ─────────────────────────────────────────────────────────────


@mcp_registry.register(
    name="read_env",
    description="[DANGEROUS — BLOCKED] Read environment variables.",
    input_schema=TOOL_INPUT_DANGEROUS,
    output_schema=TOOL_OUTPUT_BLOCKED,
    risk_level="DANGEROUS_BLOCKED",
)
async def handle_read_env(
    auth: MCPAuthContext | None = None,
    **kwargs: object,
) -> MCPResponse:
    """Always blocked."""
    return _blocked_response(
        request_id=auth.request_id if auth else "",
        organization_id=str(auth.organization_id) if auth and auth.organization_id else "",
    )


@mcp_registry.register(
    name="print_secrets",
    description="[DANGEROUS — BLOCKED] Print secrets to output.",
    input_schema=TOOL_INPUT_DANGEROUS,
    output_schema=TOOL_OUTPUT_BLOCKED,
    risk_level="DANGEROUS_BLOCKED",
)
async def handle_print_secrets(
    auth: MCPAuthContext | None = None,
    **kwargs: object,
) -> MCPResponse:
    """Always blocked."""
    return _blocked_response(
        request_id=auth.request_id if auth else "",
        organization_id=str(auth.organization_id) if auth and auth.organization_id else "",
    )


@mcp_registry.register(
    name="rotate_keys",
    description="[DANGEROUS — BLOCKED] Rotate API keys.",
    input_schema=TOOL_INPUT_DANGEROUS,
    output_schema=TOOL_OUTPUT_BLOCKED,
    risk_level="DANGEROUS_BLOCKED",
)
async def handle_rotate_keys(
    auth: MCPAuthContext | None = None,
    **kwargs: object,
) -> MCPResponse:
    """Always blocked."""
    return _blocked_response(
        request_id=auth.request_id if auth else "",
        organization_id=str(auth.organization_id) if auth and auth.organization_id else "",
    )


# ── Database Tools ────────────────────────────────────────────────────────────


@mcp_registry.register(
    name="delete_database",
    description="[DANGEROUS — BLOCKED] Delete or drop the database.",
    input_schema=TOOL_INPUT_DANGEROUS,
    output_schema=TOOL_OUTPUT_BLOCKED,
    risk_level="DANGEROUS_BLOCKED",
)
async def handle_delete_database(
    auth: MCPAuthContext | None = None,
    **kwargs: object,
) -> MCPResponse:
    """Always blocked."""
    return _blocked_response(
        request_id=auth.request_id if auth else "",
        organization_id=str(auth.organization_id) if auth and auth.organization_id else "",
    )


# ── Git Tools ─────────────────────────────────────────────────────────────────


@mcp_registry.register(
    name="force_push",
    description="[DANGEROUS — BLOCKED] Force push to git remote.",
    input_schema=TOOL_INPUT_DANGEROUS,
    output_schema=TOOL_OUTPUT_BLOCKED,
    risk_level="DANGEROUS_BLOCKED",
)
async def handle_force_push(
    auth: MCPAuthContext | None = None,
    **kwargs: object,
) -> MCPResponse:
    """Always blocked."""
    return _blocked_response(
        request_id=auth.request_id if auth else "",
        organization_id=str(auth.organization_id) if auth and auth.organization_id else "",
    )


# ── Stripe Tools ──────────────────────────────────────────────────────────────


@mcp_registry.register(
    name="change_stripe_secret_config",
    description="[DANGEROUS — BLOCKED] Change Stripe secret configuration.",
    input_schema=TOOL_INPUT_DANGEROUS,
    output_schema=TOOL_OUTPUT_BLOCKED,
    risk_level="DANGEROUS_BLOCKED",
)
async def handle_change_stripe_secret_config(
    auth: MCPAuthContext | None = None,
    **kwargs: object,
) -> MCPResponse:
    """Always blocked."""
    return _blocked_response(
        request_id=auth.request_id if auth else "",
        organization_id=str(auth.organization_id) if auth and auth.organization_id else "",
    )
