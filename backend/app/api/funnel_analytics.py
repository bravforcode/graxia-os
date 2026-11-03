import logging
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.tenant import get_org
from app.auth.dependencies import require_permission
from app.models.organization import Organization
from app.services.funnel_analytics_service import FunnelAnalyticsService
from app.services.public_funnel_service import (
    PublicFunnelBindingError,
    require_public_funnel_organization,
)
from app.schemas.funnel import (
    ConversionEventCreatePublic,
    ConversionEventRead,
    FunnelAnalyticsSummary,
    FunnelDailyAnalytics,
    FunnelAttributionRow,
    FunnelDashboardResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/events", response_model=ConversionEventRead, status_code=status.HTTP_201_CREATED)
async def log_funnel_event(
    payload: ConversionEventCreatePublic,
    db: AsyncSession = Depends(get_db),
):
    """
    Public endpoint to ingest funnel analytics events (e.g. page views, checkouts, lead magnet captures).
    """
    try:
        organization_id = require_public_funnel_organization(payload.organization_id)
    except PublicFunnelBindingError as exc:
        raise HTTPException(
            status_code=503 if "not configured" in str(exc) else 404,
            detail=str(exc),
        ) from exc
    service = FunnelAnalyticsService(db)
    try:
        event = await service.log_event(
            organization_id=organization_id,
            event_type=payload.event_type,
            product_id=payload.product_id,
            contact_id=payload.contact_id,
            order_id=payload.order_id,
            session_id=payload.session_id,
            source=payload.source,
            medium=payload.medium,
            campaign=payload.campaign,
            referrer=payload.referrer,
            first_touch=payload.first_touch.model_dump(exclude_none=True) if payload.first_touch else None,
            last_touch=payload.last_touch.model_dump(exclude_none=True) if payload.last_touch else None,
            landing_path=payload.landing_path,
            content_id=payload.content_id,
            referral_code=payload.referral_code,
            metadata_json=payload.metadata_json,
            idempotency_key=payload.idempotency_key,
            public=True,
        )
        return event
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(e)},
        )

@router.get("/analytics/summary", response_model=FunnelAnalyticsSummary)
async def get_analytics_summary(
    product_id: Optional[UUID] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    """
    Get aggregated conversion funnel and sales summary metrics (Admin only).
    """
    service = FunnelAnalyticsService(db)
    return await service.get_analytics_summary(
        organization_id=org.id,
        product_id=product_id,
        start_date=start_date,
        end_date=end_date,
    )

@router.get("/analytics/products/{product_id}", response_model=FunnelAnalyticsSummary)
async def get_product_analytics(
    product_id: UUID,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    """
    Get product-specific conversion funnel and sales summary metrics (Admin only).
    """
    service = FunnelAnalyticsService(db)
    return await service.get_analytics_summary(
        organization_id=org.id,
        product_id=product_id,
        start_date=start_date,
        end_date=end_date,
    )

@router.get("/analytics/daily", response_model=List[FunnelDailyAnalytics])
async def get_daily_analytics(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    """
    Get daily breakdown of funnel events and revenues (Admin only).
    """
    service = FunnelAnalyticsService(db)
    return await service.get_daily_analytics(
        organization_id=org.id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/analytics/attribution", response_model=List[FunnelAttributionRow])
async def get_attribution_analytics(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    """Return revenue and funnel outcomes grouped by source/campaign."""
    service = FunnelAnalyticsService(db)
    return await service.get_attribution_summary(
        organization_id=org.id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/analytics/dashboard", response_model=FunnelDashboardResponse)
async def get_analytics_dashboard(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    source: Optional[str] = Query(None, max_length=100),
    medium: Optional[str] = Query(None, max_length=100),
    campaign: Optional[str] = Query(None, max_length=100),
    product_id: Optional[UUID] = Query(None),
    plan: Optional[str] = Query(None, max_length=100),
    referral_code: Optional[str] = Query(None, max_length=160),
    org: Organization = Depends(get_org),
    _analytics_permission=Depends(require_permission("analytics:read")),
    db: AsyncSession = Depends(get_db),
):
    """Return evidence-labelled conversion metrics for one organization."""
    try:
        return await FunnelAnalyticsService(db).get_dashboard(
            organization_id=org.id,
            start_date=start_date,
            end_date=end_date,
            source=source,
            medium=medium,
            campaign=campaign,
            product_id=product_id,
            plan=plan,
            referral_code=referral_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
