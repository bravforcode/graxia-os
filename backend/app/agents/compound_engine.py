import logging
from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class CompoundEngine(BaseAgent):
    name = "compound_engine"

    async def handle_submission_sent(self, payload: dict) -> None:
        logger.info(f"CompoundEngine: submission sent {payload.get('submission_id')}")

    async def handle_win(self, payload: dict) -> None:
        value = payload.get("actual_value_thb", 0)
        try:
            await self._update_weekly_metrics(revenue=value)
        except Exception as e:
            logger.error(f"CompoundEngine handle_win failed: {e}")

    async def _update_weekly_metrics(self, revenue: float = 0) -> None:
        from app.database import AsyncSessionLocal
        from app.models.metric import WeeklyMetric
        from sqlalchemy import select
        from datetime import date, timedelta

        week_start = date.today() - timedelta(days=date.today().weekday())
        async with AsyncSessionLocal() as db:
            q = await db.execute(select(WeeklyMetric).where(WeeklyMetric.week_start == week_start))
            metric = q.scalar_one_or_none()
            if not metric:
                metric = WeeklyMetric(week_start=week_start)
                db.add(metric)
            if revenue:
                metric.revenue_thb = (metric.revenue_thb or 0) + revenue
                metric.proposals_won = (metric.proposals_won or 0) + 1
            await db.commit()


compound_engine = CompoundEngine()
