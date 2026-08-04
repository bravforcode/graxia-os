"""Multi-symbol measurement daemon (Phase 1, delta-stream).

One process, one MT5 connection, delta-fetches ticks for every
candidate/measuring symbol via copy_ticks_from (no polling gaps),
classifies each tick with the existing TickRecorder quality rules
(VALID/STALE/OUT_OF_ORDER/GAP), records per-session-day coverage, and
writes rolling per-symbol parquet (data/ticks/{symbol}_{date}.parquet)
with atomic writes + INV-005 manifests.

The batch core (MeasurementBatchProcessor) and delta core
(StreamCollector) are pure and testable without MT5; MeasurementDaemon
wraps them with the broker loop and connection-recovery backoff.
"""

from __future__ import annotations

import importlib.util

# INV-005 ticks manifest (Task 8). `data` is not importable as a top-level
# package (data/__init__.py imports `..core.enums`, which exceeds the
# top-level package in this layout), so load data/manifest.py directly —
# same pattern as scripts/generate_manifests.py.
import sys as _sys
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from market_data.coverage_tracker import MIN_VALID_TICKS_PER_SESSION_DAY, CoverageTracker
from market_data.stream_collector import StreamCollector
from market_data.tick_recorder import TickRecord, TickRecorder
from market_data.tick_store import merge_write_batch

