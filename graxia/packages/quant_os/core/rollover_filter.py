"""Rollover filter — blocks trades during the daily FX settlement window.

During the daily rollover (approximately 21:55–22:15 UTC), liquidity
dries up, spreads widen 5–10×, and technical indicators generate false
signals.  This module provides hard blocks and soft warnings around that
window.

Blocked periods:
  - 21:50 – 22:15 UTC  →  BLOCKED  (dead zone)
  - 21:45 – 22:20 UTC  →  WARNING  (extended buffer, warn only)

Reason: During rollover, spreads widen 5-10×, indicators generate false
signals, and slippage can be catastrophic (3+ pips on XAUUSD).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Hard block: 21:50 – 22:15 UTC (25 minutes)
BLOCK_START = time(21, 50)
BLOCK_END = time(22, 15)

# Soft warning: 21:45 – 22:20 UTC (35 minutes, extends 5 min each side)
WARN_START = time(21, 45)
WARN_END = time(22, 20)

_BLOCK_REASON = (
    "ROLLOVER DEAD ZONE: Spreads widen 5-10×, indicators generate false "
    "signals, slippage exceeds 3 pips on XAUUSD. No trades allowed."
)
_WARNING_REASON = (
    "ROLLOVER BUFFER: Approaching/leaving rollover window. "
    "Spreads may be elevated. Trade with caution."
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class RolloverStatus(str, Enum):
    """Rollover filter status."""
    BLOCKED = "BLOCKED"
    WARNING = "WARNING"
    CLEAR = "CLEAR"


@dataclass(frozen=True)
class RolloverCheck:
    """Result of a rollover check."""
    status: RolloverStatus
    timestamp: datetime
    reason: str = ""
    is_blocked: bool = False
    is_warning: bool = False


# ---------------------------------------------------------------------------
# RolloverFilter
# ---------------------------------------------------------------------------

class RolloverFilter:
    """Hard block + soft warning filter for the daily rollover window.

    Usage::

        rf = RolloverFilter()
        if rf.is_blocked(datetime.now(timezone.utc)):
            log.warning("Trade blocked: rollover dead zone")
        status = rf.get_status(some_timestamp)
    """

    def __init__(
        self,
        block_start: time = BLOCK_START,
        block_end: time = BLOCK_END,
        warn_start: time = WARN_START,
        warn_end: time = WARN_END,
    ) -> None:
        """Initialise with configurable window boundaries.

        Args:
            block_start: Start of hard block window (UTC).
            block_end: End of hard block window (UTC).
            warn_start: Start of warning buffer (UTC).
            warn_end: End of warning buffer (UTC).
        """
        self._block_start = block_start
        self._block_end = block_end
        self._warn_start = warn_start
        self._warn_end = warn_end

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_blocked(self, timestamp: datetime) -> bool:
        """Return True if the timestamp falls in the hard-block window.

        Args:
            timestamp: UTC datetime to check.

        Returns:
            True if trading is blocked.
        """
        t = timestamp.time()
        blocked = self._in_window(t, self._block_start, self._block_end)
        if blocked:
            logger.info(
                "ROLLOVER BLOCK: %s (window %s–%s UTC)",
                timestamp.isoformat(),
                self._block_start.strftime("%H:%M"),
                self._block_end.strftime("%H:%M"),
            )
        return blocked

    def is_warning(self, timestamp: datetime) -> bool:
        """Return True if the timestamp is in the extended warning buffer.

        The warning zone extends 5 minutes on each side of the block
        window.  A timestamp in the warning zone is *not* blocked but
        should trigger a caution log.

        Args:
            timestamp: UTC datetime to check.

        Returns:
            True if the timestamp is in the warning zone (but not blocked).
        """
        t = timestamp.time()
        in_warn = self._in_window(t, self._warn_start, self._warn_end)
        in_block = self._in_window(t, self._block_start, self._block_end)
        return in_warn and not in_block

    def get_status(self, timestamp: datetime) -> RolloverStatus:
        """Return the rollover status for a given timestamp.

        Args:
            timestamp: UTC datetime to check.

        Returns:
            ``RolloverStatus.BLOCKED``, ``WARNING``, or ``CLEAR``.
        """
        t = timestamp.time()
        if self._in_window(t, self._block_start, self._block_end):
            return RolloverStatus.BLOCKED
        if self._in_window(t, self._warn_start, self._warn_end):
            return RolloverStatus.WARNING
        return RolloverStatus.CLEAR

    def check(self, timestamp: datetime) -> RolloverCheck:
        """Full rollover check returning a structured result.

        Args:
            timestamp: UTC datetime to check.

        Returns:
            RolloverCheck with status, reason, and convenience booleans.
        """
        status = self.get_status(timestamp)

        if status == RolloverStatus.BLOCKED:
            return RolloverCheck(
                status=status,
                timestamp=timestamp,
                reason=_BLOCK_REASON,
                is_blocked=True,
                is_warning=False,
            )
        if status == RolloverStatus.WARNING:
            return RolloverCheck(
                status=status,
                timestamp=timestamp,
                reason=_WARNING_REASON,
                is_blocked=False,
                is_warning=True,
            )
        return RolloverCheck(
            status=status,
            timestamp=timestamp,
            reason="",
            is_blocked=False,
            is_warning=False,
        )

    def minutes_until_clear(self, timestamp: datetime) -> float:
        """Return minutes until the rollover window fully clears.

        Returns 0.0 if already clear.  Handles wrap-around (e.g. if called
        at 22:00, returns minutes until 22:20).

        Args:
            timestamp: UTC datetime to check.

        Returns:
            Minutes until clear, or 0.0 if already outside all windows.
        """
        status = self.get_status(timestamp)
        if status == RolloverStatus.CLEAR:
            return 0.0

        # Target is the warn_end
        t = timestamp.time()
        warn_end_minutes = self._warn_start.hour * 60 + self._warn_start.minute
        current_minutes = t.hour * 60 + t.minute

        delta = warn_end_minutes - current_minutes
        if delta < 0:
            delta += 24 * 60  # wraps around midnight

        return float(delta)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _in_window(t: time, start: time, end: time) -> bool:
        """Check if *t* falls within [start, end), handling midnight wrap.

        Supports windows that span midnight (e.g. 23:00–01:00).
        """
        if start <= end:
            return start <= t < end
        # Wraps midnight (e.g. 23:50 → 00:15)
        return t >= start or t < end
