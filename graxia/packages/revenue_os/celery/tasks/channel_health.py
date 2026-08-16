"""Channel health monitoring — stale last_sync_at -> IncidentEvent (once).

A connected, enabled channel whose last_sync_at is older than the stale
threshold (12h default, per-channel override via config['health_stale_hours'])
raises an open IncidentEvent LOW once. FX row is a config store, not a sync
target, so it is skipped.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_db_session
from ...core.db_ops import acquire_automation_lock
from ...enums import ChannelType, IncidentSeverity
from ...models import ChannelConnection, IncidentEvent

logger = structlog.get_logger()

LOCK_NAME = "channel_health"
DEFAULT_STALE_HOURS = 12.0


async def channel_health_with_db(db: AsyncSession) -> dict:
    async with acquire_automation_lock(db, LOCK_NAME, ttl_seconds=600) as acquired:
        if not acquired:
            return {"skipped": True, "reason": "lock_held_by_another_worker"}
        rows = (await db.execute(select(ChannelConnection))).scalars().all()
        healthy = stale = 0
        for conn in rows:
            if conn.channel == ChannelType.FX or not conn.enabled:
                continue  # fx row is a config store; disabled channels are silent
            last = conn.last_sync_at
            if last is None:
                continue  # never synced — not a health failure yet
            threshold = float((conn.config or {}).get("health_stale_hours", DEFAULT_STALE_HOURS))
            if datetime.now(timezone.utc) - last > timedelta(hours=threshold):
                stale += 1
                title = f"Channel sync stale: {conn.channel.value}"
                open_incident = await db.scalar(select(IncidentEvent.id).where(
                    IncidentEvent.title == title,
                    IncidentEvent.status == "open",
                ))
                if open_incident is None:  # once per channel until resolved
                    db.add(IncidentEvent(
                        title=title,
                        description=f"last_sync_at {last.isoformat()} older than {threshold}h",
                        severity=IncidentSeverity.LOW, source="channel_health",
                    ))
            else:
                healthy += 1
        await db.commit()
        return {"skipped": False, "healthy": healthy, "stale": stale}


def channel_health():
    import asyncio

    async def _impl():
        async with get_db_session() as db:
            return await channel_health_with_db(db)

    return asyncio.run(_impl())
