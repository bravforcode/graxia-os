"""
Analytics API — Real-time dashboards, AI usage logs, and cost tracking.
Features 41-55: Analytics, dashboards, reporting, and cost tracking.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.models.analytics import (
    AgentPerformanceAnalytics,
    AnalyticsDashboard,
    AnalyticsMetric,
    AnalyticsWidget,
    SkillUsageAnalytics,
)
from app.models.usage_log import UsageLog
from app.models.user import User

router = APIRouter(prefix="/analytics", tags=["analytics"])


# Request/Response Models
class DashboardResponse(BaseModel):
    id: str
    name: str
    description: str | None
    layout: dict[str, Any]
    time_range_default: str
    refresh_interval_seconds: int | None
    is_active: bool


class WidgetResponse(BaseModel):
    id: str
    dashboard_id: str
    widget_type: str
    title: str
    data_source: str
    metric_name: str
    filters: dict[str, Any]
    chart_type: str | None
    position: dict[str, int]


class MetricResponse(BaseModel):
    metric_key: str
    metric_name: str
    dimension: str
    dimension_value: str
    period_start: datetime
    period_end: datetime
    value_numeric: float | None
    value_count: int | None
    value_text: str | None


class UsageStatsResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    total_requests: int
    total_cost_usd: float
    requests_by_day: list[dict[str, Any]]
    cost_by_day: list[dict[str, Any]]
    top_skills: list[dict[str, Any]]
    top_agents: list[dict[str, Any]]


class CostBreakdownResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    total_cost_usd: float
    breakdown_by_model: dict[str, float]
    breakdown_by_skill: dict[str, float]
    cost_trend: list[dict[str, Any]]
    projected_monthly_cost: float


# Dashboard Endpoints
@router.get("/dashboards")
async def list_dashboards(
    user: User = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """List available dashboards for the user."""
    result = await db.execute(
        select(AnalyticsDashboard).where(
            (AnalyticsDashboard.owner_agent_id.is_(None)) | 
            (AnalyticsDashboard.is_shared == True)
        )
    )
    dashboards = result.scalars().all()
    return [
        DashboardResponse(
            id=str(d.id),
            name=d.name,
            description=d.description,
            layout=d.layout or {},
            time_range_default=d.time_range_default,
            refresh_interval_seconds=d.refresh_interval_seconds,
            is_active=d.is_active,
        )
        for d in dashboards
    ]


@router.get("/dashboards/{dashboard_id}")
async def get_dashboard(
    dashboard_id: str,
    user: User = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard details with widgets."""
    # Get dashboard
    dashboard = await db.get(AnalyticsDashboard, dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    
    # Get widgets
    widgets_result = await db.execute(
        select(AnalyticsWidget).where(AnalyticsWidget.dashboard_id == dashboard_id)
        .order_by(AnalyticsWidget.position_y, AnalyticsWidget.position_x)
    )
    widgets = widgets_result.scalars().all()
    
    return {
        "dashboard": DashboardResponse(
            id=str(dashboard.id),
            name=dashboard.name,
            description=dashboard.description,
            layout=dashboard.layout or {},
            time_range_default=dashboard.time_range_default,
            refresh_interval_seconds=dashboard.refresh_interval_seconds,
            is_active=dashboard.is_active,
        ),
        "widgets": [
            WidgetResponse(
                id=str(w.id),
                dashboard_id=str(w.dashboard_id),
                widget_type=w.widget_type,
                title=w.title,
                data_source=w.data_source,
                metric_name=w.metric_name,
                filters=w.filters or {},
                chart_type=w.chart_type,
                position={"x": w.position_x, "y": w.position_y, "width": w.width, "height": w.height},
            )
            for w in widgets
        ]
    }


# Usage Analytics Endpoints
@router.get("/usage/stats")
async def get_usage_stats(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> UsageStatsResponse:
    """Get AI usage statistics for the last N days."""
    if not user.organization:
        raise HTTPException(status_code=400, detail="No organization")
    
    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=days)
    
    # Get usage logs
    result = await db.execute(
        select(
            func.date(UsageLog.created_at).label("date"),
            func.sum(UsageLog.quantity).label("requests"),
            func.sum(UsageLog.quantity * UsageLog.quantity).label("cost"),  # Simplified cost calc
        )
        .where(UsageLog.organization_id == user.organization.id)
        .where(UsageLog.created_at >= start_date)
        .where(UsageLog.feature.in_(["ai_request", "skill_execution"]))
        .group_by(func.date(UsageLog.created_at))
        .order_by(func.date(UsageLog.created_at))
    )
    
    daily_stats = result.all()
    
    total_requests = sum(s.requests or 0 for s in daily_stats)
    total_cost = sum(s.cost or 0 for s in daily_stats)
    
    requests_by_day = [
        {"date": str(s.date), "requests": s.requests or 0}
        for s in daily_stats
    ]
    
    cost_by_day = [
        {"date": str(s.date), "cost": float(s.cost or 0)}
        for s in daily_stats
    ]
    
    # Get top skills (simplified)
    top_skills_result = await db.execute(
        select(UsageLog.feature, func.count().label("count"))
        .where(UsageLog.organization_id == user.organization.id)
        .where(UsageLog.created_at >= start_date)
        .where(UsageLog.feature.like("skill_%"))
        .group_by(UsageLog.feature)
        .order_by(func.count().desc())
        .limit(5)
    )
    top_skills = [
        {"skill": r.feature, "count": r.count}
        for r in top_skills_result
    ]
    
    # Get top agents (simplified)
    top_agents_result = await db.execute(
        select(UsageLog.metadata["agent_name"], func.count().label("count"))
        .where(UsageLog.organization_id == user.organization.id)
        .where(UsageLog.created_at >= start_date)
        .where(UsageLog.metadata["agent_name"].isnot(None))
        .group_by(UsageLog.metadata["agent_name"])
        .order_by(func.count().desc())
        .limit(5)
    )
    top_agents = [
        {"agent": r.agent_name, "count": r.count}
        for r in top_agents_result
    ]
    
    return UsageStatsResponse(
        period_start=start_date,
        period_end=end_date,
        total_requests=total_requests,
        total_cost_usd=total_cost,
        requests_by_day=requests_by_day,
        cost_by_day=cost_by_day,
        top_skills=top_skills,
        top_agents=top_agents,
    )


@router.get("/usage/cost-breakdown")
async def get_cost_breakdown(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
) -> CostBreakdownResponse:
    """Get detailed cost breakdown by model and skill."""
    if not user.organization:
        raise HTTPException(status_code=400, detail="No organization")
    
    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=days)
    
    # Get cost by model
    model_costs_result = await db.execute(
        select(
            UsageLog.metadata["model"], 
            func.sum(UsageLog.quantity * UsageLog.quantity).label("cost")
        )
        .where(UsageLog.organization_id == user.organization.id)
        .where(UsageLog.created_at >= start_date)
        .where(UsageLog.feature == "ai_request")
        .where(UsageLog.metadata["model"].isnot(None))
        .group_by(UsageLog.metadata["model"])
    )
    
    breakdown_by_model = {
        r.model: float(r.cost or 0)
        for r in model_costs_result
    }
    
    # Get cost by skill
    skill_costs_result = await db.execute(
        select(
            UsageLog.feature,
            func.sum(UsageLog.quantity * UsageLog.quantity).label("cost")
        )
        .where(UsageLog.organization_id == user.organization.id)
        .where(UsageLog.created_at >= start_date)
        .where(UsageLog.feature.like("skill_%"))
        .group_by(UsageLog.feature)
    )
    
    breakdown_by_skill = {
        r.feature: float(r.cost or 0)
        for r in skill_costs_result
    }
    
    total_cost = sum(breakdown_by_model.values()) + sum(breakdown_by_skill.values())
    
    # Calculate trend (simplified - last 7 days vs previous 7 days)
    mid_date = end_date - timedelta(days=7)
    prev_start = start_date
    
    recent_cost = await db.execute(
        select(func.sum(UsageLog.quantity * UsageLog.quantity))
        .where(UsageLog.organization_id == user.organization.id)
        .where(UsageLog.created_at >= mid_date)
        .where(UsageLog.created_at < end_date)
    )
    recent_total = float(recent_cost.scalar() or 0)
    
    previous_cost = await db.execute(
        select(func.sum(UsageLog.quantity * UsageLog.quantity))
        .where(UsageLog.organization_id == user.organization.id)
        .where(UsageLog.created_at >= prev_start)
        .where(UsageLog.created_at < mid_date)
    )
    previous_total = float(previous_cost.scalar() or 0)
    
    # Project monthly cost based on recent trend
    daily_average = recent_total / 7 if recent_total > 0 else 0
    projected_monthly = daily_average * 30
    
    cost_trend = [
        {"period": "previous_7_days", "cost": previous_total},
        {"period": "recent_7_days", "cost": recent_total},
    ]
    
    return CostBreakdownResponse(
        period_start=start_date,
        period_end=end_date,
        total_cost_usd=total_cost,
        breakdown_by_model=breakdown_by_model,
        breakdown_by_skill=breakdown_by_skill,
        cost_trend=cost_trend,
        projected_monthly_cost=projected_monthly,
    )


