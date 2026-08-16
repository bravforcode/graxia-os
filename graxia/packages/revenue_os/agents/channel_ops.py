"""Per-channel commerce agent — one automation cycle for a single marketplace
channel, gated by autonomy mode and locked per channel.

Division of labor: ChannelOpsAgent owns the channel operational cycle
(poll -> import -> reconcile). Inventory/price/listing pushes stay in the
global inventory-sync beat job so writers never race on PriceChangeLock.
"""
from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ..celery.tasks.marketplace_poll import poll_channel
from ..core.db_ops import acquire_automation_lock
from ..core.policy_engine import PolicyEngine
from ..enums import AutonomyMode, ChannelType

logger = structlog.get_logger()


class ChannelOpsAgent:
    """Operates ONE marketplace channel per cycle (poll-first, mode-gated)."""

    @staticmethod
    async def run_cycle(db: AsyncSession, channel: ChannelType,
                        adapter_factory=None) -> dict:
        mode = await PolicyEngine.get_autonomy_mode(db)
        if mode in (AutonomyMode.OFF, AutonomyMode.SHADOW):
            # SHADOW never calls external APIs (global constraint)
            return {"skipped": True, "channel": channel.value,
                    "reason": f"mode={mode.value}"}
        async with acquire_automation_lock(db, f"channel_ops_{channel.value}",
                                           ttl_seconds=600) as acquired:
            if not acquired:
                return {"skipped": True, "channel": channel.value,
                        "reason": "lock_held_by_another_worker"}
            result = await poll_channel(db, channel)
            await db.commit()
            return {"skipped": False, "channel": channel.value, **result}
