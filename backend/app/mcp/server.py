"""MCP Server — JSON-RPC message dispatcher.

Handles JSON-RPC messages, routes to tools/list and tools/call methods,
enforces auth and permissions, and returns safe responses.
"""
from __future__ import annotations

import json
import logging
from uuid import uuid4

from app.mcp.errors import (
    ERR_INVALID_REQUEST,
    safe_error_response,
)
from app.mcp.registry import mcp_registry
from app.mcp.schemas import MCPAuthContext, MCPResponse

logger = logging.getLogger(__name__)


async def handle_jsonrpc_message(
    raw_body: str,
    auth: MCPAuthContext | None = None,
) -> str:
    """Handle a single JSON-RPC message and return JSON response string."""
    request_id = auth.request_id if auth else str(uuid4())
    org_id = str(auth.organization_id) if auth and auth.organization_id else ""

    # Parse JSON
    try:
        msg = json.loads(raw_body)
    except (json.JSONDecodeError, ValueError):
        response = safe_error_response(
            code=ERR_INVALID_REQUEST,
            message="Invalid JSON.",
            request_id=request_id,
            organization_id=org_id,
        )
        return json.dumps(response.to_dict())

    method = msg.get("method", "")
    params = msg.get("params", {})

    if not isinstance(params, dict):
        params = {}

    # Build auth if none provided
    if auth is None:
        auth = MCPAuthContext.system()

    # tools/list
    if method == "tools/list":
        risk_level = params.get("risk_level")
        tools = mcp_registry.list_tools(risk_level=risk_level)
        response = MCPResponse.ok_response(
            data={"tools": tools},
            request_id=request_id,
            organization_id=org_id,
            estimated_tokens=max(50, len(tools) * 20),
        )
        return json.dumps(response.to_dict())

    # tools/call
    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        if not isinstance(tool_args, dict):
            tool_args = {}
        response = await mcp_registry.call_tool(tool_name, tool_args, auth=auth)
        return json.dumps(response.to_dict())

    # Unknown method
    response = safe_error_response(
        code="METHOD_NOT_FOUND",
        message=f"Unknown method: {method}",
        request_id=request_id,
        organization_id=org_id,
    )
    return json.dumps(response.to_dict())
