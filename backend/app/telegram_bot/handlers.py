import logging
from app.config import settings

logger = logging.getLogger(__name__)


async def handle_callback(update, context) -> None:
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    parts = data.split(":")
    if len(parts) < 3:
        return

    entity, action, entity_id = parts[0], parts[1], parts[2]

    try:
        from app.database import AsyncSessionLocal
        if entity == "opp":
            from app.models.opportunity import Opportunity
            import uuid
            async with AsyncSessionLocal() as db:
                opp = await db.get(Opportunity, uuid.UUID(entity_id))
                if not opp:
                    await query.edit_message_text("Opportunity not found.")
                    return
                if action == "approve":
                    opp.status = "approved"
                elif action == "skip":
                    opp.status = "ignored"
                    opp.decision = "skip"
                elif action == "delay":
                    opp.decision = "delay"
                await db.commit()
            await query.edit_message_text(f"✅ Opportunity {action}d.")

        elif entity == "draft":
            from app.models.content_draft import ContentDraft
            from datetime import datetime, timezone
            import uuid
            async with AsyncSessionLocal() as db:
                draft = await db.get(ContentDraft, uuid.UUID(entity_id))
                if not draft:
                    await query.edit_message_text("Draft not found.")
                    return
                if action == "approve":
                    draft.status = "approved"
                    draft.approved_at = datetime.now(timezone.utc)
                elif action == "reject":
                    draft.status = "rejected"
                await db.commit()
            await query.edit_message_text(f"✅ Draft {action}d.")
    except Exception as e:
        logger.error(f"Callback handler error: {e}")
        await query.edit_message_text(f"Error: {e}")


async def handle_checkin_command(update, context) -> None:
    """Handle /checkin command: /checkin energy=7 stress=3 hours=20"""
    try:
        args = context.args or []
        params = {}
        for arg in args:
            if "=" in arg:
                k, v = arg.split("=", 1)
                params[k.strip()] = int(v.strip())

        energy = params.get("energy", 7)
        stress = params.get("stress", 3)
        hours = params.get("hours", 20)

        from app.database import AsyncSessionLocal
        from app.models.cognitive_state import CognitiveState
        from sqlalchemy import select
        from datetime import date

        async with AsyncSessionLocal() as db:
            today = date.today()
            q = await db.execute(select(CognitiveState).where(CognitiveState.date == today))
            state = q.scalar_one_or_none()
            if state:
                state.energy = energy
                state.stress = stress
                state.available_hours_this_week = hours
            else:
                state = CognitiveState(date=today, energy=energy, stress=stress, available_hours_this_week=hours)
                db.add(state)
            await db.commit()

        from app.core.event_bus import event_bus
        await event_bus.emit("cognitive_state.updated", {"energy": energy, "stress": stress, "available_hours": hours})

        await update.message.reply_text(f"✅ Check-in saved: Energy={energy}/10, Stress={stress}/10, Hours={hours}h")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
