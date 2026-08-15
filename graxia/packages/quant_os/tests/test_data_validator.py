"""Tests for data.validator — 3-stage data validation pipeline."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from graxia.packages.quant_os.data.validator import DataValidator


def _make_clean_ohlcv(n: int = 20) -> pd.DataFrame:
    """Build a valid OHLCV DataFrame with sensible random data."""
    rng = np.random.default_rng(42)
    base = 3000.0
    close = base + np.cumsum(rng.normal(0, 2.5, n))
    high = close + rng.uniform(1, 10, n)
    low = close - rng.uniform(1, 10, n)
    open_ = low + rng.uniform(0, 1, n) * (high - low)
    idx = pd.date_range("2024-01-15 08:00", periods=n, freq="15min", name="timestamp")
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": rng.uniform(100, 1000, n),
        },
        index=idx,
    )


class TestValidateOhlcv:
    def test_validate_ohlcv_passes_clean_data(self):
        """DataValidator().validate_ohlcv returns passed=True for a clean DF."""
        v = DataValidator()
        df = _make_clean_ohlcv(20)
        result = v.validate_ohlcv(df, symbol="XAUUSD")
        assert result.passed is True
        assert result.failures == []
        assert result.stage == "all"
        assert len(result.checks) >= 3  # at least basic+schema+business

    def test_validate_ohlcv_fails_on_nulls(self):
        """A DataFrame with nulls in any column should fail BASIC null check."""
        v = DataValidator()
        df = _make_clean_ohlcv(20)
        df.loc[df.index[3], "close"] = np.nan
        result = v.validate_ohlcv(df, symbol="XAUUSD")
        assert result.passed is False
        assert any("BASIC:null_columns" in f for f in result.failures)

    def test_validate_ohlcv_fails_on_missing_columns(self):
        """DF missing required columns should fail schema check."""
        v = DataValidator()
        df = _make_clean_ohlcv(20)
        # Drop 'volume' and 'low' to trigger the missing columns branch.
        df = df.drop(columns=["volume", "low"])
        result = v.validate_ohlcv(df, symbol="XAUUSD")
        assert result.passed is False
        assert any("SCHEMA:missing_columns" in f for f in result.failures)

    def test_validate_ohlcv_fails_on_negative_volume(self):
        """A negative volume should fail the BUSINESS negative_volume rule."""
        v = DataValidator()
        df = _make_clean_ohlcv(20)
        df.loc[df.index[2], "volume"] = -1.0
        result = v.validate_ohlcv(df, symbol="XAUUSD")
        assert result.passed is False
        assert any("BUSINESS:negative_volume" in f for f in result.failures)

    def test_validate_ohlcv_fails_on_high_less_than_low(self):
        """A row where high < low should fail the high_gte_low business rule."""
        v = DataValidator()
        df = _make_clean_ohlcv(20)
        df.loc[df.index[5], "high"] = df.loc[df.index[5], "low"] - 1.0
        result = v.validate_ohlcv(df, symbol="XAUUSD")
        assert result.passed is False
        assert any("BUSINESS:high_less_than_low" in f for f in result.failures)


class TestValidateManifestPresent:
    def test_validate_manifest_present(self, tmp_path: Path):
        """Directory with manifests for all data files returns passed=True."""
        from graxia.packages.quant_os.data.manifest import DataManifest

        # Two data files + matching manifests.
        f1 = tmp_path / "A_M1.parquet"
        f2 = tmp_path / "B_M1.parquet"
        f1.write_bytes(b"alpha")
        f2.write_bytes(b"beta")
        for f in (f1, f2):
            DataManifest.create_for_file(
                file_path=f,
                symbol=f.stem.split("_")[0],
                date_range="2024-01-01:2024-01-02",
                row_count=1,
                columns=["open", "high", "low", "close", "volume"],
                dtypes={"open": "float64"},
            )

        v = DataValidator()
        result = v.validate_manifest_present(tmp_path)
        assert result.passed is True
        assert result.failures == []
        # Both files were checked.
        assert any("A_M1.parquet" in c for c in result.checks)
        assert any("B_M1.parquet" in c for c in result.checks)

    def test_validate_manifest_present_missing_files(self, tmp_path: Path):
        """Directory missing one of the manifests returns failures."""
        from graxia.packages.quant_os.data.manifest import DataManifest

        good = tmp_path / "GOOD_M1.parquet"
        good.write_bytes(b"ok")
        DataManifest.create_for_file(
            file_path=good,
            symbol="GOOD",
            date_range="2024-01-01:2024-01-02",
            row_count=1,
            columns=["open", "high", "low", "close", "volume"],
            dtypes={"open": "float64"},
        )

        # This file has no manifest.
        (tmp_path / "ORPHAN_M1.parquet").write_bytes(b"orphan")

        v = DataValidator()
        result = v.validate_manifest_present(tmp_path)
        assert result.passed is False
        assert any("ORPHAN_M1.parquet" in f for f in result.failures)
        # Good one should be in checks.
        assert any("GOOD_M1.parquet" in c for c in result.checks)
