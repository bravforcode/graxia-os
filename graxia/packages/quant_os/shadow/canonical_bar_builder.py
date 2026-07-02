"""Canonical bar builder — constructs M1/H1 bars from canonical ticks only.

No MT5 bar API dependency. Bars are built from tick stream.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
from typing import Optional


@dataclass
class CanonicalBar:
    """Bar built from canonical ticks."""
    symbol: str
    timeframe: str  # "M1" or "H1"
    open_time: datetime
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    tick_count: int = 0
    volume: int = 0
    is_finalized: bool = False

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "open_time": self.open_time.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "tick_count": self.tick_count,
            "volume": self.volume,
            "is_finalized": self.is_finalized,
        }


class CanonicalBarBuilder:
    """Builds M1/H1 bars from canonical tick stream.

    Policy:
    - Bars are only finalized after bar_finalization_delay_seconds
    - Finalized bars are immutable
    - Strategy only sees finalized bars
    """

    def __init__(
        self,
        symbol: str,
        bar_finalization_delay_seconds: int = 120,
    ):
        self._symbol = symbol
        self._delay = bar_finalization_delay_seconds
        self._m1_bars: dict[datetime, CanonicalBar] = {}
        self._h1_bars: dict[datetime, CanonicalBar] = {}

    def _minute_start(self, ts: datetime) -> datetime:
        """Floor timestamp to minute boundary."""
        return ts.replace(second=0, microsecond=0)

    def _hour_start(self, ts: datetime) -> datetime:
        """Floor timestamp to hour boundary."""
        return ts.replace(minute=0, second=0, microsecond=0)

    def add_tick(self, tick: dict) -> None:
        """Add a tick to the bar builder."""
        tick_time = datetime.fromtimestamp(tick["time"], tz=UTC)
        bid = tick.get("bid", 0)
        ask = tick.get("ask", 0)
        mid = (bid + ask) / 2 if bid and ask else bid or ask
        vol = tick.get("volume", 0)

        # Update M1 bar
        m1_start = self._minute_start(tick_time)
        if m1_start not in self._m1_bars:
            self._m1_bars[m1_start] = CanonicalBar(
                symbol=self._symbol, timeframe="M1", open_time=m1_start,
                open=mid, high=mid, low=mid, close=mid,
            )
        bar = self._m1_bars[m1_start]
        bar.high = max(bar.high, mid)
        bar.low = min(bar.low, mid)
        bar.close = mid
        bar.tick_count += 1
        bar.volume += vol

        # Update H1 bar
        h1_start = self._hour_start(tick_time)
        if h1_start not in self._h1_bars:
            self._h1_bars[h1_start] = CanonicalBar(
                symbol=self._symbol, timeframe="H1", open_time=h1_start,
                open=mid, high=mid, low=mid, close=mid,
            )
        h1 = self._h1_bars[h1_start]
        h1.high = max(h1.high, mid)
        h1.low = min(h1.low, mid)
        h1.close = mid
        h1.tick_count += 1
        h1.volume += vol

    def finalize_bars(self, system_utc: datetime) -> None:
        """Finalize bars that are older than finalization delay."""
        cutoff = system_utc - timedelta(seconds=self._delay)
        for m1_start, bar in self._m1_bars.items():
            if not bar.is_finalized and m1_start + timedelta(minutes=1) <= cutoff:
                bar.is_finalized = True
        for h1_start, bar in self._h1_bars.items():
            if not bar.is_finalized and h1_start + timedelta(hours=1) <= cutoff:
                bar.is_finalized = True

    def get_finalized_m1_bars(self, count: int = 3) -> list[CanonicalBar]:
        """Get last N finalized M1 bars."""
        finalized = [b for b in self._m1_bars.values() if b.is_finalized]
        finalized.sort(key=lambda b: b.open_time)
        return finalized[-count:]

    def get_finalized_h1_bars(self, count: int = 3) -> list[CanonicalBar]:
        """Get last N finalized H1 bars."""
        finalized = [b for b in self._h1_bars.values() if b.is_finalized]
        finalized.sort(key=lambda b: b.open_time)
        return finalized[-count:]

    def get_current_m1_bar(self) -> Optional[CanonicalBar]:
        """Get the current (not yet finalized) M1 bar."""
        unfinalized = [b for b in self._m1_bars.values() if not b.is_finalized]
        if not unfinalized:
            return None
        return max(unfinalized, key=lambda b: b.open_time)

    def version(self) -> str:
        return "canonical_bar_builder_v1"
