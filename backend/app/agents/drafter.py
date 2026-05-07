import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

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
        from sqlalchemy import select

        from app.config import settings
        from app.core.identity import identity
        from app.database import AsyncSessionLocal
        from app.models.content_draft import ContentDraft
        from app.models.opportunity import Opportunity

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
                template_name = "competition_essay.md" if draft_type == "application_essay" else "proposal_base.md"
                content = self._render_template(settings, identity, template_name, opp)
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

    def _render_template(self, settings, identity, template_name: str, opp) -> str | None:
        try:
            template_path = Path(settings.IDENTITY_PATH).resolve().parent / "templates" / template_name
            text = template_path.read_text(encoding="utf-8")
        except Exception:
            return None

        name = identity.get_profile().get("personal", {}).get("name") or "Developer"
        now = datetime.now(UTC).astimezone().strftime("%Y-%m-%d")
        description = (opp.description or "").strip().splitlines()
        first_line = (description[0] if description else "Automated system implementation.").strip()
        replacements = {
            "[PROJECT NAME]": opp.title or "Project",
            "[CLIENT NAME / COMPANY]": getattr(opp, "source", None) or "Client",
            "[DATE]": now,
            "P (Phirawit Jitnarong)": name,
            "[1-2 sentences: their specific operational problem in their terms]": first_line[:160],
            "[3-5 bullet points: concrete deliverables, not vague services]": "- Scope discovery and technical plan\n- Implementation with deployment\n- Testing and handover",
            "[Feature 1]:": "[Feature 1]:",
            "[Feature 2]:": "[Feature 2]:",
            "[Feature 3]:": "[Feature 3]:",
            "[What it does in plain terms]": "Deliver a working MVP aligned to requirements",
            "[Core feature]": "Core MVP",
            "[Secondary feature]": "Enhancements",
            "[X weeks]": "1-2",
            "[N]": "2",
            "[Amount]": "TBD",
            "[TOTAL]": "TBD",
            "[AMOUNT]": "TBD",
            "[2-3 sentences: what specific problem exists and why current solutions fail]": first_line[:200],
            "[3-4 sentences: what we built, how it works, what makes it different]": "We will deliver a practical implementation with clear milestones and measurable impact.",
            "[Be specific: users, revenue, deployments, feedback received]": "Initial delivery with measurable outcomes and iterative improvements.",
            "[Project 1]": "Testlyn",
            "[Project 2]": "Plexta",
            "[SECTOR]": "SME",
            "[SIZE/GROWTH]": "growing",
            "[REASON]": "fragmented tooling",
            "[HOW/WHY].": "Through targeted integrations and repeatable playbooks.",
            "[What we're asking for: prize money, mentorship, acceleration]": "Mentorship and support to accelerate deployment.",
            "[What we'll do with it in 90 days: specific milestones]": "Ship MVP, onboard early users, and validate retention.",
        }
        for k, v in replacements.items():
            text = text.replace(k, str(v))
        return text.strip()


drafter_agent = Drafter()
