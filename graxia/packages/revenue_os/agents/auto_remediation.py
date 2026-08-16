"""Incident auto-remediation — retry known-recoverable failures before humans.

Registry: incident source -> handler(db, incident) -> bool (recovered?).
On success the incident is marked resolved (human attention only for what the
system cannot fix itself). Handlers are conservative: they retry the SAME
recoverable operation, never make business decisions.
"""
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db_session
from ..core.db_ops import acquire_automation_lock
from ..enums import ChannelType, IncidentSeverity
from ..models import IncidentEvent

logger = structlog.get_logger()

LOCK_NAME = "auto_remediation"


async def _poll_channel(db: AsyncSession, channel: ChannelType, since=None) -> dict:
    """Indirection so tests can monkeypatch the poll (local import keeps the
    celery->channels graph out of this module's import time)."""
    from ..celery.tasks.marketplace_poll import poll_channel
    return await poll_channel(db, channel, since=since)


async def _retry_channel_poll(db: AsyncSession, incident: IncidentEvent) -> bool:
    """Stale channel sync -> retry the poll once (channel_health incidents)."""
    title = incident.title or ""
    prefix = "Channel sync stale: "
    if not title.startswith(prefix):
        return False
    try:
        channel = ChannelType(title[len(prefix):])
    except ValueError:
        return False
    result = await _poll_channel(db, channel)
    if result.get("skipped") and result.get("reason", "").startswith("error"):
        return False  # still failing — keep the incident open
    return True  # poll ran (even if empty) — sync path works again


async def _retry_supplier_submissions(db: AsyncSession, incident: IncidentEvent) -> bool:
    """Supplier orders stuck SUBMITTED-without-ref -> retry the poll job once."""
    from ..channels.supplier_pod import SupplierPODAdapter
    result = await SupplierPODAdapter().poll(db)
    return bool(result.get("updated", 0) or result.get("submitted", 0))


REMEDIATIONS = {
    "channel_health": _retry_channel_poll,
    "supplier": _retry_supplier_submissions,
}


async def auto_remediation_with_db(db: AsyncSession) -> dict:
    async with acquire_automation_lock(db, LOCK_NAME, ttl_seconds=600) as acquired:
        if not acquired:
            return {"skipped": True, "reason": "lock_held_by_another_worker"}
        incidents = (await db.execute(select(IncidentEvent).where(
            IncidentEvent.status == "open",
            IncidentEvent.severity.in_([IncidentSeverity.MEDIUM, IncidentSeverity.HIGH]),
            IncidentEvent.source.in_(list(REMEDIATIONS)),
        ))).scalars().all()
        recovered = failed = 0
        for incident in incidents:
            handler = REMEDIATIONS.get(incident.source)
            try:
                ok = await handler(db, incident)
            except Exception as exc:
                logger.exception("auto_remediation_handler_failed",
                                 incident_id=str(incident.id), err=str(exc))
                ok = False
            if ok:
                incident.status = "resolved"
                incident.resolved_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                recovered += 1
            else:
                failed += 1
        await db.commit()
        return {"skipped": False, "checked": len(incidents), "recovered": recovered,
                "failed": failed}


def auto_remediation():
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await auto_remediation_with_db(db)

    return asyncio.run(_impl())
