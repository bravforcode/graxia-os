"""Tests for market_data/tick_store.py — atomic parquet write_batch
(flat layout, extended schema, no leftover temp files)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

from market_data.tick_recorder import TickRecorder
from market_data.tick_store import write_batch


def _rec(ts, msc, vol):
    return TickRecorder("XAUUSD", "s1").record_tick(
        bid=Decimal("2300.00"),
        ask=Decimal("2300.20"),
        last=Decimal("2300.10"),
        timestamp_utc=ts,
        time_msc=msc,
        volume=vol,
        mt5_flags=0,
    )


def test_write_batch_atomic_and_schema(tmp_path):
    recs = [_rec(datetime.now(UTC), 1764864000000, 1.0)]
    path = write_batch(recs, tmp_path, "XAUUSD", date(2026, 8, 4))
    assert path == tmp_path / "XAUUSD_2026-08-04.parquet"
    assert path.exists()
    assert not Path(str(path) + ".tmp").exists()  # no temp left behind
    df = pd.read_parquet(path)
    assert len(df) == 1
    assert df.iloc[0]["time_msc"] == 1764864000000
    assert df.iloc[0]["volume"] == 1.0
    assert df.iloc[0]["flags_mt5"] == 0
    assert df.iloc[0]["flags"] == ""  # quality-tag column preserved
    assert df.iloc[0]["data_quality"] == "VALID"


def test_write_batch_overwrites_complete_file(tmp_path):
    a = _rec(datetime.now(UTC), 1764864000000, 1.0)
    write_batch([a], tmp_path, "XAUUSD", date(2026, 8, 4))
    b = _rec(datetime.now(UTC), 1764864060000, 2.0)
    write_batch([a, b], tmp_path, "XAUUSD", date(2026, 8, 4))
    df = pd.read_parquet(tmp_path / "XAUUSD_2026-08-04.parquet")
    assert len(df) == 2  # full replacement, never partial append
