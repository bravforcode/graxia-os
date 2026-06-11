"""
Funnel AI Recommendation API

Exposes the AI funnel recommendation engine via REST endpoints.
Returns prioritized, actionable recommendations plus a funnel health score.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.services.funnel_ai_recommendation_service import FunnelAIRecommendationService

router = APIRouter(tags=["funnel_ai"])


@router.get("/ai/recommendations")
async def get_funnel_recommendations(
    product_id: Optional[UUID] = Query(None, description="Filter recommendations to a specific product"),
    days_back: int = Query(30, ge=1, le=365, description="Analysis window in days"),
    max_recommendations: int = Query(10, ge=1, le=20, description="Max number of recommendations"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get AI-powered funnel recommendations for the authenticated organization.

    Returns:
    - `health_score`: Overall funnel health across 4 dimensions (0-100)
    - `recommendations`: Prioritized list of actionable improvements
    - `metrics_snapshot`: Key funnel metrics used in the analysis
    """
    service = FunnelAIRecommendationService(db)
    return await service.get_recommendations(
        organization_id=UUID(str(current_user.organization_id)),
        product_id=product_id,
        days_back=days_back,
        max_recommendations=max_recommendations,
    )


@router.get("/ai/recommendations/products/{product_id}")
async def get_product_recommendations(
    product_id: UUID,
    days_back: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get AI recommendations scoped to a specific product.
    """
    service = FunnelAIRecommendationService(db)
    return await service.get_product_recommendations(
        organization_id=UUID(str(current_user.organization_id)),
        product_id=product_id,
        days_back=days_back,
    )
