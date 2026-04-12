import logging
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class CompoundEngine(BaseAgent):
    name = "compound_engine"

    async def handle_submission_sent(self, payload: dict[str, object]) -> None:
        try:
            await self._update_weekly_metrics(proposals_sent=1)
        except Exception as exc:
            logger.error("CompoundEngine handle_submission_sent failed: %s", exc, exc_info=True)

    async def handle_win(self, payload: dict[str, object]) -> None:
        revenue = Decimal(str(payload.get("actual_value_thb", 0)))
        try:
            await self._update_weekly_metrics(revenue=revenue, proposals_won=1)
        except Exception as exc:
            logger.error("CompoundEngine handle_win failed: %s", exc, exc_info=True)

    async def run(self) -> dict[str, Any]:
        metrics = await self._calculate_weekly_metrics()
        strategy = await self._generate_strategy(metrics)
        if not strategy:
            strategy = self._heuristic_strategy(metrics)

        await self.log_audit(
            "compound_engine.weekly_report",
            {
                "week_start": metrics["week_start"],
                "metrics": metrics,
                "strategy": strategy,
            },
        )
        await self.bus.emit(
            "strategy.generated",
            {
                "week_start": metrics["week_start"],
                "metrics": metrics,
                "strategy": strategy,
            },
        )
        return {"metrics": metrics, "strategy": strategy}

    async def _calculate_weekly_metrics(self) -> dict[str, Any]:
        from app.database import AsyncSessionLocal
        from app.models.metric import WeeklyMetric
        from app.models.opportunity import Opportunity
        from app.models.submission import Submission

        week_start = date.today() - timedelta(days=date.today().weekday())
        window_start = datetime.combine(week_start, time.min, tzinfo=timezone.utc)
        window_end = window_start + timedelta(days=7)

        async with AsyncSessionLocal() as db:
            opportunities_found = int(
                await db.scalar(
                    select(func.count())
                    .select_from(Opportunity)
                    .where(Opportunity.found_at >= window_start, Opportunity.found_at < window_end)
                )
                or 0
            )
            opportunities_scored = int(
                await db.scalar(
                    select(func.count())
                    .select_from(Opportunity)
                    .where(
                        Opportunity.updated_at >= window_start,
                        Opportunity.updated_at < window_end,
                        Opportunity.total_score.is_not(None),
                    )
                )
                or 0
            )
            opportunities_decided = int(
                await db.scalar(
                    select(func.count())
                    .select_from(Opportunity)
                    .where(
                        Opportunity.updated_at >= window_start,
                        Opportunity.updated_at < window_end,
                        Opportunity.decision.is_not(None),
                    )
                )
                or 0
            )
            opportunities_actioned = int(
                await db.scalar(
                    select(func.count())
                    .select_from(Opportunity)
                    .where(
                        Opportunity.acted_on_at >= window_start,
                        Opportunity.acted_on_at < window_end,
                    )
                )
                or 0
            )
            opportunities_ignored = int(
                await db.scalar(
                    select(func.count())
                    .select_from(Opportunity)
                    .where(
                        Opportunity.updated_at >= window_start,
                        Opportunity.updated_at < window_end,
                        Opportunity.decision == "skip",
                    )
                )
                or 0
            )

            submissions = list(
                (
                    await db.execute(
                        select(Submission).where(
                            Submission.created_at >= window_start,
                            Submission.created_at < window_end,
                        )
                    )
                ).scalars()
            )
            wins = [submission for submission in submissions if submission.status == "won"]
            losses = [submission for submission in submissions if submission.status == "lost"]
            revenue = sum(
                Decimal(str(submission.actual_value or 0))
                for submission in wins
            )
            proposals_sent = len(submissions)
            close_rate = (
                Decimal(str(round((len(wins) / proposals_sent) * 100, 2)))
                if proposals_sent
                else Decimal("0")
            )

            metric = (
                await db.execute(
                    select(WeeklyMetric).where(WeeklyMetric.week_start == week_start).limit(1)
                )
            ).scalar_one_or_none()
            if metric is None:
                metric = WeeklyMetric(week_start=week_start)
                db.add(metric)

            metric.opps_found = opportunities_found
            metric.opps_scored = opportunities_scored
            metric.opps_decided = opportunities_decided
            metric.opps_actioned = opportunities_actioned
            metric.opps_ignored = opportunities_ignored
            metric.proposals_sent = proposals_sent
            metric.proposals_won = len(wins)
            metric.close_rate = close_rate
            metric.revenue_thb = revenue

            await db.commit()

        return {
            "week_start": week_start.isoformat(),
            "opportunities_found": opportunities_found,
            "opportunities_scored": opportunities_scored,
            "opportunities_decided": opportunities_decided,
            "opportunities_actioned": opportunities_actioned,
            "opportunities_ignored": opportunities_ignored,
            "submissions": proposals_sent,
            "wins": len(wins),
            "losses": len(losses),
            "revenue_thb": float(revenue),
            "close_rate": float(close_rate),
        }

    async def _generate_strategy(self, metrics: dict[str, Any]) -> str | None:
        if self.llm.is_degraded():
            return None
        try:
            return await self.llm.complete(
                system="Synthesize weekly execution data into one short strategy recommendation.",
                user=(
                    f"Metrics: {metrics}\n"
                    "Return one concise paragraph with the main focus for next week."
                ),
                max_tokens=250,
                temperature=0.4,
                allow_fallback=True,
                task_class="strategy",
                complexity=4,
            )
        except Exception as exc:
            logger.warning("CompoundEngine strategy generation fell back to heuristic: %s", exc)
            return None

    def _heuristic_strategy(self, metrics: dict[str, Any]) -> str:
        if metrics["losses"] > metrics["wins"]:
            return "Tighten qualification and proposal differentiation before increasing volume."
        if metrics["wins"] > 0 and metrics["revenue_thb"] > 0:
            return "Double down on the opportunity type that just converted and protect time for similar work."
        if metrics["submissions"] == 0:
            return "Pipeline is thin; focus on generating one strong opportunity and turning it into a submitted proposal."
        return "Keep the current pace, but prune low-conviction items so the week stays focused."

    async def _update_weekly_metrics(
        self,
        *,
        revenue: Decimal = Decimal("0"),
        proposals_sent: int = 0,
        proposals_won: int = 0,
    ) -> None:
        from app.database import AsyncSessionLocal
        from app.models.metric import WeeklyMetric

        week_start = date.today() - timedelta(days=date.today().weekday())
        async with AsyncSessionLocal() as db:
            metric = (
                await db.execute(
                    select(WeeklyMetric).where(WeeklyMetric.week_start == week_start).limit(1)
                )
            ).scalar_one_or_none()
            if metric is None:
                metric = WeeklyMetric(week_start=week_start)
                db.add(metric)

            if proposals_sent:
                metric.proposals_sent = (metric.proposals_sent or 0) + proposals_sent
            if proposals_won:
                metric.proposals_won = (metric.proposals_won or 0) + proposals_won
            if revenue:
                metric.revenue_thb = Decimal(str(metric.revenue_thb or 0)) + revenue
            await db.commit()


compound_engine = CompoundEngine()
