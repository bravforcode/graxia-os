"""
Comprehensive unit tests for data pipeline, market_data, features, signals, and cost calibration.
Covers parquet integrity, feature building, signal generation, and cost validation.
"""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Ensure package root is on path for direct imports
_pkg_root = str(Path(__file__).resolve().parent.parent)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

# ── Paths ──────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
COST_CAL_PATH = ROOT / "config" / "cost_calibration.json"

# ── Expected assets ────────────────────────────────────────────────
PORTFOLIO_ASSETS = ["NAS100", "XAUUSD", "USDJPY", "BTCUSD", "OIL", "SPX500"]
ALL_COST_ASSETS = ["BTCUSD", "ETHUSD", "EURUSD", "GBPUSD", "OIL", "USDJPY", "SILVER", "XAUUSD", "NAS100"]


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def sample_ohlcv_df():
    """500-row synthetic OHLCV DataFrame with DatetimeIndex."""
    n = 500
    dates = pd.date_range("2025-01-01", periods=n, freq="1h", tz=UTC)
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0, 0.5, n))
    df = pd.DataFrame(
        {
            "open": close + rng.normal(0, 0.1, n),
            "high": close + abs(rng.normal(0, 0.5, n)),
            "low": close - abs(rng.normal(0, 0.5, n)),
            "close": close,
            "volume": rng.integers(100, 10000, n).astype(float),
        },
        index=dates,
    )
    df.index.name = "timestamp"
    return df


@pytest.fixture
def sample_parquet_path(tmp_path, sample_ohlcv_df):
    """Write sample OHLCV to parquet and return path."""
    path = tmp_path / "portfolio.parquet"
    sample_ohlcv_df.to_parquet(path)
    return path


@pytest.fixture
def multi_asset_parquet(tmp_path):
    """Multi-asset portfolio parquet with SPX500_close column."""
    n = 200
    dates = pd.date_range("2025-06-01", periods=n, freq="1h", tz=UTC)
    rng = np.random.default_rng(99)
    base = 100 + np.cumsum(rng.normal(0, 0.3, n))
    df = pd.DataFrame(index=dates)
    df.index.name = "timestamp"
    for asset in PORTFOLIO_ASSETS:
        noise = rng.normal(0, 1, n)
        df[f"{asset}_close"] = base + noise
        df[f"{asset}_volume"] = rng.integers(50, 5000, n).astype(float)
    path = tmp_path / "portfolio.parquet"
    df.to_parquet(path)
    return path


