import logging
from decimal import Decimal
from statistics import mean
from typing import Any, cast

from sqlalchemy import desc, func, select

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class LearningEngine(BaseAgent):
    name = "learning_engine"

    async def handle_win(self, payload: dict[str, object]) -> None:
        submission_id = payload.get("submission_id")
        actual_value = float(cast(int | float | str, payload.get("actual_value_thb", 0)))
        try:
            await self._record_outcome(submission_id, "positive", actual_value)
        except Exception as exc:
            logger.error("LearningEngine handle_win failed: %s", exc, exc_info=True)

    async def handle_loss(self, payload: dict[str, object]) -> None:
        submission_id = payload.get("submission_id")
        lost_reason = str(payload.get("lost_reason", "unknown"))
        try:
            await self._record_outcome(
                submission_id,
                "negative",
                0,
                lost_reason=lost_reason,
            )
        except Exception as exc:
            logger.error("LearningEngine handle_loss failed: %s", exc, exc_info=True)

    async def _record_outcome(
        self,
        submission_id: object,
        outcome: str,
        value: float,
        lost_reason: str | None = None,
    ) -> None:
        from app.database import AsyncSessionLocal
        from app.models.cognitive_state import CognitiveState
        from app.models.opportunity import Opportunity
        from app.models.outcome_pattern import OutcomePattern
        from app.models.submission import Submission

        async with AsyncSessionLocal() as db:
            submission = await db.get(Submission, submission_id) if submission_id else None
            opportunity = (
                await db.get(Opportunity, submission.opportunity_id)
                if submission and submission.opportunity_id
                else None
            )
            cognitive_state_result = await db.execute(
                select(CognitiveState).order_by(desc(CognitiveState.date)).limit(1)
            )
            cognitive_state = cognitive_state_result.scalar_one_or_none()

            pattern = OutcomePattern(
                opportunity_id=getattr(opportunity, "id", None),
                submission_id=getattr(submission, "id", None),
                opportunity_type=getattr(opportunity, "type", None),
                money_score=getattr(opportunity, "money_score", None),
                brand_score=getattr(opportunity, "brand_score", None),
                network_score=getattr(opportunity, "network_score", None),
                startup_score=getattr(opportunity, "startup_score", None),
                effort_score=getattr(opportunity, "effort_score", None),
                total_score=getattr(opportunity, "total_score", None),
                decision_at_time=getattr(opportunity, "decision", None),
                energy_at_time=getattr(cognitive_state, "energy", None),
                outcome=outcome,
                actual_value_thb=Decimal(str(value)),
                lost_reason=lost_reason,
                notes=getattr(submission, "outcome_notes", None),
            )
            db.add(pattern)
            await db.commit()

        await self.log_audit(
            "learning_engine.outcome_recorded",
            {
                "submission_id": str(submission_id) if submission_id else None,
                "outcome": outcome,
                "actual_value_thb": value,
                "lost_reason": lost_reason,
            },
        )

    async def analyze_loss(self, submission) -> dict[str, Any]:
        """Produce a short actionable lesson for weekly review and post-mortems."""
        from app.database import AsyncSessionLocal
        from app.models.opportunity import Opportunity

        opportunity = None
        if getattr(submission, "opportunity_id", None):
            async with AsyncSessionLocal() as db:
                opportunity = await db.get(Opportunity, submission.opportunity_id)

        reason = getattr(submission, "lost_reason_primary", None) or "unknown"
        if not self.llm.is_degraded():
            try:
                system = (
                    "Analyze a lost submission and return compact JSON with keys "
                    "category, key_insight, recommendation, confidence."
                )
                user = (
                    f"Reason: {reason}\n"
                    f"Stage: {getattr(submission, 'lost_stage', None) or 'unknown'}\n"
                    f"Opportunity: {getattr(opportunity, 'title', 'unknown')}\n"
                    f"Type: {getattr(opportunity, 'type', 'unknown')}\n"
                    f"Submission: {(getattr(submission, 'content', '') or '')[:400]}"
                )
                result = await self.llm.complete_json(
                    system=system,
                    user=user,
                    task_class="analysis",
                    complexity=4,
                )
                return {
                    "category": str(result.get("category", "execution")),
                    "key_insight": str(result.get("key_insight", "")).strip()
                    or self._heuristic_loss_insight(submission, opportunity)["key_insight"],
                    "recommendation": str(result.get("recommendation", "")).strip()
                    or self._heuristic_loss_insight(submission, opportunity)["recommendation"],
                    "confidence": float(result.get("confidence", 0.6)),
                }
            except Exception as exc:
                logger.warning("LearningEngine loss analysis fell back to heuristic: %s", exc)

        return self._heuristic_loss_insight(submission, opportunity)

    def _heuristic_loss_insight(self, submission, opportunity) -> dict[str, Any]:
        reason = (getattr(submission, "lost_reason_primary", None) or "unknown").replace("_", " ")
        stage = getattr(submission, "lost_stage", None) or "unknown"

        if reason in {"no reply", "weak message", "deadline missed"} or stage in {
            "no_contact",
            "proposal",
        }:
            return {
                "category": "execution",
                "key_insight": f"Loss reason was {reason}, which points to an execution gap in the outreach sequence.",
                "recommendation": "Tighten the opening hook, shorten the first message, and add a timed follow-up within 48 hours.",
                "confidence": 0.7,
            }
        if reason in {"too expensive", "weak fit", "unclear scope", "student status disadvantage"}:
            return {
                "category": "fit",
                "key_insight": f"{getattr(opportunity, 'title', 'This opportunity')} was likely mis-positioned for the buyer's budget or scope expectations.",
                "recommendation": "Pre-qualify budget and success criteria earlier, and anchor value with a narrower scope before expanding.",
                "confidence": 0.68,
            }
        if reason in {"stronger competitor"}:
            return {
                "category": "competition",
                "key_insight": "A stronger competing offer likely won on proof, specialization, or timing.",
                "recommendation": "Lead with sharper proof of shipped outcomes and show one clear differentiator in the first message.",
                "confidence": 0.62,
            }
        return {
            "category": "luck",
            "key_insight": f"The loss reason was recorded as {reason}; the dataset is still too thin for a stronger claim.",
            "recommendation": "Capture more explicit loss reasons and client objections so future analysis can move from guesswork to pattern detection.",
            "confidence": 0.45,
        }

    async def run_weekly_analysis(self) -> dict[str, Any] | None:
        """Adjust scoring weights when outcome patterns show a stable signal."""
        from app.core.identity import identity
        from app.database import AsyncSessionLocal
        from app.models.outcome_pattern import OutcomePattern

        async with AsyncSessionLocal() as db:
            total = await db.scalar(select(func.count()).select_from(OutcomePattern))
            total = int(total or 0)
            if total < 10:
                logger.info("LearningEngine: not enough data yet (need 10+ outcomes)")
                return None

            rows = list(
                (
                    await db.execute(select(OutcomePattern).order_by(desc(OutcomePattern.created_at)))
                ).scalars()
            )

        positives = [row for row in rows if row.outcome == "positive"]
        negatives = [row for row in rows if row.outcome == "negative"]
        if not positives or not negatives:
            logger.info("LearningEngine: need both positive and negative outcomes to rebalance")
            return None

        current_weights = await identity.get_scoring_weights()
        proposed_weights = {key: float(value) for key, value in current_weights.items()}
        adjustments = self._derive_weight_adjustments(positives, negatives)
        if not adjustments:
            return None

        for key, delta in adjustments.items():
            proposed_weights[key] = proposed_weights.get(key, 0.0) + delta

        normalized_weights = self._normalize_weights(proposed_weights)
        result = await identity.apply_scoring_weights(
            normalized_weights,
            changed_by="learning_engine",
            change_reason="weekly outcome analysis",
            confidence_at_change=0.72,
            data_points_analyzed=total,
        )
        await self.log_audit(
            "learning_engine.weights_adjusted",
            {
                "version": result["version"],
                "adjustments": adjustments,
                "weights": result["weights"],
                "data_points_analyzed": total,
            },
        )
        return {
            "version": result["version"],
            "weights": result["weights"],
            "adjustments": adjustments,
        }

    def _derive_weight_adjustments(self, positives, negatives) -> dict[str, float]:
        def _avg(items, attr: str) -> float:
            values = [float(getattr(item, attr)) for item in items if getattr(item, attr) is not None]
            return mean(values) if values else 0.0

        metric_mapping = {
            "money_score": "money",
            "brand_score": "brand",
            "network_score": "network",
            "startup_score": "startup_relevance",
        }
        adjustments: dict[str, float] = {}

        for metric, weight_key in metric_mapping.items():
            diff = _avg(positives, metric) - _avg(negatives, metric)
            if abs(diff) < 0.5:
                continue
            adjustments[weight_key] = round(self._scaled_delta(diff), 4)

        effort_signal = _avg(negatives, "effort_score") - _avg(positives, "effort_score")
        if abs(effort_signal) >= 0.5:
            adjustments["effort_inverse"] = round(self._scaled_delta(effort_signal), 4)

        return adjustments

    def _scaled_delta(self, diff: float) -> float:
        magnitude = min(0.05, max(0.01, abs(diff) * 0.01))
        return magnitude if diff > 0 else -magnitude

    def _normalize_weights(self, weights: dict[str, float]) -> dict[str, float]:
        ordered_keys = [
            "money",
            "brand",
            "startup_relevance",
            "network",
            "effort_inverse",
        ]
        clamped = {
            key: min(0.6, max(0.05, float(weights.get(key, 0.0))))
            for key in ordered_keys
        }
        total = sum(clamped.values()) or 1.0
        normalized = {
            key: round(value / total, 6) for key, value in clamped.items()
        }
        last_key = ordered_keys[-1]
        normalized[last_key] = round(
            1.0 - sum(normalized[key] for key in ordered_keys[:-1]),
            6,
        )
        return normalized


learning_engine = LearningEngine()
