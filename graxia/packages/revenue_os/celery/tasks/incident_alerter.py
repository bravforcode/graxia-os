"""Send MEDIUM+ incidents to Telegram once (Risk Audit #10 — make humans notice)."""
from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db_session
from ...enums import IncidentSeverity
from ...models import IncidentEvent
from graxia.services.telegram_notifier import TelegramNotifier

logger = structlog.get_logger()

notifier = TelegramNotifier  # monkeypatch target for tests


async def alerter_sweep(db: AsyncSession) -> dict:
    result = await db.execute(
        select(IncidentEvent).where(
            IncidentEvent.severity.in_([IncidentSeverity.MEDIUM, IncidentSeverity.HIGH]),
            IncidentEvent.notified_at.is_(None),
        ).order_by(IncidentEvent.created_at)
    )
    incidents = list(result.scalars().all())
    sent = 0
    for incident in incidents:
        try:
            notifier.notify_system_alert(
                severity=incident.severity.value,
                msg=f"{incident.title}\n{incident.description}",
            )
            incident.notified_at = datetime.now(timezone.utc)
            sent += 1
        except Exception:
            logger.exception("incident_alert_failed", incident_id=str(incident.id))
    await db.commit()
    return {"sent": sent, "pending": len(incidents) - sent}


def incident_alerter():
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await alerter_sweep(db)

    return asyncio.run(_impl())
