"""
graxia/services/revenue_os_api/routers/affiliate.py
Affiliate/KOL program admin endpoints (policy-gated creation, overview).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.affiliate.service import AffiliateError, create_affiliate
from ....packages.revenue_os.db import get_db
from ....packages.revenue_os.enums import AffiliateStatus
from ....packages.revenue_os.models import Affiliate, AffiliatePayout
from ....packages.revenue_os.schemas import (
    AffiliateCreateRequest,
    AffiliateOverviewResponse,
    AffiliateResponse,
)
from ..dependencies import require_admin_api_key

router = APIRouter()


@router.post("/create", response_model=AffiliateResponse,
             dependencies=[Depends(require_admin_api_key)])
async def create(body: AffiliateCreateRequest, db: AsyncSession = Depends(get_db)) -> AffiliateResponse:
    try:
        affiliate = await create_affiliate(
            db, email=body.email, commission_percent=body.commission_percent, code=body.code)
    except AffiliateError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return AffiliateResponse.model_validate(affiliate)


@router.get("/overview", response_model=AffiliateOverviewResponse,
            dependencies=[Depends(require_admin_api_key)])
async def overview(db: AsyncSession = Depends(get_db)) -> AffiliateOverviewResponse:
    affiliates = (await db.execute(select(Affiliate))).scalars().all()
    payouts = (await db.execute(select(AffiliatePayout))).scalars().all()
    return AffiliateOverviewResponse(
        total=len(affiliates),
        active=sum(1 for a in affiliates if a.status == AffiliateStatus.ACTIVE),
        pending_payouts=sum(1 for p in payouts if p.status == "pending"),
        pending_payout_cents=sum(p.amount_cents for p in payouts if p.status == "pending"),
        needs_review=sum(1 for p in payouts if p.needs_review),
    )
