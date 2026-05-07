import logging
import uuid
from datetime import UTC, date, timedelta
from decimal import Decimal

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class DecisionEngine(BaseAgent):
    name = "decision_engine"
    _cognitive_cache: dict = {}

    async def update_cognitive_context(self, payload: dict) -> None:
        self._cognitive_cache = payload

    async def handle_scored_opportunity(self, payload: dict) -> None:
        event_payload = payload.get("data", payload)
        opp_id = event_payload.get("opportunity_id")
        if not opp_id:
            return
        try:
            await self._decide(uuid.UUID(opp_id))
        except Exception as e:
            logger.error(f"DecisionEngine failed for {opp_id}: {e}", exc_info=True)

    async def _get_cognitive_state(self) -> dict:
        try:
            from sqlalchemy import desc, select

            from app.database import AsyncSessionLocal
            from app.models.cognitive_state import CognitiveState
            async with AsyncSessionLocal() as db:
                q = await db.execute(select(CognitiveState).order_by(desc(CognitiveState.date)).limit(1))
                state = q.scalar_one_or_none()
                if state:
                    return {"energy": state.energy, "stress": state.stress, "available_hours": state.available_hours_this_week, "exam_pressure": state.exam_pressure}
        except Exception:
            pass
        from app.core.identity import identity
        defaults = identity.get_cognitive_defaults()
        return {"energy": defaults["default_energy"], "stress": defaults["default_stress"], "available_hours": defaults["default_available_hours"], "exam_pressure": 0}

    async def _get_workload(self) -> dict:
        try:
            from datetime import datetime

            from sqlalchemy import func, select

            from app.database import AsyncSessionLocal
            from app.models.content_draft import ContentDraft
            from app.models.opportunity import Opportunity
            async with AsyncSessionLocal() as db:
                do_now_count = await db.scalar(select(func.count()).where(Opportunity.decision == "do_now", Opportunity.status.in_(["decided", "approved", "in_progress"])))
                pending_count = await db.scalar(select(func.count()).where(ContentDraft.status == "pending"))
                week_start = date.today() - timedelta(days=date.today().weekday())
                actioned_count = await db.scalar(select(func.count()).where(Opportunity.acted_on_at >= datetime(week_start.year, week_start.month, week_start.day, tzinfo=UTC)))
                return {"active_do_now": do_now_count or 0, "pending_approvals": pending_count or 0, "actioned_this_week": actioned_count or 0}
        except Exception:
            return {"active_do_now": 0, "pending_approvals": 0, "actioned_this_week": 0}

    async def _decide(self, opp_id: uuid.UUID) -> None:
        from app.config import settings
        from app.database import AsyncSessionLocal
        from app.models.opportunity import Opportunity

        async with AsyncSessionLocal() as db:
            opp = await db.get(Opportunity, opp_id)
            if not opp or opp.decision:
                return

            cog = await self._get_cognitive_state()
            workload = await self._get_workload()
            energy = cog["energy"]
            stress = cog["stress"]
            avail = cog["available_hours"]
            total = float(opp.total_score or 0)
            priority = opp.action_priority
            days_left = (opp.deadline - date.today()).days if opp.deadline else None
            max_pending = settings.MAX_PENDING_APPROVALS

            decision = None
            confidence = 0.7
            reasoning = ""
            review_after = (date.today() + timedelta(days=7)).isoformat()

            # Rule 0: queue full
            if workload["pending_approvals"] >= max_pending:
                decision, confidence = "delay", 0.99
                reasoning = "Approval queue full. Resolve pending items first."

            # Rule 1: low energy
            elif energy <= 3:
                if total < 7.5:
                    decision, confidence = "delay", 0.9
                    reasoning = f"Energy too low ({energy}/10) for this opportunity. Revisit when recovered."
                else:
                    decision = "ask_user"
                    reasoning = f"High-value opportunity but energy is low ({energy}/10). Your call."

            # Rule 2: stress + overload
            elif stress >= 8 and avail < 5:
                if total < 8.0:
                    decision, confidence = "delay", 0.85
                    reasoning = f"High stress ({stress}/10) + very low hours ({avail}h). Protecting your capacity."

            # Rule 3: obvious skip
            elif priority == "skip":
                decision, confidence = "skip", 0.95
                reasoning = "Scored below threshold — not worth the time."

            # Rule 4: obvious do_now
            elif total >= 8.0 and days_left is not None and days_left < 3:
                decision, confidence = "do_now", 0.90
                reasoning = f"Exceptional score ({total}) + critical deadline ({days_left} days). Act now."

            if decision:
                opp.decision = decision
                opp.decision_confidence = Decimal(str(confidence))
                opp.decision_reasoning = reasoning
                opp.decision_factors = {"rule_based": True, "energy": energy, "stress": stress}
                opp.review_after = date.fromisoformat(review_after) if decision == "delay" else None
                opp.status = "decided"
                await db.commit()
            else:
                # LLM decision
                try:
                    result = await self._llm_decide(opp, cog, workload)
                    if result:
                        opp.decision = result.get("decision", "delay")
                        opp.decision_confidence = Decimal(
                            str(result.get("confidence", 0.6))
                        )
                        opp.decision_reasoning = result.get("reasoning", "")
                        opp.decision_factors = result.get("decision_factors", {})
                        ra = result.get("review_after")
                        opp.review_after = date.fromisoformat(ra) if ra else None
                        opp.status = "decided"
                        await db.commit()
                except Exception as e:
                    logger.error(f"LLM decision failed: {e}")
                    opp.decision = "delay"
                    opp.decision_confidence = Decimal("0.5")
                    opp.decision_reasoning = "LLM unavailable — defaulting to delay."
                    opp.status = "decided"
                    await db.commit()

        if opp.decision == "ask_user":
            await self._ask_user(opp)

        await self.log_audit(
            "opportunity.decided",
            {
                "opp_id": str(opp_id),
                "decision": opp.decision,
                "confidence": float(opp.decision_confidence or 0),
            },
        )
        await self.bus.emit("opportunity.decided", {"opportunity_id": str(opp_id), "decision": opp.decision, "confidence": float(opp.decision_confidence or 0)})

    async def _llm_decide(self, opp, cog: dict, workload: dict) -> dict:
        from app.core.identity import identity
        days_left = (opp.deadline - date.today()).days if opp.deadline else "unknown"
        system = f"You are the Executive Decision Engine for {identity.get_profile()['personal']['name']}.\nMake context-aware decisions about whether to pursue opportunities.\n{self.agent_context}"
        user = f"""Cognitive state: Energy={cog['energy']}/10, Stress={cog['stress']}/10, Hours={cog['available_hours']}, Exam={cog['exam_pressure']}/10
Workload: do_now={workload['active_do_now']}, pending_approvals={workload['pending_approvals']}, actioned_this_week={workload['actioned_this_week']}

Opportunity:
  Title: {opp.title}
  Type: {opp.type}
  Score: {opp.total_score}/10
  Deadline: {opp.deadline} ({days_left} days)
  Effort score: {opp.effort_score}/10 (higher=more effort)
  Red flags: {opp.red_flags}

Return ONLY valid JSON: {{"decision":"do_now|delay|skip|ask_user","confidence":0.0-1.0,"reasoning":"2-4 sentences","decision_factors":{{"deadline_pressure":"critical|moderate|comfortable|none","strategic_fit":"high|medium|low","workload_fit":"fits|tight|overloaded","cash_need":"urgent|moderate|comfortable","conviction_signal":"strong|medium|absent"}},"review_after":"YYYY-MM-DD or null","alternative_action":"optional string"}}"""
        return await self.llm.complete_json(
            system=system,
            user=user,
            task_class="analysis",
            complexity=6,
        )

    async def _ask_user(self, opp) -> None:
        try:
            from app.telegram_bot.bot import send_message
            msg = f"🤔 *ต้องการการตัดสินใจ*\n\n*{opp.title}*\nScore: {opp.total_score}/10\nDeadline: {opp.deadline}\n\n_{opp.decision_reasoning}_"
            await send_message(msg)
        except Exception as e:
            logger.warning(f"ask_user telegram failed: {e}")


decision_engine = DecisionEngine()
