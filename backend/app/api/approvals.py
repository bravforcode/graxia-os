from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.control_plane import resolve_approval_batch, resolve_approval_request
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
    status: ApprovalStatus = None,
    batch_key: BatchKey = None,
    limit: ResultLimit = 20,
    offset: ResultOffset = 0,
) -> ApprovalList:
    query = select(ApprovalRequest)
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
async def get_approval(approval_id: UUID, db: DbSession) -> ApprovalRequestOut:
    approval = await db.get(ApprovalRequest, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return ApprovalRequestOut.model_validate(approval)


@router.patch("/{approval_id}/approve", response_model=ApprovalDecisionResponse)
async def approve_approval(
    approval_id: UUID,
    note: str = "",
) -> ApprovalDecisionResponse:
    approval = await resolve_approval_request(approval_id, "approved", note=note or None)
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
    note: str = "",
) -> ApprovalDecisionResponse:
    approval = await resolve_approval_request(approval_id, "rejected", note=note or None)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return ApprovalDecisionResponse(
        id=approval.id,
        status=approval.status,
        batch_key=approval.batch_key,
    )


@router.patch("/batch/{batch_key}/approve", response_model=ApprovalBatchResponse)
async def approve_batch(batch_key: str, note: str = "") -> ApprovalBatchResponse:
    count = await resolve_approval_batch(batch_key, "approved", note=note or None)
    return ApprovalBatchResponse(status="approved", batch_key=batch_key, count=count)


@router.patch("/batch/{batch_key}/reject", response_model=ApprovalBatchResponse)
async def reject_batch(batch_key: str, note: str = "") -> ApprovalBatchResponse:
    count = await resolve_approval_batch(batch_key, "rejected", note=note or None)
    return ApprovalBatchResponse(status="rejected", batch_key=batch_key, count=count)
