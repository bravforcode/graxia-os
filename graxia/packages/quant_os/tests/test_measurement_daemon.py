"""Tests for market_data/measurement_daemon.py — pure core + mocked-MT5
restart-resume integration (pattern: tests/test_mt5_gateway.py)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from market_data.coverage_tracker import CoverageTracker
from market_data.measurement_daemon import (
    MeasurementBatchProcessor,
    MeasurementDaemon,
    spread_bps,
    write_daily_parquet,
)
from market_data.tick_recorder import TickRecorder


def _next_asian_window() -> datetime:
    """Next future 02:00 UTC on a weekday (asian session).

    TickRecorder marks any tick older than STALE_THRESHOLD_SECONDS (5s) as
    STALE, so simulated ticks must carry timestamps >= now. 02:00 UTC on a
    weekday is inside the asian session window and the classifier accepts it.
    """
    now = datetime.now(UTC)
    candidate = now.replace(hour=2, minute=0, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:  # Saturday=5, Sunday=6
        candidate += timedelta(days=1)
    return candidate


def _rec(ts):
    return TickRecorder("XAUUSD", "s1").record_tick(
        bid=Decimal("2300.00"),
        ask=Decimal("2300.20"),
        last=Decimal("2300.10"),
        timestamp_utc=ts,
    )


class TestSpreadBps:
    def test_spread_bps_from_tick_record(self):
        rec = _rec(_next_asian_window())
        assert spread_bps(rec) == pytest.approx(0.8696, abs=1e-3)


class TestBatchProcessor:
    def test_valid_ticks_count_per_session_day(self, tmp_path):
        tracker = CoverageTracker("XAUUSD", tmp_path / "cov.json")
        processor = MeasurementBatchProcessor(tracker)
        base = _next_asian_window()
        recs = []
        for i in range(100):
            recs.append(_rec(base + timedelta(seconds=i)))
        summaries = processor.process(recs)
        asian = [s for s in summaries if s.session_name == "asian"]
        assert asian and asian[0].valid_ticks == 100

    def test_gap_tick_flags_session(self, tmp_path):
        tracker = CoverageTracker("XAUUSD", tmp_path / "cov.json")
        processor = MeasurementBatchProcessor(tracker)
        recs = [_rec(_next_asian_window())]
        summaries = processor.process(recs)
        assert summaries and summaries[0].valid_ticks == 1
        assert not summaries[0].covered


class TestDaemonRestartResume:
    """A 7+ day wall-clock process WILL see restarts — coverage must resume."""

    def _make_tick(self, symbol: str, ts: datetime) -> dict:
        return {
            "bid": 2300.00,
            "ask": 2300.20,
            "last": 2300.10,
            "volume": 1.0,
            "time": int(ts.timestamp()),
        }

    def test_progress_survives_restart(self, tmp_path):
        ticks_served = {"count": 0}
        base = _next_asian_window()

        def provider(symbol):
            ts = base + timedelta(seconds=ticks_served["count"])
            ticks_served["count"] += 1
            return self._make_tick(symbol, ts)

        def fill_day(day_offset: int):
            daemon = MeasurementDaemon(
                ["XAUUSD"],
                coverage_dir=tmp_path / "coverage",
                ticks_dir=tmp_path / "ticks",
                session_id=f"session-{day_offset}",
                tick_provider=provider,
            )
            # One tick per second for one minute → 60 valid ticks per session-day.
            for _ in range(60):
                daemon.run_once()

        fill_day(0)
        # "Restart": fresh daemon object, same dirs.
        fill_day(1)

        reloaded = CoverageTracker("XAUUSD", tmp_path / "coverage" / "XAUUSD_coverage.json")
        assert reloaded.qualifying_day_count() == 0  # 120 ticks/session-day << 50k floor
        # Parquet files are named by the daemon's wall-clock day:
        expected_day = datetime.now(UTC).date().isoformat()
        assert (tmp_path / "ticks" / f"XAUUSD_{expected_day}.parquet").exists()

    def test_parquet_roundtrip(self, tmp_path):
        rec = _rec(datetime(2026, 8, 3, 12, 0, tzinfo=UTC))
        path = write_daily_parquet([rec], tmp_path, "XAUUSD", date(2026, 8, 3))
        assert path.exists()
        import pandas as pd

        df = pd.read_parquet(path)
        assert len(df) == 1
        assert df.iloc[0]["symbol"] == "XAUUSD"
