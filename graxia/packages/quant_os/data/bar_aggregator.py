"""
Bar Aggregator — aggregates live ticks into OHLCV bars with VWAP.

Subscribes to tick events from the EventBus, accumulates them into
time-aligned bars, and emits completed bars when each timeframe closes.

Supports multiple simultaneous timeframes per symbol. Bars are aligned
to standard boundaries (e.g. 1m bars at :00, :01, :02, …; 1h bars at
:00 of each hour).

Usage:
    from core.event_bus import EventBus
    bus = EventBus()
    await bus.start()

    aggregator = BarAggregator(
        symbols=["XAUUSD"],
        timeframes=["1m", "5m", "15m", "1h"],
        event_bus=bus,
    )
    await aggregator.start()
    # ... ticks flow in via EventBus ...
    await aggregator.stop()
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# ── Timeframe definitions ──────────────────────────────────────────

TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}

TIMEFRAME_LABELS: dict[str, str] = {
    "1m": "M1",
    "5m": "M5",
    "15m": "M15",
    "30m": "M30",
    "1h": "H1",
    "4h": "H4",
    "1d": "D1",
}


def align_to_boundary(timestamp: float, timeframe_sec: int) -> float:
    """
    Align a unix timestamp to the start of its timeframe boundary.

    Args:
        timestamp: Unix epoch seconds.
        timeframe_sec: Timeframe duration in seconds.

    Returns:
        Epoch seconds of the bar's opening time.
    """
    return (timestamp // timeframe_sec) * timeframe_sec


# ── In-progress bar state ──────────────────────────────────────────


@dataclass
class BarAccumulator:
    """Mutable accumulator for a single in-progress bar."""

    symbol: str
    timeframe: str
    open_time: float  # Epoch seconds of bar boundary
    open: float = 0.0
    high: float = float("-inf")
    low: float = float("inf")
    close: float = 0.0
    volume: float = 0.0
    tick_count: int = 0

    # VWAP accumulation
    _vwap_numerator: float = 0.0  # sum(price * volume)
    _vwap_denominator: float = 0.0  # sum(volume)

    @property
    def vwap(self) -> float:
        """Volume-Weighted Average Price. Returns close if no volume."""
        if self._vwap_denominator > 0:
            return self._vwap_numerator / self._vwap_denominator
        return self.close

    def add_tick(self, bid: float, ask: float, volume: float, timestamp: float) -> None:
        """
        Incorporate a tick into the accumulator.

        Args:
            bid: Bid price.
            ask: Ask price.
            volume: Tick volume.
            timestamp: Tick epoch seconds.
        """
        mid = (bid + ask) / 2.0
        self.tick_count += 1

        if self.tick_count == 1:
            self.open = mid

        self.high = max(self.high, mid)
        self.low = min(self.low, mid)
        self.close = mid
        self.volume += volume

        # VWAP: use mid-price weighted by volume
        if volume > 0:
            self._vwap_numerator += mid * volume
            self._vwap_denominator += volume

    def to_dict(self) -> dict[str, Any]:
        """Convert completed bar to a dict for storage/event emission."""
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": datetime.fromtimestamp(
                self.open_time,
                tz=UTC,
            ).isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "vwap": round(self.vwap, 8),
            "tick_count": self.tick_count,
        }

    @property
    def is_valid(self) -> bool:
        """A bar is valid if it received at least one tick."""
        return self.tick_count > 0


# ── Completed bar (immutable) ─────────────────────────────────────


@dataclass(frozen=True)
class CompletedBar:
    """Immutable completed bar emitted by the aggregator."""

    symbol: str
    timeframe: str
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float
    tick_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.open_time.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "vwap": round(self.vwap, 8),
            "tick_count": self.tick_count,
        }


# ── Aggregator stats ──────────────────────────────────────────────


@dataclass
class AggregatorStats:
    """Mutable statistics for monitoring."""

    total_ticks_processed: int = 0
    total_bars_emitted: int = 0
    active_bars: int = 0
    symbols_tracked: int = 0
    timeframes_tracked: int = 0


# ── Bar Aggregator ────────────────────────────────────────────────


class BarAggregator:
    """
    Multi-symbol, multi-timeframe bar aggregator.

    Subscribes to ``tick.{asset_class}.new`` events on the EventBus,
    accumulates ticks into aligned OHLCV bars, and emits completed bars
    as ``bar.{asset_class}.completed`` events.

    Also writes completed bars to the DuckDBWriteQueue if provided.

    Args:
        symbols: Symbols to aggregate.
        timeframes: Timeframe strings (e.g. "1m", "5m", "15m", "1h", "4h", "1d").
        event_bus: EventBus for subscribing/publishing.
        write_queue: Optional DuckDBWriteQueue for persistence.
        on_bar: Optional async callback for each completed bar.
    """

    def __init__(
        self,
        symbols: Sequence[str],
        timeframes: Sequence[str],
        event_bus: Any,  # EventBus
        write_queue: Any | None = None,  # DuckDBWriteQueue
        on_bar: Callable[[CompletedBar], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        self._symbols = tuple(s.upper() for s in symbols)
        self._timeframes = tuple(timeframes)
        self._event_bus = event_bus
        self._write_queue = write_queue
        self._on_bar = on_bar

        # Validate timeframes
        for tf in self._timeframes:
            if tf not in TIMEFRAME_SECONDS:
                raise ValueError(f"Unknown timeframe '{tf}'. " f"Supported: {list(TIMEFRAME_SECONDS.keys())}")

        # Key: (symbol, timeframe) → BarAccumulator
        self._active_bars: dict[tuple[str, str], BarAccumulator] = {}
        self._stats = AggregatorStats()
        self._running = False

        # Deferred import
        from .quality_gate import classify_symbol

        self._classify_symbol = classify_symbol

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Subscribe to tick events and start aggregation."""
        if self._running:
            return

        # Subscribe to tick events for each asset class
        asset_classes = set()
        for sym in self._symbols:
            asset_classes.add(self._classify_symbol(sym))

        for ac in asset_classes:
            subject = f"tick.{ac}.new"
            self._event_bus.subscribe(subject, self._on_tick_event)

        self._running = True
        self._stats.symbols_tracked = len(self._symbols)
        self._stats.timeframes_tracked = len(self._timeframes)

        logger.info(
            "bar_aggregator.started",
            symbols=list(self._symbols),
            timeframes=list(self._timeframes),
        )

    async def stop(self) -> None:
        """Flush in-progress bars and unsubscribe."""
        if not self._running:
            return
        self._running = False

        # Emit any in-progress bars as final bars
        for key, bar in list(self._active_bars.items()):
            if bar.is_valid:
                await self._emit_bar(bar)
        self._active_bars.clear()

        logger.info(
            "bar_aggregator.stopped",
            total_bars_emitted=self._stats.total_bars_emitted,
        )

    @property
    def stats(self) -> AggregatorStats:
        self._stats.active_bars = len(self._active_bars)
        return self._stats

    # ------------------------------------------------------------------
    # Tick processing
    # ------------------------------------------------------------------

    async def _on_tick_event(self, data: Any) -> None:
        """
        Callback registered with EventBus.

        Args:
            data: MT5Tick dataclass from the tick ingester.
        """
        if not self._running:
            return

        symbol = str(data.symbol).upper()
        if symbol not in self._symbols:
            return

        try:
            bid = float(data.bid)
            ask = float(data.ask)
            volume = float(data.volume)
            timestamp = self._parse_timestamp(data.timestamp)
        except (AttributeError, TypeError, ValueError):
            logger.debug("bar_aggregator.bad_tick", data=data)
            return

        await self._process_tick(symbol, bid, ask, volume, timestamp)

    async def _process_tick(
        self,
        symbol: str,
        bid: float,
        ask: float,
        volume: float,
        timestamp: float,
    ) -> None:
        """Route a tick to all timeframe accumulators."""
        self._stats.total_ticks_processed += 1

        for tf in self._timeframes:
            tf_sec = TIMEFRAME_SECONDS[tf]
            boundary = align_to_boundary(timestamp, tf_sec)
            key = (symbol, tf)

            bar = self._active_bars.get(key)

            if bar is None:
                # Start a new bar
                bar = BarAccumulator(
                    symbol=symbol,
                    timeframe=tf,
                    open_time=boundary,
                )
                self._active_bars[key] = bar

            elif bar.open_time < boundary:
                # Tick crossed a boundary → close old bar, start new one
                if bar.is_valid:
                    await self._emit_bar(bar)

                bar = BarAccumulator(
                    symbol=symbol,
                    timeframe=tf,
                    open_time=boundary,
                )
                self._active_bars[key] = bar

            bar.add_tick(bid, ask, volume, timestamp)

    async def _emit_bar(self, bar: BarAccumulator) -> None:
        """Emit a completed bar to EventBus, write queue, and callback."""
        completed = CompletedBar(
            symbol=bar.symbol,
            timeframe=bar.timeframe,
            open_time=datetime.fromtimestamp(bar.open_time, tz=UTC),
            open=bar.open,
            high=bar.high if bar.high != float("-inf") else bar.open,
            low=bar.low if bar.low != float("inf") else bar.open,
            close=bar.close,
            volume=bar.volume,
            vwap=bar.vwap,
            tick_count=bar.tick_count,
        )

        # Serialize only for DuckDB write queue
        bar_dict = completed.to_dict()

        # Publish typed CompletedBar to event bus
        asset_cls = self._classify_symbol(bar.symbol)
        subject = f"bar.{asset_cls}.completed"
        try:
            await self._event_bus.publish(subject, completed)
        except Exception:
            logger.exception("bar_aggregator.publish_error", subject=subject)

        # Write to DuckDB
        if self._write_queue is not None:
            try:
                await self._write_queue.enqueue("bars", [bar_dict])
            except Exception:
                logger.exception("bar_aggregator.write_error")

        # Custom callback
        if self._on_bar is not None:
            try:
                await self._on_bar(completed)
            except Exception:
                logger.exception("bar_aggregator.on_bar_error")

        self._stats.total_bars_emitted += 1
        logger.debug(
            "bar_aggregator.bar_emitted",
            symbol=bar.symbol,
            timeframe=bar.timeframe,
            open_time=bar_dict["timestamp"],
            ticks=bar.tick_count,
            vwap=round(bar.vwap, 5),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_timestamp(ts: Any) -> float:
        """Convert various timestamp formats to epoch seconds."""
        if isinstance(ts, (int, float)):
            return ts / 1000.0 if ts > 1e12 else float(ts)
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                return ts.replace(tzinfo=UTC).timestamp()
            return ts.timestamp()
        if isinstance(ts, str):
            for fmt in (
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
            ):
                try:
                    dt = datetime.strptime(ts, fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=UTC)
                    return dt.timestamp()
                except ValueError:
                    continue
        raise ValueError(f"Cannot parse timestamp: {ts!r}")

    def get_active_bar(
        self,
        symbol: str,
        timeframe: str,
    ) -> dict[str, Any] | None:
        """
        Snapshot of the current in-progress bar (for dashboards).

        Args:
            symbol: Symbol name.
            timeframe: Timeframe string.

        Returns:
            Bar dict or None if no ticks received yet for this bar.
        """
        bar = self._active_bars.get((symbol.upper(), timeframe))
        if bar is None or not bar.is_valid:
            return None
        return bar.to_dict()
