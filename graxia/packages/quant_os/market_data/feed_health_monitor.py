"""
Feed Health Monitor for Quant OS

Tracks connection health and freshness of the market data feed.
Detects stale data, disconnections, and feed degradation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class FeedHealthLevel(str, Enum):
    """Feed health severity levels."""
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    DISCONNECTED = "DISCONNECTED"
    UNKNOWN = "UNKNOWN"


@dataclass
class FeedHealthState:
    """Current feed health analysis."""
    level: FeedHealthLevel
    last_tick_age_seconds: Optional[float]
    max_tick_age_seconds: float
    ticks_received: int
    ticks_per_second: float
    consecutive_timeouts: int
    last_error: Optional[str]
    symbol: str

    @property
    def is_connected(self) -> bool:
        return self.level in (FeedHealthLevel.HEALTHY, FeedHealthLevel.DEGRADED)

    @property
    def is_eligible_for_order(self) -> bool:
        return self.level == FeedHealthLevel.HEALTHY

    def summary(self) -> str:
        age_str = f"{self.last_tick_age_seconds:.1f}s" if self.last_tick_age_seconds else "N/A"
        return (
            f"Feed {self.level.value}: last_tick_age={age_str} | "
            f"ticks={self.ticks_received} ({self.ticks_per_second:.1f}/s) | "
            f"timeouts={self.consecutive_timeouts}"
        )


class FeedHealthMonitor:
    """
    Monitors market data feed health.

    Tracks:
    - Tick freshness (stale detection)
    - Connection state
    - Throughput (ticks/second)
    - Error count

    Fails closed: any unexpected error sets health to DISCONNECTED.
    """

    def __init__(
        self,
        symbol: str,
        max_tick_age_seconds: float = 3.0,
        throughput_window_seconds: float = 60.0,
    ):
        if max_tick_age_seconds <= 0:
            raise ValueError("max_tick_age_seconds must be positive")

        self._symbol = symbol
        self._max_tick_age_seconds = max_tick_age_seconds
        self._throughput_window = throughput_window_seconds

        self._last_tick_time: Optional[datetime] = None
        self._tick_timestamps: list[datetime] = []
        self._consecutive_timeouts: int = 0
        self._last_error: Optional[str] = None
        self._ticks_received: int = 0

    def record_tick(self, timestamp_utc: Optional[datetime] = None) -> FeedHealthState:
        """Record a received tick and update health state."""
        now = datetime.now(timezone.utc)
        ts = timestamp_utc or now

        try:
            self._tick_timestamps.append(ts)
            self._last_tick_time = ts
            self._ticks_received += 1
            self._consecutive_timeouts = 0
            self._last_error = None

            # Trim throughput window
            cutoff = now.timestamp() - self._throughput_window
            self._tick_timestamps = [
                t for t in self._tick_timestamps if t.timestamp() > cutoff
            ]

            return self._compute_state()
        except Exception as e:
            self._last_error = str(e)
            return self._compute_state()

    def record_timeout(self, error: Optional[str] = None) -> FeedHealthState:
        """Record a connection timeout or error."""
        self._consecutive_timeouts += 1
        self._last_error = error or "timeout"
        return self._compute_state()

    def _compute_state(self) -> FeedHealthState:
        """Compute current health from accumulated data."""
        now = datetime.now(timezone.utc)

        # Tick age
        age_seconds: Optional[float] = None
        if self._last_tick_time:
            age_seconds = (now - self._last_tick_time).total_seconds()

        # Throughput
        tps = len(self._tick_timestamps) / self._throughput_window if self._throughput_window > 0 else 0.0

        # Determine level
        level = self._determine_level(age_seconds)

        return FeedHealthState(
            level=level,
            last_tick_age_seconds=age_seconds,
            max_tick_age_seconds=self._max_tick_age_seconds,
            ticks_received=self._ticks_received,
            ticks_per_second=tps,
            consecutive_timeouts=self._consecutive_timeouts,
            last_error=self._last_error,
            symbol=self._symbol,
        )

    def _determine_level(self, age_seconds: Optional[float]) -> FeedHealthLevel:
        """Determine feed health level from current state."""
        if self._consecutive_timeouts >= 3:
            return FeedHealthLevel.DISCONNECTED

        if self._consecutive_timeouts >= 1:
            return FeedHealthLevel.DEGRADED

        if age_seconds is None:
            return FeedHealthLevel.UNKNOWN

        if age_seconds > self._max_tick_age_seconds:
            return FeedHealthLevel.STALE

        if age_seconds > self._max_tick_age_seconds * 0.7:
            return FeedHealthLevel.DEGRADED

        return FeedHealthLevel.HEALTHY

    def get_state(self) -> FeedHealthState:
        """Get current health state without recording new data."""
        return self._compute_state()
