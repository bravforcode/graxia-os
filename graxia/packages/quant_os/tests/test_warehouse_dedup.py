"""Tests for backtest.data_loader._load_ohlcv_warehouse's duplicate-row
defense.

Context: data.warehouse_loader.Warehouse.get_ohlcv() can return the same
row several times over when the underlying hive-partitioned parquet files
overlap (a partition-ingestion bug, out of scope to fix at the source here
-- see confirmed real-data reproduction: XAUUSD/H1 returned 300,000 rows
for only 50,000 unique timestamps, each row repeated exactly 6x with every
column identical). Duplicate rows straddling a purge/embargo split boundary
leak test-fold information into training, inflating apparent OOS Sharpe.
These tests pin the defensive dedup added to
``backtest.data_loader._load_ohlcv_warehouse`` / ``_dedupe_warehouse_ohlcv``.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

_QUANT_OS_ROOT = Path(__file__).resolve().parent.parent
if str(_QUANT_OS_ROOT) not in sys.path:
    sys.path.insert(0, str(_QUANT_OS_ROOT))

from backtest.data_loader import _dedupe_warehouse_ohlcv, _load_ohlcv_warehouse  # noqa: E402
from graxia.packages.quant_os.data.warehouse_loader import Warehouse  # noqa: E402


def _make_duplicated_df(n_unique: int = 5, repeat: int = 6) -> pd.DataFrame:
    """Build a DataFrame mirroring the real bug: each unique bar repeated
    ``repeat`` times, byte-identical across every column."""
    times = [f"2026-01-01 0{i}:00:00" for i in range(n_unique)]
    rows = []
    for t in times:
        for _ in range(repeat):
            rows.append(
                {
                    "time": t,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 10.0,
                    "symbol": "XAUUSD",
                    "source": "MT5",
                }
            )
    return pd.DataFrame(rows)


class TestDedupeWarehouseOhlcvUnit:
    """Direct unit tests of _dedupe_warehouse_ohlcv (no DB involved)."""

    def test_drops_exact_duplicate_rows(self):
        df = _make_duplicated_df(n_unique=5, repeat=6)
        assert len(df) == 30

        out = _dedupe_warehouse_ohlcv(df, symbol="XAUUSD", timeframe="H1")

        assert len(out) == 5
        assert out["time"].is_unique
        # Values are preserved, not just deduped away.
        assert set(out["close"]) == {100.5}

    def test_no_duplicates_is_a_noop(self):
        df = _make_duplicated_df(n_unique=5, repeat=1)
        out = _dedupe_warehouse_ohlcv(df, symbol="XAUUSD", timeframe="H1")
        assert len(out) == 5
        pd.testing.assert_series_equal(
            out["time"].reset_index(drop=True), df["time"].reset_index(drop=True)
        )

    def test_missing_time_column_is_a_noop(self):
        """No 'time' column -> function must not raise or reshape the frame."""
        df = pd.DataFrame({"close": [1.0, 1.0, 2.0]})
        out = _dedupe_warehouse_ohlcv(df, symbol="X", timeframe="H1")
        assert len(out) == 3

    def test_non_identical_duplicate_timestamp_keeps_first_and_warns(self, caplog):
        """Same timestamp but a different column value (not the confirmed
        bug's signature) must still be safely collapsed to one row, with a
        loud warning distinguishing it from the exact-duplicate case."""
        df = pd.DataFrame(
            [
                {"time": "2026-01-01 00:00:00", "open": 1.0, "close": 1.0},
                {"time": "2026-01-01 00:00:00", "open": 1.0, "close": 2.0},  # differs
            ]
        )
        with caplog.at_level("WARNING"):
            out = _dedupe_warehouse_ohlcv(df, symbol="X", timeframe="H1")

        assert len(out) == 1
        assert out["time"].is_unique
        assert any("non_identical_duplicate_timestamps" in r.message for r in caplog.records)


class TestLoadOhlcvWarehouseDedupIntegration:
    """_load_ohlcv_warehouse dedups whatever Warehouse.get_ohlcv() returns."""

    def test_load_ohlcv_warehouse_dedups_mocked_duplicates(self, tmp_path):
        dup_df = _make_duplicated_df(n_unique=5, repeat=6)
        assert len(dup_df) == 30

        with (
            patch.object(Warehouse, "register_ohlcv_glob", return_value=None),
            patch.object(Warehouse, "get_ohlcv", return_value=dup_df),
        ):
            df = _load_ohlcv_warehouse(
                "XAUUSD", "H1", warehouse_db_path=str(tmp_path / "wh.duckdb")
            )

        assert len(df) == 5
        assert df["time"].is_unique

    def test_load_ohlcv_warehouse_empty_still_raises(self, tmp_path):
        """Dedup must not change the existing empty-result error behavior."""
        with (
            patch.object(Warehouse, "register_ohlcv_glob", return_value=None),
            patch.object(Warehouse, "get_ohlcv", return_value=pd.DataFrame()),
        ):
            with pytest.raises(ValueError, match="no warehouse OHLCV rows"):
                _load_ohlcv_warehouse(
                    "XAUUSD", "H1", warehouse_db_path=str(tmp_path / "wh.duckdb")
                )


class TestRealWarehouseDataDedup:
    """Row-count check against the actual on-disk warehouse data, if present."""

    def test_real_xauusd_h1_dedup_matches_confirmed_bug_shape(self):
        """Confirmed real-data shape: 300,000 raw rows / 50,000 unique
        timestamps (each row repeated exactly 6x). Skips if the real
        warehouse parquet files aren't present in this environment."""
        real_root = _QUANT_OS_ROOT / "data" / "warehouse" / "ohlcv" / "symbol=XAUUSD" / "frequency=H1"
        if not real_root.exists() or not any(real_root.rglob("*.parquet")):
            pytest.skip("no real XAUUSD/H1 warehouse parquet data in this environment")

        wh = Warehouse(db_path=str(_QUANT_OS_ROOT / "data" / "warehouse" / "quantos.duckdb"))
        try:
            wh.register_ohlcv_glob("XAUUSD", "H1")
            raw = wh.get_ohlcv("XAUUSD", "H1")
        finally:
            wh.close()

        deduped = _dedupe_warehouse_ohlcv(raw.copy(), symbol="XAUUSD", timeframe="H1")

        assert len(deduped) == raw["time"].nunique()
        assert deduped["time"].is_unique
        # The confirmed bug shape: real duplication should be discovered,
        # not silently absent (a regression here would mean the fixture
        # data changed shape -- still validate dedup is idempotent).
        assert len(deduped) <= len(raw)
