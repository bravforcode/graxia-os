from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.database import get_db
from app.models.metric import WeeklyMetric
from app.schemas.metric import WeeklyMetricOut

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", response_model=list[WeeklyMetricOut])
async def list_metrics(limit: int = 12, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WeeklyMetric).order_by(desc(WeeklyMetric.week_start)).limit(limit))
    return result.scalars().all()
