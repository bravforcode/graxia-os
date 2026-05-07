"""
graxia/services/revenue_os_api/routers/campaigns.py
Revenue campaign management endpoints.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.db import get_db
from ....packages.revenue_os.models import CampaignStatus, RevenueCampaign
from ....packages.revenue_os.schemas import CampaignCreateRequest, CampaignResponse
from ..dependencies import require_admin_api_key

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/",
    response_model=list[CampaignResponse],
    dependencies=[Depends(require_admin_api_key)],
    summary="List campaigns",
)
async def list_campaigns(
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[CampaignResponse]:
    stmt = select(RevenueCampaign)
    if status_filter:
        stmt = stmt.where(RevenueCampaign.status == status_filter)
    result = await db.scalars(
        stmt.order_by(RevenueCampaign.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [CampaignResponse.model_validate(c) for c in result]


@router.post(
    "/",
    response_model=CampaignResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_api_key)],
    summary="Create a new campaign",
)
async def create_campaign(
    payload: CampaignCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> CampaignResponse:
    campaign = RevenueCampaign(**payload.model_dump())
    db.add(campaign)
    await db.flush()
    logger.info("Campaign created: id=%s name=%s", campaign.id, campaign.name)
    return CampaignResponse.model_validate(campaign)


@router.get(
    "/{campaign_id}",
    response_model=CampaignResponse,
    dependencies=[Depends(require_admin_api_key)],
)
async def get_campaign(campaign_id: UUID, db: AsyncSession = Depends(get_db)) -> CampaignResponse:
    campaign = await db.get(RevenueCampaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return CampaignResponse.model_validate(campaign)


@router.patch(
    "/{campaign_id}/pause",
    response_model=CampaignResponse,
    dependencies=[Depends(require_admin_api_key)],
)
async def pause_campaign(
    campaign_id: UUID,
    reason: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
) -> CampaignResponse:
    campaign = await db.get(RevenueCampaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.status = CampaignStatus.PAUSED.value
    campaign.paused_reason = reason
    await db.flush()
    return CampaignResponse.model_validate(campaign)


@router.patch(
    "/{campaign_id}/resume",
    response_model=CampaignResponse,
    dependencies=[Depends(require_admin_api_key)],
)
async def resume_campaign(
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> CampaignResponse:
    campaign = await db.get(RevenueCampaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.status = CampaignStatus.ACTIVE.value
    campaign.paused_reason = None
    await db.flush()
    return CampaignResponse.model_validate(campaign)
