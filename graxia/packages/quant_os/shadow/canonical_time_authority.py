"""Canonical time authority — single source of truth for all timestamps.

Uses trusted system UTC for event/session/health decisions.
copy_ticks_range with UTC-aware input for market tick data.
No symbol_info_tick.time, no MT5 bar timestamps, no copy_ticks_from.
"""
from datetime import datetime, timezone
from typing import Optional


class CanonicalTimeAuthority:
    """Single clock model for the shadow system.

    event clock       = trusted system UTC
    market tick clock = copy_ticks_range UTC-aware
    bar close clock   = canonical bars built from tick stream
    """

    def __init__(self):
        self._tick_source_label = "copy_ticks_range_utc_aware"
        self._bar_source_label = "canonical_built_from_ticks"

    def trusted_system_utc(self) -> datetime:
        """System UTC — the only authority for event/session/health."""
        return datetime.now(timezone.utc)

    def tick_source(self) -> str:
        return self._tick_source_label

    def bar_source(self) -> str:
        return self._bar_source_label

    def is_tick_time_trusted(self) -> bool:
        """symbol_info_tick.time is NOT trusted for time decisions."""
        return False

    def is_bar_time_trusted(self) -> bool:
        """MT5 bar timestamps are NOT trusted for time decisions."""
        return False
