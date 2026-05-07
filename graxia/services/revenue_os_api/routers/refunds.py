"""
graxia/services/revenue_os_api/routers/refunds.py
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.db import get_db
from ....packages.revenue_os.models import Order, OrderStatus, Refund, RefundStatus
from ....packages.revenue_os.schemas import RefundResponse
from ..dependencies import require_admin_api_key

router = APIRouter()


@router.get(
    "/",
    response_model=list[RefundResponse],
    dependencies=[Depends(require_admin_api_key)],
)
async def list_refunds(
    order_id: UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[RefundResponse]:
    stmt = select(Refund)
    if order_id:
        stmt = stmt.where(Refund.order_id == order_id)
    result = await db.scalars(
        stmt.order_by(Refund.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [RefundResponse.model_validate(r) for r in result]


@router.get(
    "/{refund_id}",
    response_model=RefundResponse,
    dependencies=[Depends(require_admin_api_key)],
)
async def get_refund(refund_id: UUID, db: AsyncSession = Depends(get_db)) -> RefundResponse:
    refund = await db.get(Refund, refund_id)
    if not refund:
        raise HTTPException(status_code=404, detail="Refund not found")
    return RefundResponse.model_validate(refund)
