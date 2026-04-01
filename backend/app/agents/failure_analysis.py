import logging
from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class FailureAnalysis(BaseAgent):
    name = "failure_analysis"

    async def handle_loss(self, payload: dict) -> None:
        sub_id = payload.get("submission_id")
        lost_reason = payload.get("lost_reason", "unknown")
        try:
            await self._analyze_loss(sub_id, lost_reason)
        except Exception as e:
            logger.error(f"FailureAnalysis failed: {e}")

    async def handle_win(self, payload: dict) -> None:
        pass  # wins handled by playbook_capture

    async def _analyze_loss(self, sub_id, lost_reason: str) -> None:
        from app.database import AsyncSessionLocal
        from app.models.submission import Submission
        from app.models.knowledge import KnowledgeItem
        from app.core.identity import identity

        if self.llm.is_degraded():
            return

        async with AsyncSessionLocal() as db:
            sub = await db.get(Submission, sub_id) if sub_id else None
            if not sub:
                return

        system = f"You are doing post-mortem analysis for {identity.get_profile()['personal']['name']}. Be honest and constructive. Identify what could be improved."
        user = f"""Analyze this loss and extract lessons:

Lost reason: {lost_reason}
Lost stage: {sub.lost_stage or 'unknown'}
Submission type: {sub.type}
Content sent: {(sub.content or '')[:500]}

Write 2-3 specific lessons learned and how to avoid this next time."""

        content = await self.llm.complete(system=system, user=user, max_tokens=400, temperature=0.5, allow_fallback=True)
        if not content:
            return

        async with AsyncSessionLocal() as db:
            item = KnowledgeItem(
                category="failure_analysis",
                title=f"Loss: {lost_reason} at {sub.lost_stage or 'unknown'} stage",
                content=content,
                tags=["loss", lost_reason, sub.type or "unknown"],
                is_active=True,
            )
            db.add(item)
            await db.commit()


failure_analysis = FailureAnalysis()
