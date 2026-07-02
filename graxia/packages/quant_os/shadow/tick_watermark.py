"""Tick watermark — tracks the latest finalized tick time.

Prevents re-processing of old ticks and ensures monotonic progress.
"""
from datetime import datetime
from typing import Optional


class TickWatermark:
    """Immutable tick watermark tracking.

    The watermark represents the latest tick time that has been
    fully processed. New queries start from watermark - overlap.
    """

    def __init__(self, overlap_seconds: int = 300):
        self._overlap_seconds = overlap_seconds
        self._watermark: Optional[datetime] = None
        self._tick_count: int = 0

    def update(self, tick_time_utc: datetime) -> None:
        """Update watermark if tick is newer."""
        if self._watermark is None or tick_time_utc > self._watermark:
            self._watermark = tick_time_utc
        self._tick_count += 1

    def query_start(self, system_utc: datetime, safety_lag_seconds: int = 2) -> datetime:
        """Calculate query start: watermark - overlap (or system_utc - overlap if no watermark)."""
        if self._watermark is not None:
            base = self._watermark
        else:
            base = system_utc
        from datetime import timedelta
        return base - timedelta(seconds=self._overlap_seconds)

    def query_end(self, system_utc: datetime, safety_lag_seconds: int = 2) -> datetime:
        """Calculate query end: system_utc - safety_lag."""
        from datetime import timedelta
        return system_utc - timedelta(seconds=safety_lag_seconds)

    @property
    def watermark(self) -> Optional[datetime]:
        return self._watermark

    @property
    def tick_count(self) -> int:
        return self._tick_count

    def data_age_ms(self, system_utc: datetime) -> float:
        """Data age: system_utc - watermark in milliseconds."""
        if self._watermark is None:
            return float("inf")
        return (system_utc - self._watermark).total_seconds() * 1000
