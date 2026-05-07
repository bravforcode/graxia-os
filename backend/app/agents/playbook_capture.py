import logging

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class PlaybookCapture(BaseAgent):
    name = "playbook_capture"

    async def handle_win(self, payload: dict) -> None:
        sub_id = payload.get("submission_id")
        actual_value = payload.get("actual_value_thb", 0)
        try:
            await self._capture_playbook(sub_id, actual_value)
        except Exception as e:
            logger.error(f"PlaybookCapture failed: {e}")

    async def _capture_playbook(self, sub_id, value: float) -> None:
        from app.core.identity import identity
        from app.database import AsyncSessionLocal
        from app.models.knowledge import KnowledgeItem
        from app.models.opportunity import Opportunity
        from app.models.submission import Submission

        if self.llm.is_degraded():
            return

        async with AsyncSessionLocal() as db:
            sub = await db.get(Submission, sub_id) if sub_id else None
            if not sub:
                return
            opp = await db.get(Opportunity, sub.opportunity_id) if sub.opportunity_id else None

        system = f"You are capturing a winning playbook for {identity.get_profile()['personal']['name']}. Be specific and actionable. Extract the pattern that led to success."
        user = f"""A submission just won! Extract a reusable playbook.

Opportunity type: {opp.type if opp else 'unknown'}
Title: {opp.title if opp else 'unknown'}
Score at time: {opp.total_score if opp else 'unknown'}
Actual value: {value} THB
Message sent: {(sub.content or '')[:500]}

Write a concise playbook (3-5 bullet points) capturing what worked and why. Be specific."""

        content = await self.llm.complete(
            system=system,
            user=user,
            max_tokens=600,
            temperature=0.5,
            allow_fallback=True,
            task_class="analysis",
            complexity=5,
        )
        if not content:
            return

        async with AsyncSessionLocal() as db:
            item = KnowledgeItem(
                category="playbook",
                title=f"Win: {opp.title[:80] if opp else 'Unknown'} ({value} THB)",
                content=content,
                tags=[opp.type if opp else "unknown", "playbook", "win"],
                best_for=[opp.type if opp else "unknown"],
                metrics_achieved=f"{value} THB",
                is_active=True,
            )
            db.add(item)
            await db.commit()
            await db.refresh(item)
            logger.info(f"PlaybookCapture: saved playbook for {value} THB win")

        await self.bus.emit(
            "knowledge.captured",
            {
                "knowledge_item_id": str(item.id),
                "category": item.category,
                "title": item.title,
            },
        )

        await self.log_audit(
            "playbook.captured",
            {
                "submission_id": str(sub_id) if sub_id else None,
                "knowledge_item_title": item.title,
                "actual_value_thb": value,
            },
        )

        try:
            from app.telegram_bot.bot import send_message
            await send_message(f"🏆 Win captured! {value:,.0f} THB — playbook saved to knowledge vault.")
        except Exception:
            pass


playbook_capture = PlaybookCapture()
