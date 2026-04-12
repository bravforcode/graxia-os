import logging
from datetime import date, timedelta
from typing import Any, cast

from sqlalchemy import desc, func, select

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class Briefer(BaseAgent):
    name = "briefer"
    _cognitive_cache: dict[str, Any] = {}

    async def update_cognitive_context(self, payload: dict[str, Any]) -> None:
        self._cognitive_cache = payload

    async def handle_decided_opportunity(self, payload: dict[str, Any]) -> None:
        logger.info(
            "Briefer observed decided opportunity %s",
            payload.get("opportunity_id"),
        )

    async def handle_draft_approved(self, payload: dict[str, Any]) -> None:
        try:
            from app.telegram_bot.bot import send_message

            await send_message("✅ Draft approved and ready to send.")
        except Exception:
            pass

    async def handle_scraper_alert(self, payload: dict[str, Any]) -> None:
        source = payload.get("source_name", "unknown")
        failures = payload.get("consecutive_failures", 0)
        try:
            from app.telegram_bot.bot import send_message

            await send_message(f"⚠️ Scraper `{source}` failed {failures}x — muted for 24h.")
        except Exception:
            pass

    async def handle_cost_alert(self, payload: dict[str, Any]) -> None:
        scope = payload.get("scope", "daily")
        reason = payload.get("reason", "limit reached")
        try:
            from app.telegram_bot.bot import send_message

            await send_message(f"⚠️ AI {scope} limit reached ({reason}). Non-critical tasks paused.")
        except Exception:
            pass

    async def send_morning_brief(self) -> str | None:
        """Send a cognitive-state-aware morning brief to Telegram."""
        try:
            from app.database import AsyncSessionLocal
            from app.models.audit import AuditLog
            from app.models.cognitive_state import CognitiveState
            from app.models.content_draft import ContentDraft
            from app.models.metric import WeeklyMetric
            from app.models.opportunity import Opportunity
            from app.models.submission import Submission
            from app.telegram_bot.bot import send_message

            async with AsyncSessionLocal() as db:
                cognitive_state = (
                    await db.execute(
                        select(CognitiveState).order_by(desc(CognitiveState.date)).limit(1)
                    )
                ).scalar_one_or_none()

                energy = int(getattr(cognitive_state, "energy", 7)) if cognitive_state else 7
                stress = int(getattr(cognitive_state, "stress", 3)) if cognitive_state else 3
                available_hours = (
                    int(getattr(cognitive_state, "available_hours_this_week", 20))
                    if cognitive_state
                    else 20
                )

                opportunities = (
                    await db.execute(
                        select(Opportunity)
                        .where(Opportunity.decision.in_(["do_now", "ask_user", "delay"]))
                        .where(Opportunity.status.in_(["decided", "approved", "scored", "in_progress"]))
                        .order_by(
                            desc(Opportunity.decision_confidence),
                            desc(Opportunity.total_score),
                            Opportunity.deadline,
                        )
                        .limit(12)
                    )
                ).scalars().all()

                pending_drafts = await db.scalar(
                    select(func.count()).where(ContentDraft.status == "pending")
                )
                pending_followups = await db.scalar(
                    select(func.count()).where(
                        Submission.follow_up_date <= date.today(),
                        Submission.status.in_(["sent", "opened"]),
                    )
                )
                proposals_waiting = await db.scalar(
                    select(func.count()).where(
                        Submission.status.in_(["sent", "opened", "replied", "meeting_scheduled"])
                    )
                )

                week_start = date.today() - timedelta(days=date.today().weekday())
                current_week = (
                    await db.execute(
                        select(WeeklyMetric).where(WeeklyMetric.week_start == week_start).limit(1)
                    )
                ).scalar_one_or_none()

                latest_strategy = (
                    await db.execute(
                        select(AuditLog)
                        .where(AuditLog.action == "strategy.generated")
                        .order_by(desc(AuditLog.created_at))
                        .limit(1)
                    )
                ).scalar_one_or_none()

            max_actionable = 3
            prefix = None

            if energy <= 3:
                max_actionable = 1
                prefix = "⚡ Low energy day — 1 priority only"
            elif stress >= 8:
                prefix = "🧘 High stress detected — essential items only"

            filtered = opportunities
            if stress >= 8:
                filtered = [
                    item for item in filtered if float(item.total_score or 0) >= 6.0
                ]
            if available_hours < 5:
                filtered = [
                    item
                    for item in filtered
                    if item.decision == "do_now"
                    and float(item.decision_confidence or 0) >= 0.8
                ]

            actionable = filtered[:max_actionable]
            new_opportunities = opportunities[: min(len(opportunities), 5)]

            lines = [f"🌅 *สรุปเช้า — {date.today().strftime('%a %d %b')}*"]
            if prefix:
                lines.append(prefix)

            lines.append("")
            lines.append(f"📌 *ต้องทำวันนี้ ({len(actionable)} อย่าง)*")
            if actionable:
                for index, opp in enumerate(actionable, start=1):
                    confidence = int(float(opp.decision_confidence or 0) * 100)
                    reason = opp.decision_reasoning or opp.scoring_rationale or "No reasoning recorded"
                    lines.append(
                        f"{index}. {opp.title[:60]} — {reason[:70]} · Confidence: {confidence}%"
                    )
            else:
                lines.append("1. ไม่มี item ที่ควรผลักวันนี้เหนือ threshold ปัจจุบัน")

            lines.append("")
            lines.append("🏆 *โอกาสใหม่น่าสนใจ*")
            if new_opportunities:
                for opp in new_opportunities:
                    score = float(opp.total_score or 0)
                    deadline = opp.deadline.isoformat() if opp.deadline else "none"
                    fit = opp.fit_summary or opp.scoring_rationale or "No fit summary yet"
                    lines.append(
                        f"• {opp.title[:56]} [{opp.type}] — {score:.2f}/10 · Deadline: {deadline}"
                    )
                    lines.append(f"  ↳ {fit[:90]} · Decision: {opp.decision or opp.action_priority or 'pending'}")
            else:
                lines.append("• ยังไม่มีโอกาสใหม่ที่ผ่าน filter เข้มข้นของระบบ")

            lines.append("")
            lines.append("💰 *Pipeline*")
            lines.append(f"• Proposals รอตอบ: {proposals_waiting or 0}")
            lines.append(
                f"• Revenue สัปดาห์นี้: {float(current_week.revenue_thb or 0):,.0f} THB"
                if current_week
                else "• Revenue สัปดาห์นี้: 0 THB"
            )

            lines.append("")
            lines.append("📊 *Strategy Bet สัปดาห์นี้*")
            latest_strategy_details = (
                cast(dict[str, Any] | None, getattr(latest_strategy, "details", None))
                if latest_strategy is not None
                else None
            )
            if latest_strategy_details and latest_strategy_details.get("strategy"):
                lines.append(str(latest_strategy_details["strategy"])[:220])
            else:
                lines.append("ยังไม่มี — /strategy เพื่อดู")

            lines.append("")
            lines.append(
                f"⚠️ *รออนุมัติ:* {pending_drafts or 0} drafts · *Follow-up วันนี้:* {pending_followups or 0}"
            )

            message = "\n".join(lines)
            await send_message(message)
            await self.log_audit(
                "brief.generated",
                {
                    "message_preview": message[:240],
                    "pending_drafts": int(pending_drafts or 0),
                    "pending_followups": int(pending_followups or 0),
                },
            )
            return message
        except Exception as exc:
            logger.error(f"Morning brief failed: {exc}", exc_info=True)
            return None


briefer_agent = Briefer()
