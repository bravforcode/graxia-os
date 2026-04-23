from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.audit import AuditLog
from app.models.network_interaction import NetworkInteraction

router = APIRouter(prefix="/api/v1/outreach", tags=["outreach"])


@router.get("/stats")
async def outreach_stats(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    sent_today = await db.scalar(
        select(func.count(NetworkInteraction.id)).where(
            NetworkInteraction.interaction_type.in_(
                ["email_outreach_initial", "email_outreach_followup_1", "email_outreach_followup_2"]
            ),
            func.date(NetworkInteraction.interaction_at) == today,
        )
    )

    def _count(action: str) -> Any:
        return select(func.count(AuditLog.id)).where(
            AuditLog.action == action,
            func.date(AuditLog.created_at) == today,
        )

    opens = await db.scalar(_count("outreach.open"))
    clicks = await db.scalar(_count("outreach.click"))
    replies = await db.scalar(_count("outreach.reply"))
    return {
        "date": today.isoformat(),
        "sent": int(sent_today or 0),
        "opens": int(opens or 0),
        "clicks": int(clicks or 0),
        "replies": int(replies or 0),
    }

