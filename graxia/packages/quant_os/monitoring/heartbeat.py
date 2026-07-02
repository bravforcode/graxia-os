"""
Heartbeat monitor for Quant OS production trading system.

Provides a ``HeartbeatMonitor`` that periodically writes a timestamp into a
shared state dict.  The :mod:`dead_mans_switch` module reads that timestamp
to detect stalls.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, UTC
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Default beat interval in seconds
_BEAT_INTERVAL: float = 5.0


class HeartbeatMonitor:
    """Emits periodic heartbeats into a shared state dictionary.

    The monitor writes ``last_heartbeat`` (UTC ISO-8601 string) into
    *state* every *interval* seconds.  The companion
    :class:`~quant_os.monitoring.dead_mans_switch.DeadMansSwitch` reads
    that key to detect stalls.

    Args:
        state: Mutable dict shared with the dead-man's switch.
        interval: Seconds between beats.  Defaults to ``5.0``.
        key: State key to write.  Defaults to ``"last_heartbeat"``.
    """

    def __init__(
        self,
        state: Dict[str, Any],
        *,
        interval: float = _BEAT_INTERVAL,
        key: str = "last_heartbeat",
    ) -> None:
        self._state = state
        self._interval = interval
        self._key = key
        self._task: Optional[asyncio.Task[None]] = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background beat loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._beat_loop())
        logger.info(
            "HeartbeatMonitor started (interval=%.1fs, key=%s)",
            self._interval,
            self._key,
        )

    async def stop(self) -> None:
        """Stop the beat loop gracefully."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("HeartbeatMonitor stopped")

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def beat(self) -> None:
        """Write the current UTC timestamp into the shared state.

        Safe to call manually from any coroutine when you want to signal
        liveness outside the regular interval (e.g. after a long I/O op).
        """
        now = datetime.now(UTC).isoformat()
        self._state[self._key] = now
        logger.debug("Heartbeat: %s", now)

    @property
    def last_beat(self) -> Optional[str]:
        """Return the last heartbeat ISO string, or ``None`` if never beaten."""
        return self._state.get(self._key)

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    async def _beat_loop(self) -> None:
        """Background coroutine that calls :meth:`beat` on the configured interval."""
        while self._running:
            self.beat()
            try:
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                break