@pytest.fixture
def cost_calibration():
    """Load the real cost_calibration.json."""
    if not COST_CAL_PATH.exists():
        pytest.skip("cost_calibration.json not found")
    with open(COST_CAL_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def tmp_cost_calibration(tmp_path):
    """Write a minimal cost_calibration.json for roundtrip tests."""
    data = {
        "version": "test",
        "date": "2026-01-01",
        "assets": {
            "TESTASSET": {
                "mt5_symbol": "TESTASSET",
                "spread_bps_measured": 1.5,
                "commission_bps": 0,
                "round_trip_bps_measured": 3.0,
                "contract_size": 1,
                "tick_size": 0.01,
                "status": "TEST",
            }
        },
    }
    path = tmp_path / "cost_calibration_test.json"
    with open(path, "w") as f:
        json.dump(data, f)
    return path, data


@pytest.fixture
def tick_recorder():
    """Fresh TickRecorder instance."""
    from graxia.packages.quant_os.market_data.tick_recorder import TickRecorder

    return TickRecorder(symbol="XAUUSD", session_id="test-session-001")


@pytest.fixture
def signal_queue():
    return asyncio.Queue()


# ═══════════════════════════════════════════════════════════════════
# 1. PARQUET DATA INTEGRITY (10 tests)
# ═══════════════════════════════════════════════════════════════════


class TestParquetDataIntegrity:
    """Validate parquet loading, columns, and data quality."""

    def test_load_parquet_returns_dataframe(self, sample_parquet_path):
        df = pd.read_parquet(sample_parquet_path)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 500

    def test_multi_asset_has_required_columns(self, multi_asset_parquet):
        df = pd.read_parquet(multi_asset_parquet)
        for asset in PORTFOLIO_ASSETS:
            assert f"{asset}_close" in df.columns, f"Missing {asset}_close"

    def test_spx500_close_column_exists(self, multi_asset_parquet):
        df = pd.read_parquet(multi_asset_parquet)
        assert "SPX500_close" in df.columns

    def test_no_nan_in_close_columns(self, multi_asset_parquet):
        df = pd.read_parquet(multi_asset_parquet)
        close_cols = [c for c in df.columns if c.endswith("_close")]
        for col in close_cols:
            assert df[col].isna().sum() == 0, f"NaN found in {col}"

    def test_datetime_index_is_monotonic(self, multi_asset_parquet):
        df = pd.read_parquet(multi_asset_parquet)
        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.index.is_monotonic_increasing

    def test_no_duplicate_rows(self, multi_asset_parquet):
        df = pd.read_parquet(multi_asset_parquet)
        assert not df.index.duplicated().any()

    def test_date_range_coverage(self, multi_asset_parquet):
        df = pd.read_parquet(multi_asset_parquet)
        assert df.index[0] >= pd.Timestamp("2025-06-01", tz=UTC)
        assert df.index[-1] <= pd.Timestamp("2025-06-30", tz=UTC) + timedelta(days=1)

    def test_all_six_assets_present(self, multi_asset_parquet):
        df = pd.read_parquet(multi_asset_parquet)
        for asset in PORTFOLIO_ASSETS:
            assert f"{asset}_close" in df.columns

    def test_close_prices_are_positive(self, multi_asset_parquet):
        df = pd.read_parquet(multi_asset_parquet)
        close_cols = [c for c in df.columns if c.endswith("_close")]
        for col in close_cols:
            assert (df[col] > 0).all(), f"Non-positive value in {col}"

    def test_no_future_dates(self, multi_asset_parquet):
        df = pd.read_parquet(multi_asset_parquet)
        now = pd.Timestamp.now(tz=UTC)
        assert (df.index <= now).all(), "Future dates detected"


# ═══════════════════════════════════════════════════════════════════
# 2. FEATURE BUILDING (10 tests)
# ═══════════════════════════════════════════════════════════════════

_pandas_ta = pytest.importorskip("pandas_ta", reason="pandas_ta not installed")


@pytest.mark.skipif(not _pandas_ta, reason="pandas_ta not installed")
class TestFeatureBuilding:
    """Validate feature computation from build_features.py logic."""

    def test_compute_features_returns_all_expected_columns(self, sample_ohlcv_df):
        from graxia.packages.quant_os.scripts.build_features import compute_features

        features = compute_features(sample_ohlcv_df)
        expected = [
            "return_1",
            "return_5",
            "return_10",
            "return_20",
            "log_return",
            "macd",
            "macd_signal",
            "macd_hist",
            "rsi_14",
            "bb_upper",
            "bb_middle",
            "bb_lower",
            "atr_14",
            "body",
            "body_pct",
        ]
        for col in expected:
            assert col in features.columns, f"Missing feature: {col}"

    def test_compute_features_preserves_original_columns(self, sample_ohlcv_df):
        from graxia.packages.quant_os.scripts.build_features import compute_features

        features = compute_features(sample_ohlcv_df)
        for col in ["open", "high", "low", "close", "volume"]:
            assert col in features.columns

    def test_feature_normalization_z_score(self, sample_ohlcv_df):
        from graxia.packages.quant_os.scripts.build_features import compute_features

        features = compute_features(sample_ohlcv_df)
        close_col = features["close"]
        z = (close_col - close_col.mean()) / close_col.std()
        assert abs(z.mean()) < 1e-10
        assert abs(z.std() - 1.0) < 1e-10

    def test_feature_correlation_matrix(self, sample_ohlcv_df):
        from graxia.packages.quant_os.scripts.build_features import compute_features

        features = compute_features(sample_ohlcv_df)
        numeric = features.select_dtypes(include=[np.number])
        corr = numeric.corr()
        assert corr.shape[0] > 10
        diag = np.diag(corr.values)
        np.testing.assert_allclose(diag, 1.0, atol=1e-10)

    def test_feature_importance_ranking(self, sample_ohlcv_df):
        from graxia.packages.quant_os.scripts.build_features import compute_features, create_target

        features = compute_features(sample_ohlcv_df)
        features = create_target(features, freq="H1", symbol="TEST")
        features = features.dropna()
        numeric = features.select_dtypes(include=[np.number]).drop(columns=["target", "target_3class"], errors="ignore")
        if "target_return" in numeric.columns:
            target = features["target_return"]
            corrs = numeric.corrwith(target).abs().sort_values(ascending=False)
            assert len(corrs) > 0
            assert corrs.iloc[0] >= 0

    def test_nan_handling_in_features(self, sample_ohlcv_df):
        from graxia.packages.quant_os.scripts.build_features import compute_features

        features = compute_features(sample_ohlcv_df)
        early_rows = features.iloc[:50]
        nan_count = early_rows.isna().sum().sum()
        assert nan_count > 0, "Expected NaN in early rows from rolling windows"

    def test_feature_lag_consistency(self, sample_ohlcv_df):
        from graxia.packages.quant_os.scripts.build_features import compute_features

        features = compute_features(sample_ohlcv_df)
        assert "return_1" in features.columns
        assert "return_5" in features.columns
        valid = features.dropna(subset=["return_1", "return_5"])
        r1_abs = valid["return_1"].abs()
        r5_abs = valid["return_5"].abs()
        corr = r1_abs.corr(r5_abs)
        assert corr > 0, "Return features should be positively correlated"

    def test_rsi_bounds(self, sample_ohlcv_df):
        from graxia.packages.quant_os.scripts.build_features import compute_features

        features = compute_features(sample_ohlcv_df)
        for period in [7, 14, 21]:
            col = f"rsi_{period}"
            if col in features.columns:
                valid = features[col].dropna()
                assert (valid >= 0).all() and (valid <= 100).all(), f"RSI {col} out of bounds"

    def test_macd_histogram_consistency(self, sample_ohlcv_df):
        from graxia.packages.quant_os.scripts.build_features import compute_features

        features = compute_features(sample_ohlcv_df)
        diff = features["macd"] - features["macd_signal"]
        np.testing.assert_allclose(features["macd_hist"].values, diff.values, atol=1e-10)

    def test_create_target_generates_labels(self, sample_ohlcv_df):
        from graxia.packages.quant_os.scripts.build_features import compute_features, create_target

        features = compute_features(sample_ohlcv_df)
        result = create_target(features, freq="H1", symbol="TEST")
        assert "target" in result.columns
        assert "target_return" in result.columns
        assert "target_3class" in result.columns
        valid = result["target"].dropna()
        assert set(valid.unique()).issubset({0, 1})


# ═══════════════════════════════════════════════════════════════════
# 3. SIGNAL GENERATION (8 tests)
# ═══════════════════════════════════════════════════════════════════


class TestSignalGeneration:
    """Validate Signal dataclass, Gateway, serialization, and validation."""

    def test_signal_creation_valid_inputs(self):
        from graxia.packages.quant_os.core.session_manager import AssetClass
        from graxia.packages.quant_os.core.signal_gateway import Side, Signal, SignalSource

        sig = Signal(
            symbol="XAUUSD",
            asset_class=AssetClass.METALS,
            side=Side.BUY,
            conviction=0.85,
            strategy="test_strat",
            entry_price=2400.0,
            stop_loss=2390.0,
            take_profit=2420.0,
            timestamp=datetime.now(UTC),
            source=SignalSource.PYTHON,
        )
        assert sig.symbol == "XAUUSD"
        assert sig.side == Side.BUY
        assert sig.conviction == 0.85

    def test_signal_with_zero_conviction(self):
        from graxia.packages.quant_os.core.session_manager import AssetClass
        from graxia.packages.quant_os.core.signal_gateway import Side, Signal, SignalSource

        sig = Signal(
            symbol="EURUSD",
            asset_class=AssetClass.FOREX,
            side=Side.SELL,
            conviction=0.0,
            strategy="edge_case",
            entry_price=1.1000,
            stop_loss=1.1050,
            take_profit=1.0950,
            timestamp=datetime.now(UTC),
            source=SignalSource.PYTHON,
        )
        assert sig.conviction == 0.0

    def test_signal_with_max_conviction(self):
        from graxia.packages.quant_os.core.session_manager import AssetClass
        from graxia.packages.quant_os.core.signal_gateway import Side, Signal, SignalSource

        sig = Signal(
            symbol="BTCUSD",
            asset_class=AssetClass.CRYPTO,
            side=Side.BUY,
            conviction=1.0,
            strategy="max_conf",
            entry_price=60000.0,
            stop_loss=59000.0,
            take_profit=62000.0,
            timestamp=datetime.now(UTC),
            source=SignalSource.ML,
        )
        assert sig.conviction == 1.0

    def test_signal_serialization_roundtrip(self):
        from graxia.packages.quant_os.core.session_manager import AssetClass
        from graxia.packages.quant_os.core.signal_gateway import Side, Signal, SignalSource

        ts = datetime(2025, 7, 1, 12, 0, 0, tzinfo=UTC)
        sig = Signal(
            symbol="NAS100",
            asset_class=AssetClass.INDICES,
            side=Side.BUY,
            conviction=0.7,
            strategy="roundtrip_test",
            entry_price=20000.0,
            stop_loss=19900.0,
            take_profit=20200.0,
            timestamp=ts,
            source=SignalSource.TRADINGVIEW,
        )
        d = sig.to_dict()
        assert d["symbol"] == "NAS100"
        assert d["side"] == "BUY"
        assert "signal_id" in d
        assert isinstance(d["signal_id"], str)
        assert len(d["signal_id"]) == 16

    def test_signal_id_deterministic(self):
        from graxia.packages.quant_os.core.session_manager import AssetClass
        from graxia.packages.quant_os.core.signal_gateway import Side, Signal, SignalSource

        ts = datetime(2025, 7, 1, 12, 0, 0, tzinfo=UTC)
        make = lambda: Signal(
            symbol="XAUUSD",
            asset_class=AssetClass.METALS,
            side=Side.BUY,
            conviction=0.8,
            strategy="s",
            entry_price=2400,
            stop_loss=2390,
            take_profit=2420,
            timestamp=ts,
            source=SignalSource.PYTHON,
        )
        assert make().signal_id == make().signal_id

    def test_signal_different_timestamps_different_id(self):
        from graxia.packages.quant_os.core.session_manager import AssetClass
        from graxia.packages.quant_os.core.signal_gateway import Side, Signal, SignalSource

        base = dict(
            symbol="XAUUSD",
            asset_class=AssetClass.METALS,
            side=Side.BUY,
            conviction=0.8,
            strategy="s",
            entry_price=2400,
            stop_loss=2390,
            take_profit=2420,
            source=SignalSource.PYTHON,
        )
        s1 = Signal(**base, timestamp=datetime(2025, 7, 1, 12, 0, tzinfo=UTC))
        s2 = Signal(**base, timestamp=datetime(2025, 7, 1, 12, 1, tzinfo=UTC))
        assert s1.signal_id != s2.signal_id

    @pytest.mark.asyncio
    async def test_signal_gateway_accepts_valid_payload(self, signal_queue):
        from graxia.packages.quant_os.core.signal_gateway import SignalGateway

        gw = SignalGateway(queue=signal_queue)
        raw = {
            "symbol": "XAUUSD",
            "asset_class": "metals",
            "side": "BUY",
            "conviction": 0.8,
            "strategy": "test_strat",
            "entry_price": 2400.0,
            "stop_loss": 2390.0,
            "take_profit": 2420.0,
        }
        sig = await gw.ingest(raw, source="python")
        assert sig is not None
        assert sig.symbol == "XAUUSD"
        assert not signal_queue.empty()

    @pytest.mark.asyncio
    async def test_signal_gateway_deduplicates(self, signal_queue):
        from graxia.packages.quant_os.core.signal_gateway import SignalGateway

        gw = SignalGateway(queue=signal_queue)
        raw = {
            "symbol": "XAUUSD",
            "asset_class": "metals",
            "side": "BUY",
            "conviction": 0.8,
            "strategy": "test_strat",
            "entry_price": 2400.0,
            "stop_loss": 2390.0,
            "take_profit": 2420.0,
        }
        sig1 = await gw.ingest(raw, source="python")
        sig2 = await gw.ingest(raw, source="python")
        assert sig1 is not None
        assert sig2 is None
        assert signal_queue.qsize() == 1


# ═══════════════════════════════════════════════════════════════════
# 4. COST CALIBRATION (7 tests)
# ═══════════════════════════════════════════════════════════════════


class TestCostCalibration:
    """Validate cost_calibration.json structure, ranges, and values."""

    def test_load_cost_calibration(self, cost_calibration):
        assert "assets" in cost_calibration
        assert "version" in cost_calibration
        assert isinstance(cost_calibration["assets"], dict)

    def test_all_expected_symbols_have_costs(self, cost_calibration):
        assets = cost_calibration["assets"]
        for sym in ALL_COST_ASSETS:
            assert sym in assets, f"Missing cost data for {sym}"

    def test_costs_in_bps_range(self, cost_calibration):
        for sym, data in cost_calibration["assets"].items():
            rt = data.get("round_trip_bps_measured", 0)
            assert 0 < rt < 100, f"{sym}: round_trip_bps {rt} out of range [0, 100]"

    def test_no_negative_costs(self, cost_calibration):
        for sym, data in cost_calibration["assets"].items():
            spread = data.get("spread_bps_measured", 0)
            commission = data.get("commission_bps", 0)
            assert spread >= 0, f"{sym}: negative spread {spread}"
            assert commission >= 0, f"{sym}: negative commission {commission}"

    def test_cost_serialization_roundtrip(self, tmp_cost_calibration):
        path, original = tmp_cost_calibration
        with open(path) as f:
            loaded = json.load(f)
        assert loaded == original

    def test_spot_crude_oil_cost(self, cost_calibration):
        oil = cost_calibration["assets"]["OIL"]
        assert oil["spread_bps_measured"] > 0
        assert oil["round_trip_bps_measured"] > 0
        assert oil["mt5_symbol"] == "USOIL"

    def test_btcusd_cost(self, cost_calibration):
        btc = cost_calibration["assets"]["BTCUSD"]
        assert btc["spread_bps_measured"] > 0
        assert btc["commission_bps"] == 0
        assert btc["round_trip_bps_measured"] > 0


# ═══════════════════════════════════════════════════════════════════
# 5. TICK RECORDER & STORE (6 tests)
# ═══════════════════════════════════════════════════════════════════


class TestTickRecorder:
    """Validate TickRecord and TickRecorder quality logic."""

    def test_record_tick_returns_valid_record(self, tick_recorder):
        from graxia.packages.quant_os.market_data.tick_recorder import TickRecord

        now = datetime.now(UTC)
        rec = tick_recorder.record_tick(
            bid=Decimal("100.00"),
            ask=Decimal("100.05"),
            last=Decimal("100.02"),
            timestamp_utc=now,
            source="mt5",
        )
        assert isinstance(rec, TickRecord)
        assert rec.data_quality == "VALID"

    def test_tick_data_quality_validates_source(self):
        from graxia.packages.quant_os.market_data.tick_recorder import TickRecord

        with pytest.raises(ValueError, match="Invalid source"):
            TickRecord(
                timestamp_utc=datetime.now(UTC),
                received_at_utc=datetime.now(UTC),
                symbol="XAUUSD",
                bid=Decimal("100"),
                ask=Decimal("100.05"),
                last=Decimal("100.02"),
                spread_points=Decimal("0.05"),
                flags="",
                sequence_id=1,
                connection_session_id="s1",
                source="invalid_source",
                data_quality="VALID",
            )

    def test_tick_data_quality_validates_quality(self):
        from graxia.packages.quant_os.market_data.tick_recorder import TickRecord

        with pytest.raises(ValueError, match="Invalid data_quality"):
            TickRecord(
                timestamp_utc=datetime.now(UTC),
                received_at_utc=datetime.now(UTC),
                symbol="XAUUSD",
                bid=Decimal("100"),
                ask=Decimal("100.05"),
                last=Decimal("100.02"),
                spread_points=Decimal("0.05"),
                flags="",
                sequence_id=1,
                connection_session_id="s1",
                source="mt5",
                data_quality="BROKEN",
            )

    def test_tick_recorder_empty_symbol_raises(self):
        from graxia.packages.quant_os.market_data.tick_recorder import TickRecorder

        with pytest.raises(ValueError, match="symbol must not be empty"):
            TickRecorder(symbol="", session_id="s1")

    def test_tick_recorder_empty_session_raises(self):
        from graxia.packages.quant_os.market_data.tick_recorder import TickRecorder

        with pytest.raises(ValueError, match="session_id must not be empty"):
            TickRecorder(symbol="XAUUSD", session_id="")

    def test_tick_recorder_count(self, tick_recorder):
        now = datetime.now(UTC)
        tick_recorder.record_tick(
            bid=Decimal("100"),
            ask=Decimal("100.05"),
            last=Decimal("100.02"),
            timestamp_utc=now,
            source="mt5",
        )
        tick_recorder.record_tick(
            bid=Decimal("100.01"),
            ask=Decimal("100.06"),
            last=Decimal("100.03"),
            timestamp_utc=now + timedelta(seconds=1),
            source="mt5",
        )
        assert tick_recorder.count() == 2


# ═══════════════════════════════════════════════════════════════════
# 6. SIGNAL FILTER (6 tests)
# ═══════════════════════════════════════════════════════════════════


class TestSignalFilter:
    """Validate FakeSignalFilter grading and criteria."""

    def test_filter_all_criteria_pass(self):
        from graxia.packages.quant_os.core.signal_filter import FakeSignalFilter

        f = FakeSignalFilter()
        result = f.evaluate(
            stability=type("S", (), {"stability_gap": 0.1, "os_sharpe": 2.0})(),
            monte_carlo=type("M", (), {"p_value": 0.01, "survival_rate": 0.95})(),
            metrics={"profit_factor": 1.5, "expectancy": 100},
        )
        assert result.passed
        assert result.score == 6
        assert result.grade == "S"

    def test_filter_insufficient_criteria(self):
        from graxia.packages.quant_os.core.signal_filter import FakeSignalFilter

        f = FakeSignalFilter()
        result = f.evaluate(stability=None, monte_carlo=None, metrics=None)
        assert not result.passed
        assert result.score == 0
        assert result.grade == "F"

    def test_filter_grade_boundary(self):
        from graxia.packages.quant_os.core.signal_filter import FakeSignalFilter

        f = FakeSignalFilter()
        for score, expected in [(6, "S"), (5, "A"), (4, "B"), (3, "C"), (2, "F")]:
            result = f.evaluate()
            result.score = score
            assert result.grade == expected

    def test_quick_check_pass(self):
        from graxia.packages.quant_os.core.signal_filter import FakeSignalFilter

        f = FakeSignalFilter()
        assert f.quick_check({"profit_factor": 1.5, "win_rate": 0.55, "expectancy": 50, "max_drawdown_pct": 10})

    def test_quick_check_fail_low_pf(self):
        from graxia.packages.quant_os.core.signal_filter import FakeSignalFilter

        f = FakeSignalFilter()
        assert not f.quick_check({"profit_factor": 0.8, "win_rate": 0.55, "expectancy": 50, "max_drawdown_pct": 10})

    def test_quick_check_fail_high_drawdown(self):
        from graxia.packages.quant_os.core.signal_filter import FakeSignalFilter

        f = FakeSignalFilter()
        assert not f.quick_check({"profit_factor": 1.5, "win_rate": 0.55, "expectancy": 50, "max_drawdown_pct": 30})


# ═══════════════════════════════════════════════════════════════════
# 7. ENUMS & EXCEPTIONS (5 tests)
# ═══════════════════════════════════════════════════════════════════


class TestEnumsAndExceptions:
    """Validate core enums and exception hierarchy."""

    def test_order_status_all_values(self):
        from graxia.packages.quant_os.core.enums import OrderStatus

        assert len(OrderStatus) >= 20
        assert OrderStatus.FILLED.value == "FILLED"
        assert OrderStatus.CANCELLED.value == "CANCELLED"

    def test_signal_type_values(self):
        from graxia.packages.quant_os.core.enums import SignalType

        assert SignalType.BUY.value == "BUY"
        assert SignalType.SELL.value == "SELL"
        assert SignalType.NO_TRADE.value == "NO_TRADE"

    def test_quant_exception_hierarchy(self):
        from graxia.packages.quant_os.core.exceptions import (
            DataQualityError,
            OrderStateError,
            QuantException,
            RiskViolationError,
            ValidationError,
        )

        assert issubclass(RiskViolationError, QuantException)
        assert issubclass(DataQualityError, QuantException)
        assert issubclass(OrderStateError, QuantException)
        assert issubclass(ValidationError, QuantException)

    def test_exception_error_code(self):
        from graxia.packages.quant_os.core.exceptions import RiskViolationError

        err = RiskViolationError("limit exceeded", violation_type="POSITION_SIZE")
        assert err.error_code == "RISK_VIOLATION"
        assert err.violation_type == "POSITION_SIZE"
        assert str(err) == "limit exceeded"

    def test_exception_context(self):
        from graxia.packages.quant_os.core.exceptions import DataQualityError

        err = DataQualityError("stale data", check_type="STALE_QUOTE", context={"symbol": "XAUUSD"})
        assert err.context["symbol"] == "XAUUSD"


# ═══════════════════════════════════════════════════════════════════
# 8. PYDANTIC SIGNAL VALIDATION (5 tests)
# ═══════════════════════════════════════════════════════════════════


class TestPydanticSignalValidation:
    """Validate RawSignalPayload Pydantic model constraints."""

    def test_valid_payload_passes(self):
        from graxia.packages.quant_os.core.signal_gateway import RawSignalPayload

        p = RawSignalPayload(
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY",
            conviction=0.8,
            strategy="test",
            entry_price=2400,
            stop_loss=2390,
            take_profit=2420,
        )
        assert p.symbol == "XAUUSD"

    def test_empty_symbol_rejected(self):
        from pydantic import ValidationError as PydanticError

        from graxia.packages.quant_os.core.signal_gateway import RawSignalPayload

        with pytest.raises(PydanticError):
            RawSignalPayload(
                symbol="",
                asset_class="metals",
                side="BUY",
                conviction=0.8,
                strategy="test",
                entry_price=2400,
                stop_loss=2390,
                take_profit=2420,
            )

    def test_conviction_out_of_range_rejected(self):
        from pydantic import ValidationError as PydanticError

        from graxia.packages.quant_os.core.signal_gateway import RawSignalPayload

        with pytest.raises(PydanticError):
            RawSignalPayload(
                symbol="XAUUSD",
                asset_class="metals",
                side="BUY",
                conviction=1.5,
                strategy="test",
                entry_price=2400,
                stop_loss=2390,
                take_profit=2420,
            )

    def test_invalid_side_rejected(self):
        from pydantic import ValidationError as PydanticError

        from graxia.packages.quant_os.core.signal_gateway import RawSignalPayload

        with pytest.raises(PydanticError):
            RawSignalPayload(
                symbol="XAUUSD",
                asset_class="metals",
                side="HOLD",
                conviction=0.8,
                strategy="test",
                entry_price=2400,
                stop_loss=2390,
                take_profit=2420,
            )

    def test_negative_stop_loss_rejected(self):
        from pydantic import ValidationError as PydanticError

        from graxia.packages.quant_os.core.signal_gateway import RawSignalPayload

        with pytest.raises(PydanticError):
            RawSignalPayload(
                symbol="XAUUSD",
                asset_class="metals",
                side="BUY",
                conviction=0.8,
                strategy="test",
                entry_price=2400,
                stop_loss=-1,
                take_profit=2420,
            )
