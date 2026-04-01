import logging
from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class LearningEngine(BaseAgent):
    name = "learning_engine"

    async def handle_win(self, payload: dict) -> None:
        sub_id = payload.get("submission_id")
        actual_value = payload.get("actual_value_thb", 0)
        try:
            await self._record_outcome(sub_id, "positive", actual_value)
        except Exception as e:
            logger.error(f"LearningEngine handle_win failed: {e}")

    async def handle_loss(self, payload: dict) -> None:
        sub_id = payload.get("submission_id")
        lost_reason = payload.get("lost_reason", "unknown")
        try:
            await self._record_outcome(sub_id, "negative", 0, lost_reason=lost_reason)
        except Exception as e:
            logger.error(f"LearningEngine handle_loss failed: {e}")

    async def _record_outcome(self, sub_id, outcome: str, value: float, lost_reason: str = None) -> None:
        from app.database import AsyncSessionLocal
        from app.models.submission import Submission
        from app.models.opportunity import Opportunity
        from app.models.outcome_pattern import OutcomePattern
        from app.models.cognitive_state import CognitiveState
        from sqlalchemy import select, desc

        async with AsyncSessionLocal() as db:
            sub = await db.get(Submission, sub_id) if sub_id else None
            opp = await db.get(Opportunity, sub.opportunity_id) if sub else None
            cog = await db.execute(select(CognitiveState).order_by(desc(CognitiveState.date)).limit(1))
            state = cog.scalar_one_or_none()

            pattern = OutcomePattern(
                opportunity_id=opp.id if opp else None,
                submission_id=sub_id,
                opportunity_type=opp.type if opp else None,
                money_score=opp.money_score if opp else None,
                brand_score=opp.brand_score if opp else None,
                network_score=opp.network_score if opp else None,
                startup_score=opp.startup_score if opp else None,
                effort_score=opp.effort_score if opp else None,
                total_score=opp.total_score if opp else None,
                decision_at_time=opp.decision if opp else None,
                energy_at_time=state.energy if state else None,
                outcome=outcome,
                actual_value_thb=value,
                lost_reason=lost_reason,
            )
            db.add(pattern)
            await db.commit()

    async def run_weekly_analysis(self) -> None:
        """Analyze outcomes and potentially update scoring weights."""
        try:
            from app.database import AsyncSessionLocal
            from app.models.outcome_pattern import OutcomePattern
            from app.models.scoring_weight_history import ScoringWeightHistory
            from app.core.identity import identity
            from sqlalchemy import select, func

            async with AsyncSessionLocal() as db:
                total = await db.scalar(select(func.count()).select_from(OutcomePattern))
                if (total or 0) < 10:
                    logger.info("LearningEngine: not enough data yet (need 10+ outcomes)")
                    return

                # For now just log — full weight adjustment needs more data
                positives = await db.scalar(select(func.count()).where(OutcomePattern.outcome == "positive"))
                logger.info(f"LearningEngine: {positives}/{total} positive outcomes. Weights stable.")
        except Exception as e:
            logger.error(f"Weekly analysis failed: {e}")


learning_engine = LearningEngine()