_manifest_spec = importlib.util.spec_from_file_location(
    "data_manifest_mod", Path(__file__).resolve().parent.parent / "data" / "manifest.py"
)
assert (
    _manifest_spec is not None and _manifest_spec.loader is not None
), "data/manifest.py must be loadable (INV-005 ticks manifest)"
_data_manifest_mod = importlib.util.module_from_spec(_manifest_spec)
_sys.modules["data_manifest_mod"] = _data_manifest_mod  # dataclass machinery needs it
_manifest_spec.loader.exec_module(_data_manifest_mod)
DataManifestManager = _data_manifest_mod.DataManifestManager


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
                # Delta-stream fields — canonical parity with tick_store layout
                # so DuckDB tick views (v_ticks) can project time_msc/volume
                # across live and backfill files (union_by_name).
                "time_msc": r.time_msc,
                "volume": r.volume,
                "flags_mt5": r.mt5_flags,
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
    """Broker-facing daemon: delta-fetches ticks per symbol via
    copy_ticks_from, feeds one TickRecorder per symbol, persists ticks
    daily, and updates coverage."""

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
        flush_cadence_sec: float = 5.0,
        max_buffer_ticks: int = 50_000,
    ):
        """tick_provider: callable(symbol, from_msc) -> list[dict] (defaults to
        broker.mt5_gateway.get_ticks_from). Tests inject a mock.
        symbol_map: universe symbol -> broker symbol (e.g. {"USOIL": "SpotCrude"});
        ticks are fetched from the broker name while coverage/parquet stay
        keyed by the universe symbol.
        flush_cadence_sec: max seconds between parquet flushes (0.0 = every
        cycle, tests). max_buffer_ticks: flush once the buffer exceeds this."""
        self._symbols = symbols
        self._symbol_map = symbol_map or {}
        self._coverage_dir = Path(coverage_dir)
        self._ticks_dir = Path(ticks_dir)
        self._session_id = session_id
        self._tick_provider = tick_provider or self._default_tick_provider
        self._min_valid_ticks = min_valid_ticks
        self._flush_cadence_sec = flush_cadence_sec
        self._max_buffer_ticks = max_buffer_ticks
        self._recorders = {sym: TickRecorder(sym, session_id) for sym in symbols}
        self._trackers = {
            sym: CoverageTracker(
                sym,
                self._coverage_dir / f"{sym}_coverage.json",
                min_valid_ticks=min_valid_ticks,
            )
            for sym in symbols
        }
        self._collector = StreamCollector(symbols, self._tick_for_delta)
        self._buffer: list[TickRecord] = []
        self._last_flush = time.time()
        self._last_processed: dict[str, datetime | None] = {sym: None for sym in symbols}
        self._backoff_base = 1.0
        self._manifest = DataManifestManager(self._ticks_dir.parent / "manifests")

    @staticmethod
    def _default_tick_provider(symbol: str, from_msc: int) -> list[dict]:
        from broker.mt5_gateway import get_ticks_from

        return get_ticks_from(symbol, from_msc)

    def _tick_for_delta(self, symbol: str, from_msc: int) -> list[dict]:
        """Fetch delta ticks for the universe symbol, resolving broker-name
        mapping. Uses the injected tick_provider (tests inject a mock); the
        default provider resolves symbol_map before calling the broker."""
        if self._tick_provider is not self._default_tick_provider:
            return self._tick_provider(symbol, from_msc)
        mt5_name = self._symbol_map.get(symbol, symbol)
        return self._default_tick_provider(mt5_name, from_msc)

    def _tick_to_record(self, symbol: str, tick: dict) -> TickRecord:
        from decimal import Decimal

        ts = datetime.fromtimestamp(int(tick["time_msc"]) / 1000.0, tz=UTC)
        return self._recorders[symbol].record_tick(
            bid=Decimal(str(tick["bid"])),
            ask=Decimal(str(tick["ask"])),
            last=Decimal(str(tick["last"])),
            timestamp_utc=ts,
            time_msc=int(tick["time_msc"]),
            volume=float(tick["volume"]),
            mt5_flags=int(tick["flags"]),
            source="mt5",
        )

    def run_once(self) -> dict:
        """Delta-fetch all symbols once, update coverage, flush parquet on
        cadence/buffer/day triggers. Returns per-symbol progress dicts."""
        per_symbol: dict[str, dict] = {}
        for symbol in self._symbols:
            new_ticks = self._collector.poll(symbol)
            for tick in new_ticks:
                self._buffer.append(self._tick_to_record(symbol, tick))
            tracker = self._trackers[symbol]
            # Coverage only needs the new ticks (tracker takes max(prior, new)).
            since = self._last_processed[symbol]
            records = self._recorders[symbol].get_ticks(since)
            if records:
                MeasurementBatchProcessor(tracker).process(records)
                self._last_processed[symbol] = records[-1].timestamp_utc
            tracker.save()
            per_symbol[symbol] = tracker.progress()
        self._maybe_flush()
        return per_symbol

    def _maybe_flush(self) -> None:
        """Flush the buffer into per-day parquet files.

        Uses merge_write_batch: each flush MERGES the delta buffer into the
        day's accumulated file (dedupe on time_msc/bid/ask/last/volume), so
        earlier flushes are never lost and restarts never duplicate."""
        due = time.time() - self._last_flush >= self._flush_cadence_sec
        big = len(self._buffer) >= self._max_buffer_ticks
        if not (due or big) or not self._buffer:
            return
        by_day: dict[date, list[TickRecord]] = {}
        for r in self._buffer:
            by_day.setdefault(r.timestamp_utc.astimezone(UTC).date(), []).append(r)
        for day, records in by_day.items():
            merge_write_batch(records, self._ticks_dir, records[0].symbol, day)
        self._buffer.clear()
        self._last_flush = time.time()
        # INV-005: keep the ticks dataset manifest current after every flush.
        self._manifest.update_manifest("ticks", sorted(self._ticks_dir.glob("*.parquet")))

    def run_forever(self, interval_seconds: float = 1.0, stop_after: int | None = None) -> None:
        """Run the delta loop forever (or `stop_after` successful cycles in
        tests). On gateway errors, backs off exponentially (1,2,4,...30s)
        from the same cursor — no ticks lost."""
        from broker.mt5_gateway import Mt5UnavailableError

        cycles = 0
        backoff = self._backoff_base
        while True:
            cycles += 1
            if stop_after is not None and cycles > stop_after:
                return
            try:
                self.run_once()
                backoff = self._backoff_base
            except Mt5UnavailableError:
                time.sleep(min(backoff, 30.0))
                backoff = backoff * 2
                continue
            except KeyboardInterrupt:
                return
            time.sleep(interval_seconds)
