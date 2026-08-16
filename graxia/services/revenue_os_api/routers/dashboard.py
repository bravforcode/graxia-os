"""
graxia/services/revenue_os_api/routers/dashboard.py
Revenue OS CEO dashboard — aggregated metrics.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.db import get_db
from ....packages.revenue_os.finance.channel_pl import channel_pl as compute_channel_pl
from ....packages.revenue_os.models import (
    Approval, ApprovalStatus, CampaignStatus,
    EmailOutbox, EmailStatus, IncidentEvent,
    Lead, Order, OrderStatus, RevenueCampaign,
)
from ....packages.revenue_os.schemas import (
    ChannelPnLResponse, CustomerProfileResponse, DashboardSummary,
)
from ....packages.revenue_os.services.customer_identity import customer_profile
from ..dependencies import require_admin_api_key
from datetime import datetime, timezone
from calendar import monthrange

router = APIRouter()


@router.get(
    "/channels",
    response_model=list[ChannelPnLResponse],
    dependencies=[Depends(require_admin_api_key)],
    summary="Per-channel P&L (revenue, est fees, est COGS, est margin)",
)
async def channel_pl(db: AsyncSession = Depends(get_db)) -> list[ChannelPnLResponse]:
    rows = await compute_channel_pl(db)
    return [ChannelPnLResponse.model_validate(row) for row in rows]


@router.get(
    "/customer/{email}",
    response_model=CustomerProfileResponse,
    dependencies=[Depends(require_admin_api_key)],
    summary="Cross-platform customer profile (orders across all channels)",
)
async def customer(email: str, db: AsyncSession = Depends(get_db)) -> CustomerProfileResponse:
    from fastapi import HTTPException
    profile = await customer_profile(db, email)
    if profile is None:
        raise HTTPException(status_code=404, detail="no orders for this email")
    return CustomerProfileResponse.model_validate(profile)


@router.get(
    "/",
    response_model=DashboardSummary,
    dependencies=[Depends(require_admin_api_key)],
    summary="CEO revenue dashboard",
)
async def dashboard_summary(db: AsyncSession = Depends(get_db)) -> DashboardSummary:
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_revenue = await db.scalar(
        select(func.coalesce(func.sum(Order.amount_cents), 0))
        .where(Order.status == OrderStatus.PAID.value)
    )
    month_revenue = await db.scalar(
        select(func.coalesce(func.sum(Order.amount_cents), 0))
        .where(Order.status == OrderStatus.PAID.value, Order.created_at >= month_start)
    )
    active_campaigns = await db.scalar(
        select(func.count(RevenueCampaign.id))
        .where(RevenueCampaign.status == CampaignStatus.ACTIVE.value)
    )
    leads_count = await db.scalar(select(func.count(Lead.id)))
    converted = await db.scalar(select(func.count(Lead.id)).where(Lead.converted_at.isnot(None)))
    pending_approvals = await db.scalar(
        select(func.count(Approval.id)).where(Approval.status == ApprovalStatus.PENDING.value)
    )
    open_incidents = await db.scalar(
        select(func.count(IncidentEvent.id)).where(IncidentEvent.resolved_at.is_(None))
    )
    emails_pending = await db.scalar(
        select(func.count(EmailOutbox.id)).where(EmailOutbox.status == EmailStatus.PENDING.value)
    )

    leads_total = leads_count or 1
    conversion_rate = round((converted or 0) / leads_total * 100, 2)

    return DashboardSummary(
        total_revenue_cents=total_revenue or 0,
        revenue_this_month_cents=month_revenue or 0,
        active_campaigns=active_campaigns or 0,
        leads_count=leads_count or 0,
        conversion_rate_pct=conversion_rate,
        pending_approvals=pending_approvals or 0,
        open_incidents=open_incidents or 0,
        emails_pending=emails_pending or 0,
    )
