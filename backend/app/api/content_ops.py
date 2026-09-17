"""Tenant-scoped Content Ops publish endpoint."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.auth.dependencies import require_permission
from app.database import get_db
from app.models.approval_request import ApprovalRequest

from app.content_ops.contracts import PublishReceipt, PublishRequest
from app.content_ops.service import execute_publish

router = APIRouter(prefix="/content-ops", tags=["content-ops"])
DbSession = Annotated[AsyncSession, Depends(get_db)]


class PublishIntentPayload(BaseModel):
    """Client payload; tenant identity is always taken from AuthContext."""

    model_config = ConfigDict(extra="forbid")

    content_id: str = Field(min_length=1, max_length=256)
    provider: str = Field(min_length=2, max_length=32)
    scheduled_at: datetime | None = None
    approval_id: str = Field(min_length=1, max_length=256)
    idempotency_key: str = Field(min_length=1, max_length=256)
    dry_run: bool = True
    live: bool = False


async def _approved_for_tenant(
    db: AsyncSession,
    auth: AuthContext,
    approval_id: str,
) -> bool:
    """Verify approval ownership/status without treating a client flag as proof."""

    try:
        parsed_id = UUID(approval_id)
    except (TypeError, ValueError):
        return False

    approval = await db.get(ApprovalRequest, parsed_id)
    if approval is None or approval.organization_id != auth.organization_id:
        return False
    if approval.status != "approved":
        return False
    if approval.expires_at is None:
        return True
    expires_at = approval.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at > datetime.now(UTC)


@router.post("/publish", response_model=PublishReceipt, status_code=status.HTTP_200_OK)
async def publish_content(
    payload: PublishIntentPayload,
    db: DbSession,
    auth: AuthContext = Depends(require_permission("runtime:write")),
) -> PublishReceipt:
    """Record a dry-run or safely gated publish intent.

    Live provider calls remain disabled until an explicitly configured adapter,
    provider allowlist, approval, consent evidence, and production canary all
    exist.  This endpoint therefore remains useful for deterministic staging
    evidence without silently sending content to a social network.
    """

    if auth.organization_id is None:
        raise HTTPException(status_code=401, detail="Organization context required")

    request = PublishRequest(
        tenant_id=str(auth.organization_id),
        content_id=payload.content_id,
        provider=payload.provider,
        scheduled_at=payload.scheduled_at,
        approval_id=payload.approval_id,
        idempotency_key=payload.idempotency_key,
        dry_run=payload.dry_run,
        live=payload.live,
    )
    approval_granted = await _approved_for_tenant(db, auth, request.approval_id)
    return await execute_publish(
        db,
        request,
        approval_granted=approval_granted,
        # Consent is intentionally not inferred from an approval.  A future
        # consent service must pass explicit evidence before live can open.
        consent_granted=False,
    )