@router.get("/metrics/{metric_key}")
async def get_metric(
    metric_key: str,
    days: int = Query(default=7, ge=1, le=90),
    user: User = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get specific metric over time."""
    if not user.organization:
        raise HTTPException(status_code=400, detail="No organization")
    
    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=days)
    
    result = await db.execute(
        select(AnalyticsMetric)
        .where(AnalyticsMetric.metric_key == metric_key)
        .where(AnalyticsMetric.period_start >= start_date)
        .where(AnalyticsMetric.period_end <= end_date)
        .order_by(AnalyticsMetric.period_start)
    )
    
    metrics = result.scalars().all()
    
    return [
        MetricResponse(
            metric_key=m.metric_key,
            metric_name=m.metric_name,
            dimension=m.dimension,
            dimension_value=m.dimension_value,
            period_start=m.period_start,
            period_end=m.period_end,
            value_numeric=float(m.value_numeric) if m.value_numeric else None,
            value_count=m.value_count,
            value_text=m.value_text,
        )
        for m in metrics
    ]


# Skill Performance Analytics
@router.get("/skills/performance")
async def get_skill_performance(
    days: int = Query(default=30, ge=1, le=90),
    user: User = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get skill usage and performance analytics."""
    if not user.organization:
        raise HTTPException(status_code=400, detail="No organization")
    
    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=days)
    
    result = await db.execute(
        select(SkillUsageAnalytics)
        .where(SkillUsageAnalytics.period_date >= start_date)
        .where(SkillUsageAnalytics.period_date <= end_date)
        .order_by(SkillUsageAnalytics.period_date.desc())
        .limit(100)
    )
    
    analytics = result.scalars().all()
    
    return [
        {
            "skill_id": str(a.skill_id),
            "period_date": a.period_date.isoformat(),
            "total_invocations": a.total_invocations,
            "unique_agents": a.unique_agents,
            "avg_execution_time_ms": float(a.avg_execution_time_ms),
            "success_rate": float(a.success_rate),
            "total_tokens_consumed": a.total_tokens_consumed,
        }
        for a in analytics
    ]


