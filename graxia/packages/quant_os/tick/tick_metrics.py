"""Phase BE-P2 — Tick metrics collector."""
import time
from collections import deque


class TickMetrics:
    """Collects metrics per BE-P2 spec."""

    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self._spreads: deque = deque(maxlen=window_size)
        self._tick_times_ms: deque = deque(maxlen=window_size)
        self._clock_drifts_ms: deque = deque(maxlen=window_size)
        self._total_ticks: int = 0
        self._stale_count: int = 0
        self._duplicate_count: int = 0
        self._out_of_order_count: int = 0
        self._gap_count: int = 0
        self._session_start_ns: int = 0

    def start_session(self) -> None:
        self._session_start_ns = time.monotonic_ns()

    def record_tick(self, spread: float, source_time_msc: int,
                    local_time_ns: int = 0) -> None:
        """Record tick for metrics."""
        self._total_ticks += 1
        self._spreads.append(spread)
        self._tick_times_ms.append(source_time_msc)

        if local_time_ns > 0 and source_time_msc > 0:
            expected_ns = source_time_msc * 1_000_000
            drift_ns = local_time_ns - expected_ns
            self._clock_drifts_ms.append(drift_ns / 1_000_000)

    def record_stale(self) -> None:
        self._stale_count += 1

    def record_duplicate(self) -> None:
        self._duplicate_count += 1

    def record_out_of_order(self) -> None:
        self._out_of_order_count += 1

    def record_gap(self) -> None:
        self._gap_count += 1

    def get_spread_stats(self) -> dict:
        if not self._spreads:
            return {"p50": 0, "p90": 0, "p99": 0, "max": 0}
        sorted_spreads = sorted(self._spreads)
        n = len(sorted_spreads)
        return {
            "p50": sorted_spreads[n // 2],
            "p90": sorted_spreads[int(n * 0.9)],
            "p99": sorted_spreads[int(n * 0.99)],
            "max": sorted_spreads[-1],
        }

    def get_clock_drift_ms(self) -> dict:
        if not self._clock_drifts_ms:
            return {"mean": 0, "max": 0}
        return {
            "mean": sum(self._clock_drifts_ms) / len(self._clock_drifts_ms),
            "max": max(abs(d) for d in self._clock_drifts_ms),
        }

    def get_session_uptime_s(self) -> float:
        if self._session_start_ns == 0:
            return 0
        return (time.monotonic_ns() - self._session_start_ns) / 1_000_000_000

    def get_summary(self) -> dict:
        return {
            "total_ticks": self._total_ticks,
            "stale_count": self._stale_count,
            "duplicate_count": self._duplicate_count,
            "out_of_order_count": self._out_of_order_count,
            "gap_count": self._gap_count,
            "spread": self.get_spread_stats(),
            "clock_drift": self.get_clock_drift_ms(),
            "session_uptime_s": self.get_session_uptime_s(),
        }
