from datetime import date, timedelta
from typing import Annotated, TypedDict, cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.metric import WeeklyMetric
from app.models.submission import Submission
from app.schemas.metric import WeeklyMetricOut

router = APIRouter(prefix="/metrics", tags=["metrics"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
MetricLimit = Annotated[int, Query(ge=1, le=52)]
HistoryWeeks = Annotated[int, Query(ge=1, le=52)]


class LossAnalysisItem(TypedDict):
    reason: str
    count: int


@router.get("", response_model=list[WeeklyMetricOut])
async def list_metrics(limit: MetricLimit, db: DbSession) -> list[WeeklyMetricOut]:
    try:
        result = await db.execute(
            select(WeeklyMetric).order_by(desc(WeeklyMetric.week_start)).limit(limit)
        )
        metrics = list(result.scalars().all())
        return [WeeklyMetricOut.model_validate(metric) for metric in metrics]
    except Exception:
        return []


@router.get("/current-week", response_model=WeeklyMetricOut | None)
async def current_week(db: DbSession) -> WeeklyMetricOut | None:
    week_start = date.today() - timedelta(days=date.today().weekday())
    try:
        result = await db.execute(
            select(WeeklyMetric).where(WeeklyMetric.week_start == week_start).limit(1)
        )
        metric = result.scalar_one_or_none()
        return WeeklyMetricOut.model_validate(metric) if metric is not None else None
    except Exception:
        return None


@router.get("/history", response_model=list[WeeklyMetricOut])
async def metric_history(weeks: HistoryWeeks, db: DbSession) -> list[WeeklyMetricOut]:
    try:
        result = await db.execute(
            select(WeeklyMetric).order_by(desc(WeeklyMetric.week_start)).limit(weeks)
        )
        metrics = list(result.scalars().all())
        return [WeeklyMetricOut.model_validate(metric) for metric in metrics]
    except Exception:
        return []


@router.get("/loss-analysis")
async def loss_analysis(db: DbSession) -> list[LossAnalysisItem]:
    try:
        result = await db.execute(
            select(
                Submission.lost_reason_primary.label("reason"),
                func.count().label("count"),
            )
            .where(Submission.status == "lost")
            .group_by(Submission.lost_reason_primary)
            .order_by(desc("count"))
        )
        rows = result.mappings().all()
        return [
            {
                "reason": cast(str | None, row["reason"]) or "unknown",
                "count": int(cast(int, row["count"])),
            }
            for row in rows
        ]
    except Exception:
        return []
