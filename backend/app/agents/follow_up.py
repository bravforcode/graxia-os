import logging
from datetime import date

from app.agents.base import BaseAgent
from app.core.control_plane import create_draft_review_request

logger = logging.getLogger(__name__)


class FollowUpAgent(BaseAgent):
    name = "follow_up"

    async def run(self) -> int:
        """Check for due follow-ups and generate reminder messages."""
        from sqlalchemy import select

        from app.database import AsyncSessionLocal
        from app.models.submission import Submission

        async with AsyncSessionLocal() as db:
            due = await db.execute(
                select(Submission).where(
                    Submission.follow_up_date <= date.today(),
                    Submission.status.in_(["sent", "opened"]),
                )
            )
            submissions = due.scalars().all()

        count = 0
        for sub in submissions:
            try:
                await self._handle_followup(sub)
                count += 1
            except Exception as e:
                logger.error(f"Follow-up failed for {sub.id}: {e}")

        return count

    async def _handle_followup(self, sub) -> None:
        from app.core.identity import identity
        from app.database import AsyncSessionLocal
        from app.models.content_draft import ContentDraft

        if self.llm.is_degraded():
            return

        system = f"You are writing a follow-up message for {identity.get_profile()['personal']['name']}.\n{identity.get_voice_instructions()}\nKeep it short — 3-4 sentences max. One clear ask."
        user = f"""Write a follow-up message for:
Title: {sub.title}
Original sent: {sub.sent_at}
Status: {sub.status}
Notes: {sub.outcome_notes or 'none'}

Write the follow-up now."""

        content = await self.llm.complete(
            system=system,
            user=user,
            max_tokens=300,
            temperature=0.7,
            allow_fallback=True,
            task_class="short_draft",
            complexity=4,
        )
        if not content:
            return

        async with AsyncSessionLocal() as db:
            draft = ContentDraft(
                type="follow_up",
                title=f"Follow-up: {sub.title[:60] if sub.title else 'Submission'}",
                content=content,
                status="pending",
                submission_id=sub.id,
                contact_id=sub.contact_id,
                opportunity_id=sub.opportunity_id,
                model_used=self.llm.default_model,
            )
            db.add(draft)
            await db.commit()
            await db.refresh(draft)
            await create_draft_review_request(
                draft_id=draft.id,
                draft_type=draft.type,
                draft_title=draft.title,
                preview_text=draft.content,
                requested_by=self.name,
            )


follow_up_agent = FollowUpAgent()
