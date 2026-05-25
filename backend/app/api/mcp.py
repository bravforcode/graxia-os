"""MCP HTTP API routes — JSON-RPC over HTTP.

Post JSON-RPC requests to /api/v1/mcp for tool calls.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.mcp.transports.http import handle_http_jsonrpc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])


@router.post("/")
@router.post("/tools/list")
@router.post("/tools/call")
async def mcp_jsonrpc(request: Request) -> dict[str, Any]:
    """Handle JSON-RPC requests via HTTP.

    Accepts JSON-RPC 2.0 format:
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {}
    }

    Also accepts raw string for backwards compatibility.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")

    # Extract org from headers or body
    organization_id = (
        request.headers.get("X-Organization-ID", "")
        or body.get("params", {}).get("organization_id", "")
        or "00000000-0000-0000-0000-000000000001"
    )

    result = await handle_http_jsonrpc(
        body=body,
        organization_id=organization_id,
        actor_type="api",
        actor_id=request.headers.get("X-User-ID"),
    )

    return result
