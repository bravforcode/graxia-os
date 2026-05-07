"""
graxia/services/revenue_os_api/routers/entitlements.py
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.db import get_db
from ....packages.revenue_os.models import Entitlement
from ....packages.revenue_os.schemas import EntitlementResponse
from ..dependencies import require_admin_api_key

router = APIRouter()


@router.get(
    "/",
    response_model=list[EntitlementResponse],
    dependencies=[Depends(require_admin_api_key)],
)
async def list_entitlements(
    customer_email: str | None = Query(None),
    product_key: str | None = Query(None),
    active_only: bool = Query(True, description="Exclude revoked/expired"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[EntitlementResponse]:
    stmt = select(Entitlement)
    if customer_email:
        stmt = stmt.where(Entitlement.customer_email == customer_email)
    if product_key:
        stmt = stmt.where(Entitlement.product_key == product_key)
    if active_only:
        now = datetime.now(timezone.utc)
        stmt = stmt.where(
            Entitlement.revoked_at.is_(None),
            (Entitlement.expires_at.is_(None)) | (Entitlement.expires_at > now),
        )
    result = await db.scalars(
        stmt.order_by(Entitlement.granted_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [EntitlementResponse.model_validate(e) for e in result]


@router.post(
    "/{entitlement_id}/revoke",
    response_model=EntitlementResponse,
    dependencies=[Depends(require_admin_api_key)],
)
async def revoke_entitlement(
    entitlement_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> EntitlementResponse:
    ent = await db.get(Entitlement, entitlement_id)
    if not ent:
        raise HTTPException(status_code=404, detail="Entitlement not found")
    if ent.revoked_at:
        raise HTTPException(status_code=409, detail="Entitlement already revoked")
    ent.revoked_at = datetime.now(timezone.utc)
    await db.flush()
    return EntitlementResponse.model_validate(ent)
