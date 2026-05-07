"""
graxia/services/revenue_os_api/routers/orders.py
Order management endpoints.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.db import get_db
from ....packages.revenue_os.models import Order, OrderStatus
from ....packages.revenue_os.schemas import OrderListResponse, OrderResponse
from ..dependencies import require_admin_api_key

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/",
    response_model=OrderListResponse,
    dependencies=[Depends(require_admin_api_key)],
    summary="List orders with optional filtering",
)
async def list_orders(
    status: Optional[str] = Query(None, description="Filter by status"),
    customer_email: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> OrderListResponse:
    stmt = select(Order)
    if status:
        stmt = stmt.where(Order.status == status)
    if customer_email:
        stmt = stmt.where(Order.customer_email == customer_email)

    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    orders_result = await db.scalars(
        stmt.order_by(Order.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return OrderListResponse(
        total=total or 0,
        items=[OrderResponse.model_validate(o) for o in orders_result],
    )


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    dependencies=[Depends(require_admin_api_key)],
    summary="Get order by ID",
)
async def get_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> OrderResponse:
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return OrderResponse.model_validate(order)
