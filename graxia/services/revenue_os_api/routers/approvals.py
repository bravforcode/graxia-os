"""
graxia/services/revenue_os_api/routers/approvals.py
CEO approval workflow endpoints.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.db import get_db
from ....packages.revenue_os.models import Approval, ApprovalStatus
from ....packages.revenue_os.schemas import ApprovalDecisionRequest, ApprovalResponse
from ..dependencies import require_admin_api_key

router = APIRouter()


@router.get("/", response_model=list[ApprovalResponse], dependencies=[Depends(require_admin_api_key)])
async def list_approvals(db: AsyncSession = Depends(get_db)) -> list[ApprovalResponse]:
    result = await db.scalars(
        select(Approval)
        .where(Approval.status == ApprovalStatus.PENDING.value)
        .order_by(Approval.created_at.asc())
    )
    return [ApprovalResponse.model_validate(a) for a in result]


@router.post("/{approval_id}/decide", response_model=ApprovalResponse, dependencies=[Depends(require_admin_api_key)])
async def decide_approval(
    approval_id: UUID,
    body: ApprovalDecisionRequest,
    db: AsyncSession = Depends(get_db),
) -> ApprovalResponse:
    approval = await db.get(Approval, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.status != ApprovalStatus.PENDING.value:
        raise HTTPException(status_code=409, detail=f"Approval already {approval.status}")
    approval.status = body.decision
    approval.ceo_notes = body.ceo_notes
    approval.reviewed_at = datetime.utcnow()
    await db.flush()
    return ApprovalResponse.model_validate(approval)
