import logging
import uuid
from app.agents.base import BaseAgent
from app.core.control_plane import create_draft_review_request

logger = logging.getLogger(__name__)


class Drafter(BaseAgent):
    name = "drafter"

    async def handle_decided_opportunity(self, payload: dict) -> None:
        opp_id = payload.get("opportunity_id")
        decision = payload.get("decision")
        if decision != "do_now":
            return
        try:
            await self._draft_for_opportunity(uuid.UUID(opp_id))
        except Exception as e:
            logger.error(f"Drafter failed for {opp_id}: {e}", exc_info=True)

    async def _draft_for_opportunity(self, opp_id: uuid.UUID) -> None:
        from app.database import AsyncSessionLocal
        from app.models.content_draft import ContentDraft
        from app.models.opportunity import Opportunity
        from app.core.identity import identity
        from sqlalchemy import select

        if self.llm.is_degraded():
            logger.info("Drafter: LLM degraded — skipping draft generation")
            return

        async with AsyncSessionLocal() as db:
            opp = await db.get(Opportunity, opp_id)
            if not opp:
                return
            existing_draft = (
                await db.execute(
                    select(ContentDraft)
                    .where(ContentDraft.opportunity_id == opp_id)
                    .where(ContentDraft.status.in_(["pending", "approved", "sent"]))
                    .limit(1)
                )
            ).scalar_one_or_none()
            if existing_draft is not None:
                logger.info("Drafter: draft already exists for %s", opp_id)
                return

            draft_type = "application_essay" if opp.type in ("competition", "hackathon", "accelerator", "fellowship") else "proposal"
            audience = "competition_judge" if draft_type == "application_essay" else "freelance_client"
            ctx = identity.get_context_for_audience(audience)
            voice = identity.get_voice_instructions()

            system = f"""You are drafting on behalf of {identity.get_profile()['personal']['name']}.
{ctx}

Voice instructions:
{voice}

Write a compelling {draft_type}. Be specific and concrete. Match the user's exact voice style."""

            user = f"""Draft a {draft_type} for this opportunity:

Title: {opp.title}
Type: {opp.type}
Description: {(opp.description or '')[:800]}
Prize/Value: {opp.prize_amount or 'not specified'}
Deadline: {opp.deadline}
Fit summary: {opp.fit_summary or 'not analyzed'}

Write the complete draft now. Make it real — not a template."""

            content = await self.llm.complete(
                system=system,
                user=user,
                max_tokens=1500,
                temperature=0.7,
                allow_fallback=True,
                task_class="proposal",
                complexity=8,
            )
            if not content:
                return

            draft = ContentDraft(
                type=draft_type,
                title=f"Draft: {opp.title[:80]}",
                content=content,
                context_notes=f"Auto-generated for opportunity: {opp.title}",
                status="pending",
                opportunity_id=opp_id,
                model_used=self.llm.default_model,
                was_fallback_draft=False,
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
            await self.log_audit(
                "draft.created",
                {
                    "draft_id": str(draft.id),
                    "opportunity_id": str(opp_id),
                    "draft_type": draft.type,
                },
            )
            logger.info(f"Drafter: created draft for {opp.title[:50]}")


drafter_agent = Drafter()
