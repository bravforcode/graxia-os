import logging
import uuid

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class Scorer(BaseAgent):
    name = "scorer"

    async def handle_new_opportunity(self, payload: dict) -> None:
        opp_id = payload.get("opportunity_id")
        if not opp_id:
            return
        try:
            await self._score_opportunity(uuid.UUID(opp_id))
        except Exception as e:
            logger.error(f"Scorer failed for {opp_id}: {e}", exc_info=True)

    async def _score_opportunity(self, opp_id: uuid.UUID) -> None:
        from sqlalchemy import select

        from app.core.identity import identity
        from app.core.scoring import score_heuristic
        from app.database import AsyncSessionLocal
        from app.models.knowledge import KnowledgeItem
        from app.models.opportunity import Opportunity

        async with AsyncSessionLocal() as db:
            opp = await db.get(Opportunity, opp_id)
            if not opp or opp.total_score is not None:
                return

            weights = await identity.get_scoring_weights()
            was_fallback = False
            score_data = None

            if not self.llm.is_degraded():
                # Fetch relevant playbooks
                tags = opp.tags or []
                playbook_ctx = ""
                try:
                    q = await db.execute(select(KnowledgeItem).where(KnowledgeItem.category == "playbook", KnowledgeItem.is_active == True).limit(5))
                    playbooks = q.scalars().all()
                    if playbooks:
                        playbook_ctx = "\nRelevant playbooks:\n" + "\n".join(f"- {p.title}" for p in playbooks)
                except Exception:
                    pass

                system = f"""You are the Opportunity Scorer for {identity.get_profile()['personal']['name']}.
Score honestly and conservatively. Overscoring wastes time.

{self.agent_context}

Current scoring weights: money={weights['money']*100:.0f}%, brand={weights['brand']*100:.0f}%, startup={weights.get('startup_relevance', 0.25)*100:.0f}%, network={weights['network']*100:.0f}%, effort_inverse={weights['effort_inverse']*100:.0f}%
{playbook_ctx}

Score each dimension 0-10:
- money_score: 5=meets 30k THB target, 7=exceeds significantly, 10=life-changing (>500k THB)
- brand_score: 5=good portfolio, 7=strong national, 10=top-tier global
- network_score: 5=good peers, 7=quality Thai founders/investors, 10=top-tier international
- startup_score: 5=tangential to founder journey, 7=strong alignment, 10=directly accelerates
- effort_score (INVERTED — higher=more effort): 3=<5h, 5=15-30h, 7=30-80h, 10=>80h

Calibration: Typical=4-5.5, Good=5.5-7, Exceptional=7-8.5 (max 1-2/week)"""

                user = f"""Opportunity:
Title: {opp.title}
Type: {opp.type}
Description: {(opp.description or '')[:500]}
Prize: {opp.prize_amount or 'unknown'}
Deadline: {opp.deadline}
Location: {opp.location_type}
Tags: {opp.tags}
Student eligible: {opp.is_student_eligible}

Return ONLY valid JSON:
{{"money_score":0-10,"brand_score":0-10,"network_score":0-10,"startup_score":0-10,"effort_score":0-10,"total_score":0.00,"action_priority":"do_now|queue|skip","scoring_rationale":"2-3 sentences","red_flags":[],"deadline_urgency":"critical|soon|comfortable|none"}}"""

                try:
                    score_data = await self.llm.complete_json(
                        system=system,
                        user=user,
                        task_class="classification",
                        complexity=2,
                    )
                except Exception as e:
                    logger.warning(f"LLM scoring failed, using heuristic: {e}")

            if not score_data:
                opp_data = {"type": opp.type, "source_platform": opp.source_platform, "location_type": opp.location_type, "tags": opp.tags or [], "prize_amount": opp.prize_amount, "days_until_deadline": None}
                if opp.deadline:
                    from datetime import date
                    opp_data["days_until_deadline"] = (opp.deadline - date.today()).days
                score_data = score_heuristic(opp_data, weights)
                was_fallback = True

            opp.money_score = score_data.get("money_score")
            opp.brand_score = score_data.get("brand_score")
            opp.network_score = score_data.get("network_score")
            opp.startup_score = score_data.get("startup_score")
            opp.effort_score = score_data.get("effort_score")
            opp.total_score = score_data.get("total_score")
            opp.scoring_rationale = score_data.get("scoring_rationale")
            opp.red_flags = score_data.get("red_flags", [])
            opp.action_priority = score_data.get("action_priority")
            opp.status = "scored"
            await db.commit()

        await self.log_audit("opportunity.scored", {"opp_id": str(opp_id), "total_score": float(opp.total_score or 0)}, was_fallback=was_fallback)
        
        # ✅ Use Domain Event instead of dict
        from app.core.domain_events import OpportunityScored
        from app.core.value_objects import Score
        
        event = OpportunityScored(
            opportunity_id=str(opp_id),
            score=Score(float(opp.total_score or 0)),
            reasoning=opp.scoring_rationale or "Scored by agent",
            action_priority=opp.action_priority or "queue"
        )
        await self.bus.emit_domain_event(event)


scorer_agent = Scorer()
