"""Org-scoped audit query API endpoints — safe, paginated, redacted."""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.auth.dependencies import require_organization
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.approval_request import ApprovalRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


def _redact_safe(obj: dict[str, Any] | None) -> dict[str, Any] | None:
    """Redact sensitive keys from audit details."""
    if not obj:
        return None
    SENSITIVE_KEYS = {
        "secret", "token", "password", "key", "credential",
        "private", "authorization", "cookie", "stripe", "oauth",
        "database_url", "api_key", "access_key",
    }
    result: dict[str, Any] = {}
    for k, v in obj.items():
        if any(s in k.lower() for s in SENSITIVE_KEYS):
            result[k] = "**[REDACTED]**"
        elif isinstance(v, dict):
            result[k] = _redact_safe(v)
        else:
            result[k] = v
    return result


@router.get("/events")
async def list_audit_events(
    auth: AuthContext = Depends(require_organization),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    event_type: str | None = Query(default=None),
    severity: str | None = Query(default=None),
):
    """List audit events for the current organization — paginated and redacted."""
    query = select(AuditLog).where(AuditLog.organization_id == auth.organization_id)

    if event_type:
        query = query.where(AuditLog.event_type == event_type)
    if severity:
        query = query.where(AuditLog.severity == severity)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.order_by(desc(AuditLog.created_at)).offset(offset).limit(limit)
    )
    items = []
    for row in result.scalars().all():
        items.append({
            "id": str(row.id),
            "action": row.action,
            "event_type": row.event_type,
            "severity": row.severity,
            "outcome": row.outcome,
            "metadata": _redact_safe(row.metadata_),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })

    return {"total": int(total or 0), "items": items, "limit": limit, "offset": offset}


@router.get("/mcp")
async def list_mcp_audit(
    auth: AuthContext = Depends(require_organization),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List MCP-related audit events for the current organization."""
    query = (
        select(AuditLog)
        .where(
            AuditLog.organization_id == auth.organization_id,
            AuditLog.action.ilike("mcp.%"),
        )
    )

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.order_by(desc(AuditLog.created_at)).offset(offset).limit(limit)
    )
    items = []
    for row in result.scalars().all():
        items.append({
            "id": str(row.id),
            "action": row.action,
            "tool_name": (row.metadata_ or {}).get("tool_name", ""),
            "outcome": row.outcome,
            "success": row.success,
            "metadata": _redact_safe(row.metadata_),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })

    return {"total": int(total or 0), "items": items, "limit": limit, "offset": offset}


@router.get("/workflows")
async def list_workflow_audit(
    auth: AuthContext = Depends(require_organization),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List workflow-related audit events for the current organization."""
    query = (
        select(AuditLog)
        .where(
            AuditLog.organization_id == auth.organization_id,
            AuditLog.action.ilike("workflow.%"),
        )
    )

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.order_by(desc(AuditLog.created_at)).offset(offset).limit(limit)
    )
    items = []
    for row in result.scalars().all():
        items.append({
            "id": str(row.id),
            "action": row.action,
            "workflow_type": (row.metadata_ or {}).get("workflow_type", ""),
            "workflow_run_id": (row.metadata_ or {}).get("workflow_run_id", ""),
            "outcome": row.outcome,
            "metadata": _redact_safe(row.metadata_),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })

    return {"total": int(total or 0), "items": items, "limit": limit, "offset": offset}


@router.get("/approvals")
async def list_approval_audit(
    auth: AuthContext = Depends(require_organization),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
):
    """List approval request events for the current organization."""
    query = (
        select(ApprovalRequest)
        .where(ApprovalRequest.organization_id == auth.organization_id)
    )
    if status:
        query = query.where(ApprovalRequest.status == status)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.order_by(desc(ApprovalRequest.created_at)).offset(offset).limit(limit)
    )
    items = []
    for row in result.scalars().all():
        items.append({
            "id": str(row.id),
            "title": row.title,
            "action_type": row.action_type,
            "status": row.status,
            "policy_class": row.policy_class,
            "details": _redact_safe(row.details),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })

    return {"total": int(total or 0), "items": items, "limit": limit, "offset": offset}
