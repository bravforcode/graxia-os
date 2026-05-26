"""MCP HTTP API routes — JSON-RPC over HTTP.

Post JSON-RPC requests to /api/v1/mcp for tool calls.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.context import AuthContext
from app.auth.dependencies import require_organization
from app.auth.org_boundary import assert_same_org

from app.mcp.transports.http import handle_http_jsonrpc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])


@router.post("/")
@router.post("/tools/list")
@router.post("/tools/call")
async def mcp_jsonrpc(
    request: Request,
    auth: AuthContext = Depends(require_organization),
) -> dict[str, Any]:
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

    request_org_candidates = [
        request.headers.get("X-Organization-ID", ""),
        request.headers.get("X-Graxia-Org-Id", ""),
        body.get("params", {}).get("organization_id", ""),
    ]
    for requested_org_id in request_org_candidates:
        if requested_org_id:
            assert_same_org(auth, requested_org_id)

    organization_id = str(auth.organization_id)

    result = await handle_http_jsonrpc(
        body=body,
        organization_id=organization_id,
        actor_type=auth.actor_type,
        actor_id=auth.actor_id or request.headers.get("X-User-ID"),
        permissions=auth.permissions,
        correlation_id=auth.correlation_id or auth.request_id or "",
    )

    return result
