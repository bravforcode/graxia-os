"""
Feed Health Monitor for Quant OS

Tracks real-time tick health per symbol:
- Stale detection (no ticks within threshold)
- Gap detection (missing ticks in sequence)
- Consecutive stale tracking
- State machine: HEALTHY -> STALE_FEED -> DISCONNECTED
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class FeedHealthState:
    """Immutable snapshot of feed health for a symbol."""

    symbol: str
    state: str  # "HEALTHY" | "STALE_FEED" | "DISCONNECTED" | "UNKNOWN"
    last_tick_age_seconds: float | None
    tick_count_last_minute: int
    gap_count: int
    stale_count: int
    consecutive_stale: int
    last_check_utc: datetime


class FeedHealthMonitor:
    """
    Per-symbol feed health monitor.

    State transitions:
        UNKNOWN -> HEALTHY      (first tick received)
        HEALTHY -> STALE_FEED   (no tick within max_tick_age_seconds)
        STALE_FEED -> HEALTHY   (tick received)
        STALE_FEED -> DISCONNECTED (consecutive_stale >= 3)

    Gap detection: tick timestamp jumps forward by more than
    2x the expected tick interval (inferred from rolling median).
    """

    def __init__(self, symbol: str, max_tick_age_seconds: float = 3.0):
        self._symbol = symbol
        self._max_tick_age = max_tick_age_seconds

        self._last_tick_time: datetime | None = None
        self._tick_times: list[datetime] = []
        self._gap_count: int = 0
        self._stale_count: int = 0
        self._consecutive_stale: int = 0
        self._state: str = "UNKNOWN"
        self._tick_count_last_minute: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_tick_received(self, tick_timestamp: datetime, received_at: datetime) -> FeedHealthState:
        """
        Process an incoming tick.

        Args:
            tick_timestamp: Exchange timestamp of the tick.
            received_at: Local wall-clock time when tick arrived.

        Returns:
            Updated FeedHealthState.
        """
        now = received_at if received_at.tzinfo else received_at.replace(tzinfo=UTC)
        tick_ts = tick_timestamp if tick_timestamp.tzinfo else tick_timestamp.replace(tzinfo=UTC)

        # Track tick age (latency)
        tick_age = max(0.0, (now - tick_ts).total_seconds())

        # Gap detection: compare to previous tick timestamp
        if self._last_tick_time is not None:
            interval = (tick_ts - self._last_tick_time).total_seconds()
            if interval > self._expected_interval() * 2 and interval > 1.0:
                self._gap_count += 1

        self._last_tick_time = tick_ts
        self._tick_times.append(now)

        # Purge ticks older than 60 s from the rolling window
        cutoff = now - timedelta(seconds=60)
        self._tick_times = [t for t in self._tick_times if t > cutoff]
        self._tick_count_last_minute = len(self._tick_times)

        # Reset consecutive stale on valid tick
        self._consecutive_stale = 0
        self._state = "HEALTHY"

        return self.check_health()

    def check_health(self) -> FeedHealthState:
        """
        Return current health assessment.

        If the last tick is older than max_tick_age the state degrades.
        """
        now = datetime.now(UTC)
        last_age: float | None = None

        if self._last_tick_time is not None:
            last_age = max(0.0, (now - self._last_tick_time).total_seconds())

            if last_age > self._max_tick_age:
                self._consecutive_stale += 1
                self._stale_count += 1

                if self._consecutive_stale >= 3:
                    self._state = "DISCONNECTED"
                else:
                    self._state = "STALE_FEED"
            elif self._state in ("STALE_FEED", "DISCONNECTED") and self._consecutive_stale == 0:
                self._state = "HEALTHY"

        return FeedHealthState(
            symbol=self._symbol,
            state=self._state,
            last_tick_age_seconds=last_age,
            tick_count_last_minute=self._tick_count_last_minute,
            gap_count=self._gap_count,
            stale_count=self._stale_count,
            consecutive_stale=self._consecutive_stale,
            last_check_utc=now,
        )

    def is_healthy(self) -> bool:
        """Convenience: True only when state is HEALTHY."""
        return self._state == "HEALTHY"

    def reset(self) -> None:
        """Reset all counters and state to UNKNOWN."""
        self._last_tick_time = None
        self._tick_times.clear()
        self._gap_count = 0
        self._stale_count = 0
        self._consecutive_stale = 0
        self._tick_count_last_minute = 0
        self._state = "UNKNOWN"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _expected_interval(self) -> float:
        """
        Estimate expected tick interval from recent history.

        Uses rolling median of inter-tick deltas (seconds).
        Falls back to 1.0 s when insufficient data.
        """
        if len(self._tick_times) < 3:
            return 1.0

        deltas = sorted(
            (self._tick_times[i] - self._tick_times[i - 1]).total_seconds() for i in range(1, len(self._tick_times))
        )
        mid = len(deltas) // 2
        return max(0.001, deltas[mid])
