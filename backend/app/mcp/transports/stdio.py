"""MCP stdio transport — JSON-RPC over stdin/stdout.

Reads JSON-RPC requests from stdin, dispatches to MCP registry,
and writes JSON-RPC responses to stdout.

Usage:
    python -m backend.app.mcp.transports.stdio
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from uuid import UUID, uuid4

from app.mcp.schemas import MCPAuthContext
from app.mcp.registry import mcp_registry
from app.mcp.errors import (
    ERR_INVALID_REQUEST,
    safe_error_response,
)

logger = logging.getLogger(__name__)

# Default organization ID for stdio mode (single-tenant local)
DEFAULT_ORG_ID = UUID("00000000-0000-0000-0000-000000000001")


async def handle_requests() -> None:
    """Read JSON-RPC requests from stdin and write responses to stdout."""
    logger.info("MCP stdio transport starting (read requests from stdin)...")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        request_id = str(uuid4())
        raw_request: dict = {}

        try:
            raw_request = json.loads(line)
        except json.JSONDecodeError:
            response = safe_error_response(
                code=ERR_INVALID_REQUEST,
                message="Invalid JSON.",
                request_id=request_id,
                organization_id=str(DEFAULT_ORG_ID),
            )
            print(json.dumps(response.to_dict()), flush=True)
            continue

        method = raw_request.get("method", "")
        params = raw_request.get("params", {})
        req_jsonrpc_id = raw_request.get("id")

        # Build auth context
        auth = MCPAuthContext(
            organization_id=DEFAULT_ORG_ID,
            actor_type="system",
            actor_id="stdio_client",
            request_id=request_id,
        )

        # Handle tools/list
        if method == "tools/list":
            risk_level = params.get("risk_level") if isinstance(params, dict) else None
            tools = mcp_registry.list_tools(risk_level=risk_level)
            response = MCPResponse(
                ok=True,
                data={"tools": tools},
            ).ok_response(
                data={"tools": tools},
                request_id=request_id,
                organization_id=str(DEFAULT_ORG_ID),
                estimated_tokens=max(50, len(tools) * 20),
            )
            print(json.dumps(response.to_dict()), flush=True)
            continue

        # Handle tools/call
        if method == "tools/call":
            tool_name = params.get("name", "") if isinstance(params, dict) else ""
            tool_args = params.get("arguments", {}) if isinstance(params, dict) else {}
            response = await mcp_registry.call_tool(tool_name, tool_args, auth=auth)
            print(json.dumps(response.to_dict()), flush=True)
            continue

        # Unknown method
        response = safe_error_response(
            code="METHOD_NOT_FOUND",
            message=f"Unknown method: {method}",
            request_id=request_id,
            organization_id=str(DEFAULT_ORG_ID),
        )
        print(json.dumps(response.to_dict()), flush=True)


def main() -> None:
    """Entry point for stdio transport."""
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    asyncio.run(handle_requests())


if __name__ == "__main__":
    main()