# Agent Performance Analytics
@router.get("/agents/performance")
async def get_agent_performance(
    days: int = Query(default=30, ge=1, le=90),
    user: User = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get agent performance analytics."""
    if not user.organization:
        raise HTTPException(status_code=400, detail="No organization")
    
    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=days)
    
    result = await db.execute(
        select(AgentPerformanceAnalytics)
        .where(AgentPerformanceAnalytics.period_date >= start_date)
        .where(AgentPerformanceAnalytics.period_date <= end_date)
        .order_by(AgentPerformanceAnalytics.period_date.desc())
        .limit(100)
    )
    
    analytics = result.scalars().all()
    
    return [
        {
            "agent_id": str(a.agent_id),
            "period_date": a.period_date.isoformat(),
            "total_executions": a.total_executions,
            "successful_executions": a.successful_executions,
            "failed_executions": a.failed_executions,
            "average_skill_rating": float(a.average_skill_rating) if a.average_skill_rating else None,
        }
        for a in analytics
    ]


# Real-time Metrics (for dashboard widgets)
@router.get("/realtime/overview")
async def get_realtime_overview(
    user: User = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get real-time overview metrics for dashboard."""
    if not user.organization:
        raise HTTPException(status_code=400, detail="No organization")
    
    # Get today's usage
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    
    today_requests = await db.execute(
        select(func.sum(UsageLog.quantity))
        .where(UsageLog.organization_id == user.organization.id)
        .where(UsageLog.created_at >= today_start)
        .where(UsageLog.feature.in_(["ai_request", "skill_execution"]))
    )
    total_requests_today = int(today_requests.scalar() or 0)
    
    # Get current month cost
    month_start = today_start.replace(day=1)
    month_cost = await db.execute(
        select(func.sum(UsageLog.quantity * UsageLog.quantity))
        .where(UsageLog.organization_id == user.organization.id)
        .where(UsageLog.created_at >= month_start)
    )
    total_cost_month = float(month_cost.scalar() or 0)
    
    # Get active skills (simplified)
    active_skills = await db.execute(
        select(func.count(func.distinct(UsageLog.feature)))
        .where(UsageLog.organization_id == user.organization.id)
        .where(UsageLog.created_at >= today_start)
        .where(UsageLog.feature.like("skill_%"))
    )
    active_skills_count = int(active_skills.scalar() or 0)
    
    # Get error rate (simplified)
    total_executions = await db.execute(
        select(func.sum(UsageLog.quantity))
        .where(UsageLog.organization_id == user.organization.id)
        .where(UsageLog.created_at >= today_start)
        .where(UsageLog.feature.in_(["skill_execution", "agent_execution"]))
    )
    error_executions = await db.execute(
        select(func.sum(UsageLog.quantity))
        .where(UsageLog.organization_id == user.organization.id)
        .where(UsageLog.created_at >= today_start)
        .where(UsageLog.feature == "skill_error")
    )
    
    total_exec = int(total_executions.scalar() or 0)
    error_exec = int(error_executions.scalar() or 0)
    error_rate = (error_exec / total_exec * 100) if total_exec > 0 else 0
    
    return {
        "requests_today": total_requests_today,
        "cost_this_month": total_cost_month,
        "active_skills": active_skills_count,
        "error_rate_percent": error_rate,
        "last_updated": datetime.now(UTC).isoformat(),
    }
