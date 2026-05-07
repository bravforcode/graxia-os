"""
graxia/services/revenue_os_api/routers/delivery.py
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.db import get_db
from ....packages.revenue_os.models import DeliveryEvent
from ....packages.revenue_os.schemas import DeliveryEventResponse
from ..dependencies import require_admin_api_key

router = APIRouter()


@router.get(
    "/",
    response_model=list[DeliveryEventResponse],
    dependencies=[Depends(require_admin_api_key)],
)
async def list_delivery_events(
    order_id: UUID | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[DeliveryEventResponse]:
    stmt = select(DeliveryEvent)
    if order_id:
        stmt = stmt.where(DeliveryEvent.order_id == order_id)
    if status_filter:
        stmt = stmt.where(DeliveryEvent.status == status_filter)
    result = await db.scalars(
        stmt.order_by(DeliveryEvent.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [DeliveryEventResponse.model_validate(d) for d in result]


@router.get(
    "/{delivery_id}",
    response_model=DeliveryEventResponse,
    dependencies=[Depends(require_admin_api_key)],
)
async def get_delivery_event(
    delivery_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> DeliveryEventResponse:
    event = await db.get(DeliveryEvent, delivery_id)
    if not event:
        raise HTTPException(status_code=404, detail="Delivery event not found")
    return DeliveryEventResponse.model_validate(event)
