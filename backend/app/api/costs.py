import calendar
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.openclaw_usage import OpenClawUsage

router = APIRouter(prefix="/api/v1/costs", tags=["costs"])
DbSession = Annotated[AsyncSession, Depends(get_db)]


class BudgetWindow(BaseModel):
    cost_usd: float
    budget_usd: float
    percentage: float


class CostSummary(BaseModel):
    today: BudgetWindow
    week: BudgetWindow
    month: BudgetWindow


class UsageSummary(BaseModel):
    period_days: int
    total_requests: int
    total_cost_usd: float
    avg_cost_per_request: float
    by_platform: dict[str, dict[str, float | int]]


@router.get("/summary", response_model=CostSummary)
async def get_cost_summary(db: DbSession):
    now = datetime.now(UTC)
    today = now.date()
    week_ago = now - timedelta(days=7)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    today_query = select(func.sum(OpenClawUsage.cost_usd)).where(func.date(OpenClawUsage.created_at) == today)
    today_result = await db.execute(today_query)
    today_cost = float(today_result.scalar() or 0)

    week_query = select(func.sum(OpenClawUsage.cost_usd)).where(OpenClawUsage.created_at >= week_ago)
    week_result = await db.execute(week_query)
    week_cost = float(week_result.scalar() or 0)

    month_query = select(func.sum(OpenClawUsage.cost_usd)).where(OpenClawUsage.created_at >= month_start)
    month_result = await db.execute(month_query)
    month_cost = float(month_result.scalar() or 0)

    daily_budget = float(settings.MAX_DAILY_AI_COST_USD)
    weekly_budget = round(daily_budget * 7, 2)
    monthly_budget = float(settings.MAX_MONTHLY_AI_COST_USD)

    return CostSummary(
        today=BudgetWindow(
            cost_usd=today_cost,
            budget_usd=daily_budget,
            percentage=round((today_cost / daily_budget) * 100, 1) if daily_budget > 0 else 0,
        ),
        week=BudgetWindow(
            cost_usd=week_cost,
            budget_usd=weekly_budget,
            percentage=round((week_cost / weekly_budget) * 100, 1) if weekly_budget > 0 else 0,
        ),
        month=BudgetWindow(
            cost_usd=month_cost,
            budget_usd=monthly_budget,
            percentage=round((month_cost / monthly_budget) * 100, 1) if monthly_budget > 0 else 0,
        )
    )


@router.get("/usage", response_model=UsageSummary)
async def get_usage_history(
    db: DbSession,
    platform: str | None = Query(None, description="Filter by platform"),
    days: int = Query(7, le=90, description="Number of days to look back"),
    limit: int = Query(100, le=500),
):
    since = datetime.now(UTC) - timedelta(days=days)
    query = select(OpenClawUsage).where(OpenClawUsage.created_at >= since)

    if platform:
        query = query.where(OpenClawUsage.platform == platform)

    query = query.order_by(OpenClawUsage.created_at.desc()).limit(limit)
    result = await db.execute(query)
    usage_records = result.scalars().all()

    total_requests = len(usage_records)
    total_cost = sum(float(record.cost_usd or 0) for record in usage_records)
    by_platform: dict[str, dict[str, float | int]] = {}
    for record in usage_records:
        platform_name = record.platform
        bucket = by_platform.setdefault(platform_name, {"requests": 0, "cost_usd": 0.0})
        bucket["requests"] = int(bucket["requests"]) + 1
        bucket["cost_usd"] = round(float(bucket["cost_usd"]) + float(record.cost_usd or 0), 4)

    return UsageSummary(
        period_days=days,
        total_requests=total_requests,
        total_cost_usd=round(total_cost, 4),
        avg_cost_per_request=round(total_cost / total_requests, 4) if total_requests else 0.0,
        by_platform=by_platform,
    )


@router.get("/forecast")
async def get_cost_forecast(db: DbSession):
    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    days_elapsed = now.day
    days_in_month = calendar.monthrange(now.year, now.month)[1]

    month_query = select(func.sum(OpenClawUsage.cost_usd)).where(OpenClawUsage.created_at >= month_start)
    month_result = await db.execute(month_query)
    month_cost = float(month_result.scalar() or 0)

    daily_avg = month_cost / days_elapsed if days_elapsed > 0 else 0
    forecast = daily_avg * days_in_month
    monthly_budget = float(settings.MAX_MONTHLY_AI_COST_USD)

    return {
        "current_cost": month_cost,
        "forecasted_cost": round(forecast, 2),
        "daily_average": round(daily_avg, 2),
        "days_elapsed": days_elapsed,
        "days_remaining": max(days_in_month - days_elapsed, 0),
        "budget": monthly_budget,
        "over_budget": forecast > monthly_budget,
    }
