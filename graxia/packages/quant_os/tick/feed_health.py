"""Phase BE-P2 — Feed watermark and staleness monitor."""

import time


class FeedHealthMonitor:
    """Monitors tick feed health: watermark, staleness, session state."""

    def __init__(self, stale_threshold_ms: int = 5000):
        self.stale_threshold_ms = stale_threshold_ms
        self._last_tick_time_ms: int = 0
        self._last_tick_received_ns: int = 0
        self._tick_count: int = 0
        self._session_start_ns: int = 0

    def start_session(self) -> None:
        self._session_start_ns = time.monotonic_ns()
        self._tick_count = 0

    def record_tick(self, source_time_msc: int) -> None:
        """Record tick arrival for health monitoring."""
        self._last_tick_time_ms = source_time_msc
        self._last_tick_received_ns = time.monotonic_ns()
        self._tick_count += 1

    def is_stale(self) -> bool:
        """Check if feed is stale."""
        if self._last_tick_received_ns == 0:
            return True
        elapsed_ms = (time.monotonic_ns() - self._last_tick_received_ns) / 1_000_000
        return elapsed_ms > self.stale_threshold_ms

    def elapsed_since_last_tick_ms(self) -> float:
        if self._last_tick_received_ns == 0:
            return float("inf")
        return (time.monotonic_ns() - self._last_tick_received_ns) / 1_000_000

    def get_watermark(self) -> int:
        return self._last_tick_time_ms

    def get_tick_count(self) -> int:
        return self._tick_count

    def get_state(self) -> dict:
        return {
            "watermark_ms": self._last_tick_time_ms,
            "tick_count": self._tick_count,
            "is_stale": self.is_stale(),
            "elapsed_ms": self.elapsed_since_last_tick_ms(),
        }
