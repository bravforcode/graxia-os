"""C2 tests: Arrow format data loader."""

import sys
from pathlib import Path

import pandas as pd
import pytest

_PACKAGES = Path(__file__).resolve().parent.parent.parent
if str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

from quant_os.backtest.data_loader import _validate_ohlcv_schema, load_arrow, to_arrow

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ohlcv_df(n: int = 100) -> pd.DataFrame:
    """Create a valid OHLCV DataFrame with DatetimeIndex."""
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    rng = range(n)
    return pd.DataFrame(
        {
            "open": [1.0 + i * 0.001 for i in rng],
            "high": [1.01 + i * 0.001 for i in rng],
            "low": [0.99 + i * 0.001 for i in rng],
            "close": [1.005 + i * 0.001 for i in rng],
            "volume": [1_000_000.0 + i for i in rng],
        },
        index=idx,
    )


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    """_validate_ohlcv_schema rejects malformed DataFrames."""

    def test_missing_columns(self):
        df = pd.DataFrame({"open": [1.0], "high": [1.0]})
        with pytest.raises(ValueError, match="Missing required OHLCV columns"):
            _validate_ohlcv_schema(df)

    def test_non_numeric_column(self):
        idx = pd.date_range("2024-01-01", periods=1, freq="1h", tz="UTC")
        df = pd.DataFrame(
            {
                "open": ["not_a_number"],
                "high": [1.0],
                "low": [1.0],
                "close": [1.0],
                "volume": [1.0],
            },
            index=idx,
        )
        with pytest.raises(ValueError, match="must be numeric"):
            _validate_ohlcv_schema(df)

    def test_non_datetime_index(self):
        df = pd.DataFrame(
            {
                "open": [1.0],
                "high": [1.0],
                "low": [1.0],
                "close": [1.0],
                "volume": [1.0],
            },
            index=[0],
        )
        with pytest.raises(ValueError, match="DatetimeIndex"):
            _validate_ohlcv_schema(df)

    def test_unsorted_index(self):
        idx = pd.date_range("2024-01-01", periods=3, freq="1h", tz="UTC")
        df = pd.DataFrame(
            {
                "open": [1.0, 2.0, 3.0],
                "high": [1.0, 2.0, 3.0],
                "low": [1.0, 2.0, 3.0],
                "close": [1.0, 2.0, 3.0],
                "volume": [1.0, 2.0, 3.0],
            },
            index=idx[::-1],
        )
        with pytest.raises(ValueError, match="ascending"):
            _validate_ohlcv_schema(df)

    def test_valid_df_passes(self):
        df = _make_ohlcv_df()
        _validate_ohlcv_schema(df)  # no exception


# ---------------------------------------------------------------------------
# Round-trip: DataFrame -> Arrow -> DataFrame
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """Write Arrow, read it back, verify values match."""

    def test_feather_round_trip(self, tmp_path: pytest.TempPathFactory):
        df = _make_ohlcv_df()
        path = str(tmp_path / "test.feather")

        to_arrow(df, path)
        loaded = load_arrow(path)

        pd.testing.assert_frame_equal(df, loaded, check_freq=False)

    def test_arrow_round_trip(self, tmp_path: pytest.TempPathFactory):
        df = _make_ohlcv_df()
        path = str(tmp_path / "test.arrow")

        to_arrow(df, path)
        loaded = load_arrow(path)

        pd.testing.assert_frame_equal(df, loaded, check_freq=False)

    def test_csv_to_arrow_to_df(self, tmp_path: pytest.TempPathFactory):
        """CSV -> Arrow -> DataFrame preserves values."""
        csv_path = str(tmp_path / "ohlcv.csv")
        df = _make_ohlcv_df()
        # Write CSV with tz-naive datetime to match default date_format
        csv_df = df.copy()
        csv_df.index = csv_df.index.tz_localize(None)
        csv_df.reset_index().rename(columns={"index": "Date"}).to_csv(csv_path, index=False)

        # Convert to arrow and back
        arrow_path = str(tmp_path / "roundtrip.feather")
        csv_df.columns = [c.lower() for c in csv_df.columns]
        csv_df.index.name = "Date"

        to_arrow(csv_df, arrow_path)
        loaded = load_arrow(arrow_path)

        assert loaded.shape == csv_df.shape
        for col in csv_df.columns:
            assert loaded[col].tolist() == pytest.approx(csv_df[col].tolist(), rel=1e-10)


# ---------------------------------------------------------------------------
# pyarrow optional import
# ---------------------------------------------------------------------------


class TestOptionalPyarrow:
    """pyarrow import is optional — graceful error when missing."""

    def test_import_error_message(self, monkeypatch):
        import importlib
        import sys

        saved = sys.modules.pop("pyarrow", None)
        monkeypatch.setitem(sys.modules, "pyarrow", None)

        from quant_os.backtest import data_loader

        importlib.reload(data_loader)

        with pytest.raises(ImportError, match="pyarrow"):
            data_loader._require_pyarrow()

        if saved is not None:
            sys.modules["pyarrow"] = saved


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case coverage."""

    def test_empty_dataframe_raises(self):
        idx = pd.DatetimeIndex([], name="Date", tz="UTC")
        df = pd.DataFrame(
            {
                "open": [],
                "high": [],
                "low": [],
                "close": [],
                "volume": [],
            },
            index=idx,
        )
        _validate_ohlcv_schema(df)

    def test_single_bar(self, tmp_path: pytest.TempPathFactory):
        df = _make_ohlcv_df(n=1)
        path = str(tmp_path / "single.feather")
        to_arrow(df, path)
        loaded = load_arrow(path)
        assert len(loaded) == 1
        assert loaded["close"].iloc[0] == df["close"].iloc[0]
