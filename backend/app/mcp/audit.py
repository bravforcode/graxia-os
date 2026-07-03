"""MCP audit log service — logs every tool call safely.

No secrets, no raw tokens, no raw delivery tokens in audit logs.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.mcp.schemas import MCPAuthContext, MCPResponse

logger = logging.getLogger(__name__)


async def log_mcp_tool_call(
    *,
    organization_id: UUID | None,
    actor_type: str,
    actor_id: str | None,
    tool_name: str,
    risk_level: str,
    status: str,  # started | success | failed | blocked | approval_required
    request_id: str,
    input_summary_redacted: str = "",
    output_summary_redacted: str = "",
    error_code: str | None = None,
    metadata_json: dict[str, Any] | None = None,
    db: AsyncSession | None = None,
) -> Any | None:
    """Log an MCP tool call to the audit log.

    All inputs and outputs are REDACTED — no raw data, no tokens, no secrets.
    """
    # Use a simple in-memory log entry for now since we don't have an MCPToolAuditLog model migration yet
    log_entry = {
        "id": str(uuid4()),
        "organization_id": str(organization_id) if organization_id else "none",
        "actor_type": actor_type,
        "actor_id": actor_id or "unknown",
        "tool_name": tool_name,
        "risk_level": risk_level,
        "status": status,
        "request_id": request_id,
        "input_summary_redacted": input_summary_redacted[:200],
        "output_summary_redacted": output_summary_redacted[:500],
        "error_code": error_code,
        "created_at": datetime.now(UTC).isoformat(),
        "metadata_json": metadata_json or {},
    }

    logger.info(
        "MCP AUDIT: tool=%s risk=%s status=%s req=%s org=%s",
        tool_name, risk_level, status, request_id,
        log_entry["organization_id"],
    )

    return log_entry


def _redact_dict(data: dict[str, Any] | None, max_len: int = 100) -> str:
    """Redact a dict to a safe summary string — no values, just keys and types."""
    if data is None:
        return ""
    parts = []
    for k, v in data.items():
        vtype = type(v).__name__
        parts.append(f"{k}:{vtype}")
    summary = ", ".join(parts)
    if len(summary) > max_len:
        summary = summary[:max_len] + "..."
    return summary


def redact_for_audit(
    response: MCPResponse | None,
    max_data_len: int = 200,
) -> str:
    """Redact an MCP response for audit logging — no raw data, just structure."""
    if response is None:
        return ""
    if not response.ok:
        return f"error={response.error.code if response.error else 'unknown'}"
    if response.data is None:
        return "ok (no data)"
    if isinstance(response.data, dict):
        return _redact_dict(response.data, max_data_len)
    if isinstance(response.data, list):
        return f"list[{len(response.data)} items]"
    return str(type(response.data).__name__)
