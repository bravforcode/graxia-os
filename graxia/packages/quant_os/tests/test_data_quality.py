"""Tests for data quality pipeline (§5)."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pandera as pa
import pytest

_QUANT_OS = Path(__file__).resolve().parent.parent


def _import_from_file(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


_schemas = _import_from_file("core.schemas", _QUANT_OS / "core" / "schemas.py")
XAUUSD_M15_SCHEMA = _schemas.XAUUSD_M15_SCHEMA
validate_ohlcv = _schemas.validate_ohlcv

_pit = _import_from_file("core.data.point_in_time_store", _QUANT_OS / "core" / "data" / "point_in_time_store.py")
PointInTimeStore = _pit.PointInTimeStore
as_of = _pit.as_of
store_point_in_time = _pit.store_point_in_time


def _make_valid_ohlcv(n_bars: int = 20) -> pd.DataFrame:
    np.random.seed(42)
    base = 3000.0
    rng = np.random.default_rng(42)
    close = base + np.cumsum(rng.normal(0, 2.5, n_bars))
    high = close + rng.uniform(1, 10, n_bars)
    low = close - rng.uniform(1, 10, n_bars)
    open_ = low + rng.uniform(0, 1, n_bars) * (high - low)
    idx = pd.date_range("2024-01-15 08:00", periods=n_bars, freq="15min", name="timestamp")

    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": rng.uniform(0, 1000, n_bars),
            "avg_spread": rng.uniform(0, 1.0, n_bars),
        },
        index=idx,
    )


class TestSchema:
    def test_schema_valid_ohlcv_passes(self):
        df = _make_valid_ohlcv(50)
        result = validate_ohlcv(df, source="test")
        assert len(result) == 50

    def test_schema_high_low_violation_fails(self):
        df = _make_valid_ohlcv(20)
        df.iloc[5, df.columns.get_loc("high")] = df.iloc[5, df.columns.get_loc("low")] - 1.0
        with pytest.raises(pa.errors.SchemaError, match="high < low"):
            XAUUSD_M15_SCHEMA.validate(df)

    def test_schema_price_jump_fails(self):
        df = _make_valid_ohlcv(30)
        prev = df.iloc[10, df.columns.get_loc("close")]
        new_close = prev * 1.07
        df.iloc[11, df.columns.get_loc("close")] = new_close
        df.iloc[11, df.columns.get_loc("high")] = new_close + 5.0
        with pytest.raises(pa.errors.SchemaError, match="Price jump >5%"):
            XAUUSD_M15_SCHEMA.validate(df)

    def test_schema_null_spread_allowed(self):
        df = _make_valid_ohlcv(20)
        df["avg_spread"] = np.nan
        result = XAUUSD_M15_SCHEMA.validate(df)
        assert result["avg_spread"].isna().all()

    def test_schema_volume_range_violation_fails(self):
        df = _make_valid_ohlcv(20)
        df["volume"] = -1.0
        with pytest.raises(pa.errors.SchemaError):
            XAUUSD_M15_SCHEMA.validate(df)

    def test_schema_price_out_of_range_fails(self):
        df = _make_valid_ohlcv(20)
        df.iloc[3, df.columns.get_loc("open")] = 200.0
        with pytest.raises(pa.errors.SchemaError):
            XAUUSD_M15_SCHEMA.validate(df)


class TestPointInTimeStore:
    @pytest.fixture
    def store(self):
        s = PointInTimeStore()
        s.append("DFII10", pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03 10:00"), -0.85)
        s.append("DFII10", pd.Timestamp("2024-01-03"), pd.Timestamp("2024-01-04 10:00"), -0.80)
        s.append("COT_GOLD_LONG", pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-05 15:30"), 250_000)
        return s

    def test_point_in_time_as_of_filters(self, store):
        query = pd.Timestamp("2024-01-03 12:00")
        result = as_of(store.to_dataframe(), query)
        assert len(result) == 1
        assert result.iloc[0]["series"] == "DFII10"

    def test_point_in_time_as_of_takes_latest(self, store):
        query = pd.Timestamp("2024-01-06")
        result = as_of(store.to_dataframe(), query)
        series_names = set(result["series"])
        assert series_names == {"DFII10", "COT_GOLD_LONG"}
        dfii = result[result["series"] == "DFII10"].iloc[0]
        assert dfii["value"] == -0.80

    def test_point_in_time_get_as_of(self, store):
        query = pd.Timestamp("2024-01-05 14:00")
        result = store.get_as_of(query)
        assert len(result) == 1
        assert result.iloc[0]["series"] == "DFII10"

    def test_point_in_time_get_latest(self, store):
        result = store.get_latest()
        assert len(result) == 2

    def test_point_in_time_save_load(self, store, tmp_path):
        path = str(tmp_path / "pit_test.parquet")
        store.save(path)
        s2 = PointInTimeStore()
        s2.load(path)
        assert len(s2.to_dataframe()) == 3
        assert list(s2.to_dataframe().columns) == list(store.to_dataframe().columns)

    def test_point_in_time_published_lag(self):
        row = store_point_in_time(
            "SERIES_A",
            pd.Timestamp("2024-06-01"),
            pd.Timestamp("2024-06-03 09:00"),
            1.23,
        )
        assert row["published_lag"] == pd.Timedelta("2 days 09:00:00")

    def test_point_in_time_empty_as_of(self, store):
        query = pd.Timestamp("2023-01-01")
        result = as_of(store.to_dataframe(), query)
        assert result.empty


class TestVerifyM15:
    def test_m15_integrity_input_path_must_exist(self):
        verify = _import_from_file("scripts.verify_m15", _QUANT_OS / "scripts" / "verify_m15.py")
        full_integrity_check = verify.full_integrity_check

        with pytest.raises(FileNotFoundError):
            full_integrity_check("nonexistent_file.parquet")
