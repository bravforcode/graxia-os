"""MCP HTTP transport — JSON-RPC via HTTP.

Integrated through FastAPI routes in app.api.mcp.
Handles JSON-RPC requests, dispatches to MCP registry,
and returns safe JSON-RPC responses.
"""
from __future__ import annotations

import json
import logging
from uuid import UUID
from uuid import uuid4

from app.mcp.errors import (
    ERR_INVALID_REQUEST,
    safe_error_response,
)
from app.mcp.registry import mcp_registry
from app.mcp.schemas import MCPAuthContext, MCPResponse

logger = logging.getLogger(__name__)


async def handle_http_jsonrpc(
    body: dict,
    organization_id: str = "",
    actor_type: str = "api",
    actor_id: str | None = None,
    permissions: list[str] | None = None,
    correlation_id: str = "",
) -> dict:
    """Handle a JSON-RPC request via HTTP transport.

    Returns a dict ready for JSON serialization.
    """
    request_id = str(uuid4())

    method = body.get("method", "")
    params = body.get("params", {})

    if not isinstance(params, dict):
        params = {}

    parsed_org_id = None
    if organization_id:
        try:
            parsed_org_id = UUID(str(organization_id))
        except (ValueError, TypeError):
            parsed_org_id = None

    # Build auth context
    auth = MCPAuthContext(
        organization_id=parsed_org_id,
        actor_type=actor_type,
        actor_id=actor_id or "api_client",
        request_id=request_id,
        correlation_id=correlation_id or request_id,
        permissions=list(permissions or []),
        is_authenticated=actor_type not in {"anonymous"},
    )

    # tools/list
    if method == "tools/list":
        risk_level = params.get("risk_level")
        tools = mcp_registry.list_tools(risk_level=risk_level)
        tools_data = {
            "tools": tools,
        }
        response = MCPResponse.ok_response(
            data=tools_data,
            request_id=request_id,
            organization_id=str(organization_id) if organization_id else "",
            estimated_tokens=max(50, len(tools) * 20),
        )
        return response.to_dict()

    # tools/call
    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        if not isinstance(tool_args, dict):
            tool_args = {}
        response = await mcp_registry.call_tool(tool_name, tool_args, auth=auth)
        return response.to_dict()

    # Unknown method
    response = safe_error_response(
        code="METHOD_NOT_FOUND",
        message=f"Unknown method: {method}",
        request_id=request_id,
        organization_id=str(organization_id) if organization_id else "",
    )
    return response.to_dict()
