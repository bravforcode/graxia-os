"""Multi-symbol measurement daemon (Phase 1).

One process, one MT5 connection, subscribes ticks for every candidate/measuring
symbol, classifies each tick with the existing TickRecorder quality rules
(VALID/STALE/OUT_OF_ORDER/GAP), records per-session-day coverage, and writes
rolling per-symbol parquet (data/ticks/{symbol}_{date}.parquet).

The batch core (MeasurementBatchProcessor) is pure and testable without MT5;
MeasurementDaemon wraps it with the broker loop.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from market_data.coverage_tracker import MIN_VALID_TICKS_PER_SESSION_DAY, CoverageTracker
from market_data.tick_recorder import TickRecord, TickRecorder


def write_daily_parquet(
    records: list[TickRecord],
    out_dir: str | Path,
    symbol: str,
    trading_day: date,
) -> Path:
    """Write records to data/ticks/{symbol}_{YYYY-MM-DD}.parquet and return the path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{symbol}_{trading_day.isoformat()}.parquet"
    df = pd.DataFrame(
        [
            {
                "timestamp_utc": r.timestamp_utc.isoformat(),
                "received_at_utc": r.received_at_utc.isoformat(),
                "symbol": r.symbol,
                "bid": float(r.bid),
                "ask": float(r.ask),
                "last": float(r.last),
                "spread_points": float(r.spread_points),
                "flags": r.flags,
                "sequence_id": r.sequence_id,
                "connection_session_id": r.connection_session_id,
                "source": r.source,
                "data_quality": r.data_quality,
            }
            for r in records
        ]
    )
    df.to_parquet(path, index=False)
    return path


def spread_bps(tick: TickRecord) -> float:
    """Spread in basis points of position notional from a TickRecord."""
    mid = (float(tick.bid) + float(tick.ask)) / 2.0
    if mid <= 0:
        return float("inf")
    return (float(tick.ask) - float(tick.bid)) / mid * 10_000.0


@dataclass(frozen=True)
class SessionDaySummary:
    symbol: str
    trading_day: date
    session_name: str
    valid_ticks: int
    had_gap: bool
    covered: bool


class MeasurementBatchProcessor:
    """Pure per-batch processing core: route TickRecords into per-session-day
    counts and coverage updates. No MT5 dependency."""

    def __init__(self, tracker: CoverageTracker):
        self._tracker = tracker

    def process(self, records: list[TickRecord]) -> list[SessionDaySummary]:
        """Group records by (trading_day, session), count VALID ticks, flag
        gaps (a GAP-quality tick inside a session invalidates that session-day),
        and update the tracker. Returns one summary per observed session-day."""
        buckets: dict[tuple[date, str], list[TickRecord]] = {}
        for r in records:
            ts = r.timestamp_utc.astimezone(UTC)
            session = self._tracker.classify(ts)
            if session is None:
                continue
            buckets.setdefault((ts.date(), session), []).append(r)

        summaries: list[SessionDaySummary] = []
        for (trading_day, session_name), group in buckets.items():
            valid = sum(1 for r in group if r.data_quality == "VALID")
            had_gap = any(r.data_quality == "GAP" for r in group)
            newly_covered = self._tracker.record_session_day(trading_day, session_name, valid, had_gap)
            summaries.append(
                SessionDaySummary(
                    symbol=self._tracker._symbol,
                    trading_day=trading_day,
                    session_name=session_name,
                    valid_ticks=valid,
                    had_gap=had_gap,
                    covered=newly_covered,
                )
            )
        return summaries


class MeasurementDaemon:
    """Broker-facing daemon: polls get_current_tick() per symbol, feeds one
    TickRecorder per symbol, persists ticks daily, and updates coverage."""

    def __init__(
        self,
        symbols: list[str],
        *,
        coverage_dir: str | Path,
        ticks_dir: str | Path,
        session_id: str,
        tick_provider=None,
        min_valid_ticks: int = MIN_VALID_TICKS_PER_SESSION_DAY,
        symbol_map: dict[str, str] | None = None,
    ):
        """tick_provider: callable(symbol) -> dict|None (defaults to
        broker.mt5_gateway.get_current_tick). Tests inject a mock.
        symbol_map: universe symbol -> broker symbol (e.g. {"USOIL": "SpotCrude"});
        ticks are fetched from the broker name while coverage/parquet stay
        keyed by the universe symbol."""
        self._symbols = symbols
        self._symbol_map = symbol_map or {}
        self._coverage_dir = Path(coverage_dir)
        self._ticks_dir = Path(ticks_dir)
        self._session_id = session_id
        self._tick_provider = tick_provider or self._default_tick_provider
        self._min_valid_ticks = min_valid_ticks
        self._recorders = {sym: TickRecorder(sym, session_id) for sym in symbols}
        self._trackers = {
            sym: CoverageTracker(
                sym,
                self._coverage_dir / f"{sym}_coverage.json",
                min_valid_ticks=min_valid_ticks,
            )
            for sym in symbols
        }

    @staticmethod
    def _default_tick_provider(symbol: str) -> dict | None:
        from broker.mt5_gateway import Mt5UnavailableError, get_current_tick

        try:
            return get_current_tick(symbol)
        except Mt5UnavailableError:
            return None

    def _tick_for(self, symbol: str) -> dict | None:
        """Fetch a tick for the universe symbol, resolving broker-name mapping.
        Uses the injected tick_provider (tests inject a mock); the default
        provider resolves symbol_map before calling the broker."""
        if self._tick_provider is not self._default_tick_provider:
            return self._tick_provider(symbol)
        mt5_name = self._symbol_map.get(symbol, symbol)
        return self._default_tick_provider(mt5_name)

    def _tick_to_record(self, symbol: str, tick: dict) -> TickRecord | None:
        from decimal import Decimal

        ts = datetime.fromtimestamp(int(tick["time"]), tz=UTC)
        return self._recorders[symbol].record_tick(
            bid=Decimal(str(tick["bid"])),
            ask=Decimal(str(tick["ask"])),
            last=Decimal(str(tick["last"])),
            timestamp_utc=ts,
            source="mt5",
        )

    def run_once(self) -> dict:
        """Poll all symbols once, persist ticks per day, update coverage.
        Returns per-symbol progress dicts."""
        today = datetime.now(UTC).date()
        per_symbol: dict[str, dict] = {}
        for symbol in self._symbols:
            tick = self._tick_for(symbol)
            if tick is not None:
                self._tick_to_record(symbol, tick)
            recorder = self._recorders[symbol]
            tracker = self._trackers[symbol]
            if recorder.count() > 0:
                records = recorder.get_ticks()
                write_daily_parquet(records, self._ticks_dir, symbol, today)
            tracker.save()
            per_symbol[symbol] = tracker.progress()
        return per_symbol

    def run_forever(self, interval_seconds: float = 1.0) -> None:
        while True:
            try:
                self.run_once()
            except KeyboardInterrupt:
                return
            time.sleep(interval_seconds)
