import logging
from datetime import date, timedelta
from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class Briefer(BaseAgent):
    name = "briefer"
    _cognitive_cache: dict = {}

    async def update_cognitive_context(self, payload: dict) -> None:
        self._cognitive_cache = payload

    async def handle_decided_opportunity(self, payload: dict) -> None:
        # Collect decided opportunities for morning brief
        pass

    async def handle_draft_approved(self, payload: dict) -> None:
        try:
            from app.telegram_bot.bot import send_message
            await send_message(f"✅ Draft approved and ready to send.")
        except Exception:
            pass

    async def handle_scraper_alert(self, payload: dict) -> None:
        source = payload.get("source_name", "unknown")
        failures = payload.get("consecutive_failures", 0)
        try:
            from app.telegram_bot.bot import send_message
            await send_message(f"⚠️ Scraper `{source}` failed {failures}x — muted for 24h.")
        except Exception:
            pass

    async def handle_cost_alert(self, payload: dict) -> None:
        scope = payload.get("scope", "daily")
        reason = payload.get("reason", "limit reached")
        try:
            from app.telegram_bot.bot import send_message
            await send_message(f"⚠️ AI {scope} limit reached ({reason}). Non-critical tasks paused.")
        except Exception:
            pass

    async def send_morning_brief(self) -> None:
        """Send daily morning brief to Telegram."""
        try:
            from app.database import AsyncSessionLocal
            from app.models.opportunity import Opportunity
            from app.models.content_draft import ContentDraft
            from app.models.submission import Submission
            from app.models.cognitive_state import CognitiveState
            from sqlalchemy import select, func, desc

            async with AsyncSessionLocal() as db:
                # Today's do_now opportunities
                do_now = await db.execute(
                    select(Opportunity).where(
                        Opportunity.decision == "do_now",
                        Opportunity.status.in_(["decided", "scored"])
                    ).order_by(Opportunity.total_score.desc()).limit(5)
                )
                opps = do_now.scalars().all()

                # Pending drafts
                pending_drafts = await db.scalar(select(func.count()).where(ContentDraft.status == "pending"))

                # Pending follow-ups
                pending_followups = await db.scalar(select(func.count()).where(Submission.follow_up_date <= date.today(), Submission.status.in_(["sent", "opened"])))

                # Today's cognitive state
                cog = await db.execute(select(CognitiveState).order_by(desc(CognitiveState.date)).limit(1))
                state = cog.scalar_one_or_none()
                energy = state.energy if state else 7

            lines = [f"☀️ *Good morning, P!*\n"]
            lines.append(f"Energy today: {energy}/10\n")

            if opps:
                lines.append(f"🎯 *Top opportunities to act on ({len(opps)}):*")
                for opp in opps:
                    deadline_str = f" · {opp.deadline}" if opp.deadline else ""
                    lines.append(f"• {opp.title[:60]} · Score: {opp.total_score}{deadline_str}")
            else:
                lines.append("No high-priority opportunities right now.")

            if pending_drafts:
                lines.append(f"\n📝 {pending_drafts} draft(s) awaiting your review")
            if pending_followups:
                lines.append(f"📬 {pending_followups} follow-up(s) due today")

            from app.telegram_bot.bot import send_message
            await send_message("\n".join(lines))
        except Exception as e:
            logger.error(f"Morning brief failed: {e}", exc_info=True)


briefer_agent = Briefer()
