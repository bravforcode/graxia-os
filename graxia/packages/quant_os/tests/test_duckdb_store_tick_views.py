"""Tests for Task 6 — DuckDB tick views, whitelisted parameterized
query_ticks, and transactional tick_coverage_summary upsert."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from data_pipeline.storage.duckdb_store import DuckDBStore
from market_data.tick_recorder import TickRecorder
from market_data.tick_store import write_batch


def _seed_ticks(tmp_path: Path):
    recs = [
        TickRecorder("XAUUSD", "s1").record_tick(
            bid=Decimal("2300.00"),
            ask=Decimal("2300.20"),
            last=Decimal("2300.10"),
            timestamp_utc=datetime.now(UTC),
            time_msc=1764864000000,
            volume=1.0,
            mt5_flags=0,
        )
    ]
    write_batch(recs, tmp_path / "ticks", "XAUUSD", date(2026, 8, 4))
    return tmp_path / "ticks"


def test_query_ticks_parameterized(tmp_path):
    ticks_dir = _seed_ticks(tmp_path)
    store = DuckDBStore(str(tmp_path / "store.duckdb"))
    store.register_tick_views(ticks_glob=str(ticks_dir / "*.parquet"))
    df = store.query_ticks("XAUUSD", 1764863999000, 1764864001000)
    assert len(df) == 1
    assert df.iloc[0]["bid"] == pytest.approx(2300.00)


def test_query_ticks_rejects_unlisted_view(tmp_path):
    store = DuckDBStore(str(tmp_path / "store.duckdb"))
    with pytest.raises(ValueError, match="view not in whitelist"):
        store.query_ticks("XAUUSD", 0, 1, view="v_ticks; DROP TABLE market_data")


def test_view_sees_newly_flushed_parquet(tmp_path):
    ticks_dir = tmp_path / "ticks"
    ticks_dir.mkdir()
    store = DuckDBStore(str(tmp_path / "store.duckdb"))
    store.register_tick_views(ticks_glob=str(ticks_dir / "*.parquet"))
    _seed_ticks(tmp_path)  # write AFTER view creation
    df = store.query_ticks("XAUUSD", 0, 10**18)
    assert len(df) == 1  # glob view picks up the new file


def test_upsert_coverage_summary_pk_and_transaction(tmp_path):
    store = DuckDBStore(str(tmp_path / "store.duckdb"))
    store.register_tick_views()
    store.upsert_coverage_summary(
        [
            {
                "symbol": "XAUUSD",
                "date": "2026-08-04",
                "source": "mt5",
                "total_ticks": 100,
                "valid_ticks": 95,
                "stale_ticks": 2,
                "gap_ticks": 3,
                "out_of_order_ticks": 0,
                "updated_at": "2026-08-04T12:00:00Z",
            },
        ]
    )
    store.upsert_coverage_summary(
        [
            {
                "symbol": "XAUUSD",
                "date": "2026-08-04",
                "source": "mt5",
                "total_ticks": 150,
                "valid_ticks": 145,
                "stale_ticks": 2,
                "gap_ticks": 3,
                "out_of_order_ticks": 0,
                "updated_at": "2026-08-04T13:00:00Z",
            },
        ]
    )
    df = pd.read_sql("SELECT * FROM tick_coverage_summary", store.conn)
    assert len(df) == 1  # PK upsert — one row, not two
    assert df.iloc[0]["total_ticks"] == 150
