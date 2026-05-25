"""Safe error handling for MCP — no raw tracebacks to client."""
from __future__ import annotations

import logging
from typing import Any

from app.mcp.schemas import MCPError, MCPResponse

logger = logging.getLogger(__name__)

# ── Safe Error Codes ─────────────────────────────────────────────────────────

ERR_TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
ERR_INVALID_REQUEST = "INVALID_REQUEST"
ERR_INVALID_PARAMS = "INVALID_PARAMS"
ERR_AUTH_REQUIRED = "AUTH_REQUIRED"
ERR_PERMISSION_DENIED = "PERMISSION_DENIED"
ERR_APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
ERR_DANGEROUS_BLOCKED = "DANGEROUS_TOOL_BLOCKED"
ERR_ORG_MISMATCH = "ORG_MISMATCH"
ERR_RATE_LIMITED = "RATE_LIMITED"
ERR_INTERNAL = "INTERNAL_ERROR"
ERR_HANDLER_ERROR = "HANDLER_ERROR"


# ── Safe Error Messages (no raw details) ─────────────────────────────────────

_SAFE_MESSAGES: dict[str, str] = {
    ERR_TOOL_NOT_FOUND: "Tool not found.",
    ERR_INVALID_REQUEST: "Invalid JSON-RPC request.",
    ERR_INVALID_PARAMS: "Invalid tool parameters.",
    ERR_AUTH_REQUIRED: "Authentication required.",
    ERR_PERMISSION_DENIED: "Permission denied.",
    ERR_APPROVAL_REQUIRED: "This action requires human approval.",
    ERR_DANGEROUS_BLOCKED: "This tool is intentionally blocked for safety.",
    ERR_ORG_MISMATCH: "Resource not found.",
    ERR_RATE_LIMITED: "Too many requests. Try again later.",
    ERR_INTERNAL: "An unexpected error occurred.",
    ERR_HANDLER_ERROR: "Tool handler error.",
}


def safe_error_response(
    code: str = ERR_INTERNAL,
    message: str | None = None,
    safe_to_retry: bool = False,
    request_id: str = "",
    organization_id: str = "",
) -> MCPResponse:
    """Build a safe error response — no raw details leaked."""
    return MCPResponse.error_response(
        code=code,
        message=message or _SAFE_MESSAGES.get(code, "An unexpected error occurred."),
        safe_to_retry=safe_to_retry,
        request_id=request_id,
        organization_id=organization_id,
    )


def handle_tool_error(
    tool_name: str,
    exc: Exception,
    request_id: str = "",
    organization_id: str = "",
) -> MCPResponse:
    """Handle a tool execution error safely — log details, return safe message."""
    logger.warning(
        "MCP tool error: tool=%s request=%s error=%s",
        tool_name, request_id, exc,
    )
    return safe_error_response(
        code=ERR_HANDLER_ERROR,
        message=f"Tool '{tool_name}' execution error.",
        safe_to_retry=False,
        request_id=request_id,
        organization_id=organization_id,
    )
