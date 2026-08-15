"""Tests for Task 14 — load_real_ticks (DuckDB tick views → DataFrame or
None when no data) + engine real-spread hook fallback safety."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from backtest.data_loader import load_real_ticks
from data_pipeline.storage.duckdb_store import DuckDBStore
from market_data.tick_recorder import TickRecorder
from market_data.tick_store import write_batch


def test_load_real_ticks_returns_rows_or_none(tmp_path):
    store = DuckDBStore(str(tmp_path / "store.duckdb"))
    store.register_tick_views(ticks_glob=str(tmp_path / "no-such-dir" / "*.parquet"))
    df = load_real_ticks("XAUUSD", "2026-08-01", "2026-08-02", db=store)
    assert df is None  # no tick data → None, caller falls back to config


def test_load_real_ticks_reads_seeded_parquet(tmp_path):
    ticks_dir = tmp_path / "ticks"
    now = datetime.now(UTC)
    recs = [
        TickRecorder("XAUUSD", "s1").record_tick(
            bid=Decimal("2300.00"),
            ask=Decimal("2300.20"),
            last=Decimal("2300.10"),
            timestamp_utc=now,
            time_msc=int(now.timestamp() * 1000),
            volume=1.0,
            mt5_flags=0,
        )
    ]
    write_batch(recs, ticks_dir, "XAUUSD", now.date())
    store = DuckDBStore(str(tmp_path / "store.duckdb"))
    store.register_tick_views(ticks_glob=str(ticks_dir / "*.parquet"))
    start = (now - timedelta(days=1)).isoformat()
    end = (now + timedelta(days=1)).isoformat()
    df = load_real_ticks("XAUUSD", start, end, db=store)
    assert df is not None and len(df) == 1
    assert df.iloc[0]["bid"] == pytest.approx(2300.00)
