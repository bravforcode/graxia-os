import logging
from datetime import date, timedelta
from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class StrategyAgent(BaseAgent):
    name = "strategy_agent"

    async def run(self) -> None:
        """Weekly strategic analysis — runs every Sunday."""
        if self.llm.is_degraded():
            logger.info("StrategyAgent: LLM degraded — skipping")
            return

        try:
            data = await self._gather_data()
            strategy = await self._generate_strategy(data)
            if strategy:
                await self._send_strategy_brief(strategy)
        except Exception as e:
            logger.error(f"StrategyAgent failed: {e}", exc_info=True)

    async def _gather_data(self) -> dict:
        from app.database import AsyncSessionLocal
        from app.models.metric import WeeklyMetric
        from app.models.outcome_pattern import OutcomePattern
        from app.models.opportunity import Opportunity
        from sqlalchemy import select, func, desc

        async with AsyncSessionLocal() as db:
            # Last 4 weeks metrics
            four_weeks_ago = date.today() - timedelta(weeks=4)
            metrics_q = await db.execute(select(WeeklyMetric).where(WeeklyMetric.week_start >= four_weeks_ago).order_by(desc(WeeklyMetric.week_start)))
            metrics = metrics_q.scalars().all()

            # Outcome patterns last 8 weeks
            eight_weeks_ago = date.today() - timedelta(weeks=8)
            patterns_q = await db.execute(select(OutcomePattern).where(OutcomePattern.created_at >= eight_weeks_ago).order_by(desc(OutcomePattern.created_at)).limit(20))
            patterns = patterns_q.scalars().all()

            # Active pipeline
            pipeline_q = await db.execute(select(Opportunity).where(Opportunity.status.in_(["decided", "approved", "in_progress"])).limit(10))
            pipeline = pipeline_q.scalars().all()

        return {"metrics": metrics, "patterns": patterns, "pipeline": pipeline}

    async def _generate_strategy(self, data: dict) -> str | None:
        from app.core.identity import identity
        metrics_summary = f"{len(data['metrics'])} weeks of data, {len(data['patterns'])} outcome patterns"
        pipeline_summary = f"{len(data['pipeline'])} active opportunities"

        system = f"""You are the Strategic Advisor for {identity.get_profile()['personal']['name']}.
Your job is NOT to find more things. It is to ensure they focus on the RIGHT things.
Be honest and direct. Be specific. Say what to STOP, CONTINUE, and DOUBLE DOWN on.

{self.agent_context}"""

        user = f"""Weekly strategic review — {date.today()}

Data available: {metrics_summary}, {pipeline_summary}

Provide a concise strategic brief (under 300 words):
1. STOP: What to stop doing or deprioritize
2. CONTINUE: What is working and should continue
3. DOUBLE DOWN: Where to invest more effort this week
4. THIS WEEK'S FOCUS: One clear primary focus for the week

Be specific. Reference actual numbers and patterns if available."""

        return await self.llm.complete(
            system=system,
            user=user,
            model=self.llm.default_model,
            max_tokens=500,
            temperature=0.6,
            allow_fallback=True,
            task_class="strategy",
            complexity=8,
        )

    async def _send_strategy_brief(self, strategy: str) -> None:
        await self.log_audit(
            "strategy.generated",
            {"date": str(date.today()), "strategy": strategy},
        )
        try:
            from app.telegram_bot.bot import send_message
            await send_message(f"🧭 *Weekly Strategy Brief — {date.today()}*\n\n{strategy}")
        except Exception as e:
            logger.error(f"Strategy brief send failed: {e}")


strategy_agent = StrategyAgent()
