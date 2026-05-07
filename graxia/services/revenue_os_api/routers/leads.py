"""
graxia/services/revenue_os_api/routers/leads.py
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.db import get_db
from ....packages.revenue_os.models import Lead
from ....packages.revenue_os.schemas import LeadCreateRequest, LeadResponse
from ..dependencies import require_admin_api_key

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_model=list[LeadResponse], dependencies=[Depends(require_admin_api_key)])
async def list_leads(
    status_filter: Optional[str] = Query(None, alias="status"),
    campaign_id: Optional[UUID] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[LeadResponse]:
    stmt = select(Lead)
    if status_filter:
        stmt = stmt.where(Lead.status == status_filter)
    if campaign_id:
        stmt = stmt.where(Lead.campaign_id == campaign_id)
    result = await db.scalars(stmt.order_by(Lead.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return [LeadResponse.model_validate(l) for l in result]


@router.post("/", response_model=LeadResponse, status_code=201, dependencies=[Depends(require_admin_api_key)])
async def create_lead(payload: LeadCreateRequest, db: AsyncSession = Depends(get_db)) -> LeadResponse:
    lead = Lead(**payload.model_dump())
    db.add(lead)
    await db.flush()
    return LeadResponse.model_validate(lead)


@router.get("/{lead_id}", response_model=LeadResponse, dependencies=[Depends(require_admin_api_key)])
async def get_lead(lead_id: UUID, db: AsyncSession = Depends(get_db)) -> LeadResponse:
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return LeadResponse.model_validate(lead)
