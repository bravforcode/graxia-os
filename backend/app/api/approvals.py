from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.auth.dependencies import get_auth_context, require_permission
from app.core.control_plane import (
    ApprovalAlreadyProcessedError,
    queue_approval_request,
    resolve_approval_batch,
    resolve_approval_request,
)
from app.database import get_db
from app.models.approval_request import ApprovalRequest
from app.schemas.approval import (
    ApprovalBatchResponse,
    ApprovalDecisionResponse,
    ApprovalList,
    ApprovalRequestOut,
)

router = APIRouter(prefix="/approvals", tags=["approvals"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
ApprovalStatus = Annotated[str | None, Query()]
BatchKey = Annotated[str | None, Query()]
ResultLimit = Annotated[int, Query(ge=1, le=100)]
ResultOffset = Annotated[int, Query(ge=0)]


@router.get("", response_model=ApprovalList)
async def list_approvals(
    db: DbSession,
    auth: AuthContext = Depends(require_permission("approvals:read")),
    status: ApprovalStatus = None,
    batch_key: BatchKey = None,
    limit: ResultLimit = 20,
    offset: ResultOffset = 0,
) -> ApprovalList:
    query = select(ApprovalRequest).where(
        ApprovalRequest.organization_id == auth.organization_id
    )
    if status:
        query = query.where(ApprovalRequest.status == status)
    if batch_key:
        query = query.where(ApprovalRequest.batch_key == batch_key)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.order_by(desc(ApprovalRequest.created_at)).offset(offset).limit(limit)
    )
    items = [ApprovalRequestOut.model_validate(item) for item in result.scalars().all()]
    return ApprovalList(total=int(total or 0), items=items)


@router.get("/{approval_id}", response_model=ApprovalRequestOut)
async def get_approval(approval_id: UUID, db: DbSession, auth: AuthContext = Depends(require_permission("approvals:read"))) -> ApprovalRequestOut:
    approval = await db.get(ApprovalRequest, approval_id)
    if approval is None or approval.organization_id != auth.organization_id:
        raise HTTPException(status_code=404, detail="Approval not found")
    return ApprovalRequestOut.model_validate(approval)


@router.patch("/{approval_id}/approve", response_model=ApprovalDecisionResponse)
async def approve_approval(
    approval_id: UUID,
    db: DbSession = None,
    auth: AuthContext = Depends(require_permission("approvals:resolve")),
    note: str = "",
) -> ApprovalDecisionResponse:
    # Verify org scope before resolving
    approval = await db.get(ApprovalRequest, approval_id)
    if approval is None or approval.organization_id != auth.organization_id:
        raise HTTPException(status_code=404, detail="Approval not found")
    try:
        approval = await resolve_approval_request(approval_id, "approved", note=note or None)
    except ApprovalAlreadyProcessedError as exc:
        raise HTTPException(status_code=409, detail="Approval already processed") from exc
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return ApprovalDecisionResponse(
        id=approval.id,
        status=approval.status,
        batch_key=approval.batch_key,
    )


@router.patch("/{approval_id}/reject", response_model=ApprovalDecisionResponse)
async def reject_approval(
    approval_id: UUID,
    db: DbSession = None,
    auth: AuthContext = Depends(require_permission("approvals:resolve")),
    note: str = "",
) -> ApprovalDecisionResponse:
    # Verify org scope before resolving
    approval = await db.get(ApprovalRequest, approval_id)
    if approval is None or approval.organization_id != auth.organization_id:
        raise HTTPException(status_code=404, detail="Approval not found")
    try:
        approval = await resolve_approval_request(approval_id, "rejected", note=note or None)
    except ApprovalAlreadyProcessedError as exc:
        raise HTTPException(status_code=409, detail="Approval already processed") from exc
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return ApprovalDecisionResponse(
        id=approval.id,
        status=approval.status,
        batch_key=approval.batch_key,
    )


@router.patch("/batch/{batch_key}/approve", response_model=ApprovalBatchResponse)
async def approve_batch(
    batch_key: str,
    note: str = "",
    auth: AuthContext = Depends(require_permission("approvals:resolve")),
) -> ApprovalBatchResponse:
    count = await resolve_approval_batch(
        batch_key,
        "approved",
        note=note or None,
        organization_id=auth.organization_id,
    )
    return ApprovalBatchResponse(status="approved", batch_key=batch_key, count=count)


@router.patch("/batch/{batch_key}/reject", response_model=ApprovalBatchResponse)
async def reject_batch(
    batch_key: str,
    note: str = "",
    auth: AuthContext = Depends(require_permission("approvals:resolve")),
) -> ApprovalBatchResponse:
    count = await resolve_approval_batch(
        batch_key,
        "rejected",
        note=note or None,
        organization_id=auth.organization_id,
    )
    return ApprovalBatchResponse(status="rejected", batch_key=batch_key, count=count)


async def create_approval_from_event(
    action_type: str,
    what_action: str,
    why_now: str = "",
    confidence: float = 0.5,
    metadata: dict | None = None,
) -> ApprovalRequest:
    """Create an approval request from an event payload.

    Args:
        action_type: Type of action (e.g., 'scoring_weight_update')
        what_action: Human-readable description of the action
        why_now: Reasoning for why the action is suggested
        confidence: Confidence score (0.0-1.0)
        metadata: Additional event metadata to store

    Returns:
        Created ApprovalRequest instance
    """
    return await queue_approval_request(
        title=what_action,
        action_type=action_type,
        subject_type=None,
        subject_id=None,
        details={
            "reasoning": why_now,
            "confidence": confidence,
            **(metadata or {}),
        },
        preview={
            "summary": what_action,
            "confidence": confidence,
        },
        requested_by="system",
    )
