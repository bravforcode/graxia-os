"""
Clock Drift Detection Guard for Quant OS

Compares MT5 server time against local system time to detect clock drift.
Excessive drift can cause stale data, misaligned candles, and incorrect signals.
"""

from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Optional


@dataclass
class ClockState:
    """Snapshot of clock synchronization state"""
    mt5_time_utc: datetime
    local_time_utc: datetime
    drift_ms: float  # positive = MT5 ahead, negative = MT5 behind
    is_drifted: bool
    max_drift_ms: float
    last_check_utc: datetime

    @property
    def drift_seconds(self) -> float:
        return self.drift_ms / 1000.0

    def summary(self) -> str:
        direction = "ahead" if self.drift_ms >= 0 else "behind"
        status = "DRIFTED" if self.is_drifted else "OK"
        return (
            f"Clock {status}: MT5 {abs(self.drift_ms):.1f}ms {direction} | "
            f"threshold={self.max_drift_ms:.0f}ms"
        )


class ClockGuard:
    """
    Clock Drift Detection Guard

    Compares MT5 server time with local UTC time on each tick/candle.
    Triggers alert when drift exceeds configurable threshold.

    Typical use:
        guard = ClockGuard(max_drift_ms=500)
        state = guard.check_clock(mt5_time_utc)
        if state.is_drifted:
            # pause trading, log alert
    """

    def __init__(self, max_drift_ms: float = 500.0):
        if max_drift_ms <= 0:
            raise ValueError("max_drift_ms must be positive")
        self._max_drift_ms = max_drift_ms
        self._last_state: Optional[ClockState] = None

    def check_clock(self, mt5_time_utc: datetime) -> ClockState:
        """
        Compare MT5 time with local time, detect drift.

        Args:
            mt5_time_utc: The current time reported by MT5 server (must be timezone-aware UTC)

        Returns:
            ClockState snapshot with drift measurement
        """
        if mt5_time_utc.tzinfo is None:
            mt5_time_utc = mt5_time_utc.replace(tzinfo=UTC)

        local_time_utc = datetime.now(UTC)

        drift_ms = (mt5_time_utc - local_time_utc).total_seconds() * 1000.0

        state = ClockState(
            mt5_time_utc=mt5_time_utc,
            local_time_utc=local_time_utc,
            drift_ms=drift_ms,
            is_drifted=abs(drift_ms) > self._max_drift_ms,
            max_drift_ms=self._max_drift_ms,
            last_check_utc=local_time_utc,
        )

        self._last_state = state
        return state

    def is_drifted(self) -> bool:
        """Check if last measurement exceeded drift threshold"""
        if self._last_state is None:
            return False
        return self._last_state.is_drifted

    def get_state(self) -> Optional[ClockState]:
        """Return the last measured clock state"""
        return self._last_state

    def get_drift_ms(self) -> Optional[float]:
        """Return drift in milliseconds (positive = MT5 ahead), or None if never checked"""
        if self._last_state is None:
            return None
        return self._last_state.drift_ms
