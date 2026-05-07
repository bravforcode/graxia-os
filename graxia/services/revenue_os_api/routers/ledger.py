"""
graxia/services/revenue_os_api/routers/ledger.py
Ledger entry read-only endpoints (append-only by design — no POST/PATCH/DELETE).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.db import get_db
from ....packages.revenue_os.models import LedgerEntry
from ....packages.revenue_os.schemas import LedgerEntryResponse
from ..dependencies import require_admin_api_key

router = APIRouter()


@router.get(
    "/",
    response_model=list[LedgerEntryResponse],
    dependencies=[Depends(require_admin_api_key)],
    summary="List ledger entries (read-only — append-only ledger)",
)
async def list_ledger_entries(
    order_id: UUID | None = Query(None),
    entry_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[LedgerEntryResponse]:
    stmt = select(LedgerEntry)
    if order_id:
        stmt = stmt.where(LedgerEntry.order_id == order_id)
    if entry_type:
        stmt = stmt.where(LedgerEntry.entry_type == entry_type)
    result = await db.scalars(
        stmt.order_by(LedgerEntry.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [LedgerEntryResponse.model_validate(e) for e in result]
