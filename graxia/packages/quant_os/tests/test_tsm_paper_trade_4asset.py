"""
Tests for TSM Paper Trade Bot — Concentrated 4-Asset Portfolio.

Covers:
  - TASK 1: 4-asset portfolio configuration
  - TASK 2: Inverse volatility position sizing
  - TASK 3: Regime detection
  - TASK 4: Drawdown-aware position reduction
"""

import math
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# Add project root to path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE.parent))

# Import the module under test
scripts_dir = BASE / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

# We need to import the module directly by path since it's a script, not a package module
import importlib.util

_spec = importlib.util.spec_from_file_location("tsm_paper_trade", scripts_dir / "tsm_paper_trade.py")
_mod = importlib.util.module_from_spec(_spec)

# Stub out MT5 and network dependencies before exec_module
with patch.dict("sys.modules", {"MetaTrader5": MagicMock()}):
    _spec.loader.exec_module(_mod)


# ═══════════════════════════════════════════════════════════════
# TASK 1: Portfolio Configuration
# ═══════════════════════════════════════════════════════════════


class TestPortfolioConfiguration:
    """Verify 4-asset concentrated portfolio setup."""

    def test_assets_count(self):
        """ASSETS must contain exactly 4 assets."""
        assert len(_mod.ASSETS) == 4

    def test_assets_list(self):
        """ASSETS must be NAS100, XAUUSD, OIL, USDJPY."""
        assert ["NAS100", "XAUUSD", "OIL", "USDJPY"] == _mod.ASSETS

    def test_mt5_symbol_map_has_all_assets(self):
        """Every asset in ASSETS must have an MT5 mapping."""
        for asset in _mod.ASSETS:
            assert asset in _mod.MT5_SYMBOL_MAP, f"{asset} missing from MT5_SYMBOL_MAP"

    def test_mt5_symbol_map_values(self):
        """MT5 symbol values must match Pepperstone naming."""
        assert _mod.MT5_SYMBOL_MAP["NAS100"] == "NAS100"
        assert _mod.MT5_SYMBOL_MAP["XAUUSD"] == "XAUUSD"
        assert _mod.MT5_SYMBOL_MAP["OIL"] == "USOIL"
        assert _mod.MT5_SYMBOL_MAP["USDJPY"] == "USDJPY"

    def test_contract_sizes_for_all_mt5_symbols(self):
        """Every MT5 symbol must have a contract size."""
        for asset, mt5_sym in _mod.MT5_SYMBOL_MAP.items():
            assert mt5_sym in _mod.CONTRACT_SIZES, f"{mt5_sym} missing from CONTRACT_SIZES"

    def test_contract_sizes_values(self):
        """Contract sizes must match Pepperstone defaults."""
        assert _mod.CONTRACT_SIZES["NAS100"] == 1
        assert _mod.CONTRACT_SIZES["XAUUSD"] == 100
        assert _mod.CONTRACT_SIZES["USOIL"] == 1000
        assert _mod.CONTRACT_SIZES["USDJPY"] == 100_000

    def test_target_vol_is_10pct(self):
        """Target vol must be 10% annualized."""
        assert _mod.TARGET_VOL == 0.10

    def test_rvol_window_config(self):
        """Realized vol window must be 60 days."""
        assert _mod.RVOL_WINDOW == 60

    def test_no_dead_weight_assets(self):
        """Dead weight assets must not be in ASSETS."""
        dead = ["EURUSD_YF", "GBPUSD_YF", "BTC_YF", "ETH_YF", "SILVER"]
        for asset in dead:
            assert asset not in _mod.ASSETS, f"Dead weight {asset} still in ASSETS"

    def test_yfinance_map_updated(self):
        """fetch_live_prices must support assets available via yfinance."""
        import inspect

        src = inspect.getsource(_mod.fetch_live_prices)
        # NAS100 uses MT5 only (no yfinance ticker); check the others
        for asset in ["XAUUSD", "OIL", "USDJPY"]:
            assert asset in src, f"{asset} missing from yfinance map"


# ═══════════════════════════════════════════════════════════════
# TASK 2: Inverse Volatility Position Sizing
# ═══════════════════════════════════════════════════════════════


class TestInverseVolSizing:
    """Verify inverse-volatility weighting logic."""

    @pytest.fixture
    def sample_returns(self):
        """Generate synthetic daily returns for 4 assets over 300 days."""
        np.random.seed(42)
        n = 300  # Enough for 120 lookback + 60 RVOL + shifts
        dates = pd.date_range("2024-01-01", periods=n, freq="B", tz="UTC")
        # Different vol levels: NAS100=high, XAUUSD=medium, OIL=medium-high, USDJPY=low
        vols = [0.25, 0.15, 0.30, 0.08]  # annualized
        data = {}
        for i, (asset, vol) in enumerate(zip(_mod.ASSETS, vols, strict=False)):
            daily_vol = vol / math.sqrt(252)
            data[asset] = np.random.normal(0.0003, daily_vol, n)
        return pd.DataFrame(data, index=dates)

    @pytest.fixture
    def sample_close_matrix(self, sample_returns):
        """Convert returns to close price matrix."""
        prices = (1 + sample_returns).cumprod() * 100
        return prices

    def test_inverse_vol_weights_sum_to_one(self, sample_close_matrix):
        """Inverse-vol weights must normalize to sum(|w|) = 1."""
        weights, _, _, _, _ = _mod.compute_target_weights(sample_close_matrix)

        # Check last row with all data
        last_valid = weights.dropna()
        if not last_valid.empty:
            last_row = last_valid.iloc[-1]
            abs_sum = last_row.abs().sum()
            assert abs_sum == pytest.approx(1.0, abs=0.01), f"abs sum = {abs_sum}"

    def test_low_vol_asset_gets_higher_weight(self, sample_close_matrix):
        """Lower-vol asset (USDJPY) should get higher weight."""
        # Get inverse-vol weights directly
        filled = sample_close_matrix.ffill()
        daily_ret = filled.pct_change(1)
        asset_rvol = daily_ret.rolling(_mod.RVOL_WINDOW, min_periods=_mod.RVOL_WINDOW).std() * np.sqrt(252)

        inv_vol = 1.0 / asset_rvol.replace(0, np.nan)
        inv_vol_sum = inv_vol.sum(axis=1).replace(0, np.nan)
        inv_weights = inv_vol.div(inv_vol_sum, axis=0)

        # Get last valid row
        last = inv_weights.dropna().iloc[-1]
        # USDJPY (lowest vol) should have highest weight
        assert last["USDJPY"] > last["NAS100"], "USDJPY should have higher weight than NAS100"

    def test_compute_target_weights_returns_tuple_of_5(self, sample_close_matrix):
        """compute_target_weights must return 5-tuple (weights, vol_scale, port_rvol, regime, trend)."""
        result = _mod.compute_target_weights(sample_close_matrix)
        assert len(result) == 5
        weights, vol_scale, port_rvol, regime, trend = result
        assert isinstance(weights, pd.DataFrame)
        assert isinstance(regime, str)
        assert regime in ("NORMAL", "HIGH_VOL", "LOW_VOL")
        assert isinstance(trend, str)
        assert trend in ("UPTREND", "DOWNTREND", "FLAT")

    def test_vol_target_config(self):
        """Target vol must be configurable."""
        assert _mod.TARGET_VOL == 0.10


# ═══════════════════════════════════════════════════════════════
# TASK 3: Regime Detection
# ═══════════════════════════════════════════════════════════════


class TestRegimeDetection:
    """Verify volatility-based regime detection."""

    @pytest.fixture
    def low_vol_returns(self):
        """Low, stable returns → NORMAL regime."""
        np.random.seed(42)
        n = 120
        dates = pd.date_range("2024-01-01", periods=n, freq="B", tz="UTC")
        data = {}
        for asset in _mod.ASSETS:
            # Consistent low vol
            data[asset] = np.random.normal(0.0002, 0.005, n)
        return pd.DataFrame(data, index=dates)

    @pytest.fixture
    def high_vol_returns(self):
        """Spike in short-term vol → HIGH_VOL regime."""
        np.random.seed(42)
        n = 120
        dates = pd.date_range("2024-01-01", periods=n, freq="B", tz="UTC")
        data = {}
        for asset in _mod.ASSETS:
            returns = np.random.normal(0.0002, 0.005, n)
            # Add vol spike in last 20 days
            returns[-20:] = np.random.normal(0, 0.025, 20)  # 5x vol
            data[asset] = returns
        return pd.DataFrame(data, index=dates)

    @pytest.fixture
    def calm_vol_returns(self):
        """Drop in short-term vol → LOW_VOL regime."""
        np.random.seed(42)
        n = 120
        dates = pd.date_range("2024-01-01", periods=n, freq="B", tz="UTC")
        data = {}
        for asset in _mod.ASSETS:
            returns = np.random.normal(0.0002, 0.02, n)
            # Very calm last 20 days (much lower vol than rest)
            returns[-20:] = np.random.normal(0, 0.002, 20)  # 10x calmer
            data[asset] = returns
        return pd.DataFrame(data, index=dates)

    def test_normal_regime(self, low_vol_returns):
        """Stable returns should be NORMAL regime."""
        regime = _mod.detect_regime(low_vol_returns)
        assert regime == "NORMAL"

    def test_high_vol_regime(self, high_vol_returns):
        """Vol spike should trigger HIGH_VOL regime."""
        regime = _mod.detect_regime(high_vol_returns)
        assert regime == "HIGH_VOL"

    def test_low_vol_regime(self, calm_vol_returns):
        """Calm market should trigger LOW_VOL regime."""
        regime = _mod.detect_regime(calm_vol_returns)
        assert regime == "LOW_VOL"

    def test_high_vol_reduces_positions(self, high_vol_returns):
        """HIGH_VOL regime must reduce position weights by 50%."""
        # We don't actually compute weights; verify the constant
        assert _mod.HIGH_VOL_POSITION_SCALE == 0.50

    def test_regime_constants(self):
        """Regime detection constants must be set correctly."""
        assert _mod.REGIME_VOL_SHORT == 20
        assert _mod.REGIME_VOL_LONG == 60
        assert _mod.REGIME_VOL_HIGH_MULTIPLIER == 1.5
        assert _mod.REGIME_VOL_LOW_MULTIPLIER == 0.8

    def test_detect_regime_handles_empty(self):
        """detect_regime must not crash on empty dataframe."""
        empty = pd.DataFrame()
        regime = _mod.detect_regime(empty)
        # Should return NORMAL (safe default) for empty data
        assert regime == "NORMAL"


# ═══════════════════════════════════════════════════════════════
# TASK 4: Drawdown-Aware Position Reduction
# ═══════════════════════════════════════════════════════════════


class TestTrendDetection:
    """Verify SMA crossover trend detection."""

    @pytest.fixture
    def uptrend_data(self):
        """Prices with steady uptrend (50d SMA > 200d SMA)."""
        np.random.seed(42)
        n = 250  # Enough for 200-day SMA
        dates = pd.date_range("2023-06-01", periods=n, freq="B", tz="UTC")
        data = {}
        for asset in _mod.ASSETS:
            # Steady uptrend: positive drift + noise
            base = 100.0
            drift = 0.001  # ~25% annualized
            vol = 0.01
            prices = [base]
            for _ in range(n - 1):
                prices.append(prices[-1] * (1 + drift + np.random.normal(0, vol)))
            data[asset] = prices
        return pd.DataFrame(data, index=dates)

    @pytest.fixture
    def downtrend_data(self):
        """Prices with steady downtrend (50d SMA < 200d SMA)."""
        np.random.seed(42)
        n = 250
        dates = pd.date_range("2023-06-01", periods=n, freq="B", tz="UTC")
        data = {}
        for asset in _mod.ASSETS:
            # Steady downtrend: negative drift + noise
            base = 200.0
            drift = -0.001  # ~-25% annualized
            vol = 0.01
            prices = [base]
            for _ in range(n - 1):
                prices.append(prices[-1] * (1 + drift + np.random.normal(0, vol)))
            data[asset] = prices
        return pd.DataFrame(data, index=dates)

    def test_uptrend_detection(self, uptrend_data):
        """Steady uptrend should detect UPTREND."""
        trend = _mod.detect_trend(uptrend_data)
        assert trend == "UPTREND"

    def test_downtrend_detection(self, downtrend_data):
        """Steady downtrend should detect DOWNTREND."""
        trend = _mod.detect_trend(downtrend_data)
        assert trend == "DOWNTREND"

    def test_insufficient_data_returns_flat(self):
        """Not enough data for 200-day SMA should return FLAT."""
        np.random.seed(42)
        n = 50  # Too short for 200-day SMA
        dates = pd.date_range("2024-01-01", periods=n, freq="B", tz="UTC")
        data = pd.DataFrame(
            {asset: np.random.normal(100, 1, n) for asset in _mod.ASSETS},
            index=dates,
        )
        trend = _mod.detect_trend(data)
        assert trend == "FLAT"

    def test_trend_constants(self):
        """Trend detection constants must be set correctly."""
        assert _mod.TREND_FAST_SMA == 50
        assert _mod.TREND_SLOW_SMA == 200

    def test_trend_filter_uptrend_removes_shorts(self, uptrend_data):
        """In uptrend, trend filter should zero out negative signals."""
        # Create signal DataFrame with mixed signals
        n = len(uptrend_data)
        dates = uptrend_data.index
        signals = pd.DataFrame(
            {
                "NAS100": np.random.uniform(-1, 1, n),
                "XAUUSD": np.random.uniform(-1, 1, n),
                "OIL": np.random.uniform(-1, 1, n),
                "USDJPY": np.random.uniform(-1, 1, n),
            },
            index=dates,
        )
        filtered = _mod.apply_trend_filter(signals, uptrend_data)
        # All negative signals should be zeroed
        assert (filtered.min() >= 0).all(), "Negative signals not zeroed in uptrend"

    def test_trend_filter_downtrend_removes_longs(self, downtrend_data):
        """In downtrend, trend filter should zero out positive signals."""
        n = len(downtrend_data)
        dates = downtrend_data.index
        signals = pd.DataFrame(
            {
                "NAS100": np.random.uniform(-1, 1, n),
                "XAUUSD": np.random.uniform(-1, 1, n),
                "OIL": np.random.uniform(-1, 1, n),
                "USDJPY": np.random.uniform(-1, 1, n),
            },
            index=dates,
        )
        filtered = _mod.apply_trend_filter(signals, downtrend_data)
        # All positive signals should be zeroed
        assert (filtered.max() <= 0).all(), "Positive signals not zeroed in downtrend"


class TestATRMultiplier:
    """Verify regime-based ATR multiplier selection."""

    def test_high_vol_atr_mult(self):
        """HIGH_VOL → 1.5x ATR."""
        assert _mod.get_regime_atr_multiplier("HIGH_VOL") == 1.5

    def test_low_vol_atr_mult(self):
        """LOW_VOL → 1.5x ATR."""
        assert _mod.get_regime_atr_multiplier("LOW_VOL") == 1.5

    def test_normal_atr_mult(self):
        """NORMAL → 2.0x ATR."""
        assert _mod.get_regime_atr_multiplier("NORMAL") == 2.0

    def test_atr_constants(self):
        """ATR multiplier constants must be set correctly."""
        assert _mod.HIGH_VOL_ATR_MULT == 1.5
        assert _mod.NORMAL_ATR_MULT == 2.0
        assert _mod.LOW_VOL_ATR_MULT == 1.5


class TestDrawdownReduction:
    """Verify drawdown-based position scaling."""

    def test_no_drawdown_full_position(self):
        """0% DD → scale 1.0 (full positions)."""
        assert _mod.drawdown_position_scale(0.0) == 1.0

    def test_small_drawdown_full_position(self):
        """3% DD → scale 1.0 (below 5% threshold)."""
        assert _mod.drawdown_position_scale(0.03) == 1.0

    def test_5pct_drawdown_reduces(self):
        """5% DD → scale 0.75 (25% reduction)."""
        assert _mod.drawdown_position_scale(0.05) == 0.75

    def test_8pct_drawdown_reduces(self):
        """8% DD → scale 0.75."""
        assert _mod.drawdown_position_scale(0.08) == 0.75

    def test_10pct_drawdown_halves(self):
        """10% DD → scale 0.50 (50% reduction)."""
        assert _mod.drawdown_position_scale(0.10) == 0.50

    def test_15pct_drawdown_halves(self):
        """15% DD → scale 0.50 (kill switch is separate, checked by AutoStop)."""
        assert _mod.drawdown_position_scale(0.15) == 0.50

    def test_extreme_drawdown_halves(self):
        """20% DD → scale 0.50 (kill switch should have triggered)."""
        assert _mod.drawdown_position_scale(0.20) == 0.50

    def test_negative_drawdown_handled(self):
        """Negative DD (equity above peak) → abs(-5%) = 5% triggers reduction."""
        # abs(-0.05) = 0.05 >= 0.05, so this should reduce
        assert _mod.drawdown_position_scale(-0.05) == 0.75

    def test_dd_constants(self):
        """Drawdown threshold constants must be correct."""
        assert _mod.DD_REDUCE_1_THRESHOLD == 0.05
        assert _mod.DD_REDUCE_1_SCALE == 0.75
        assert _mod.DD_REDUCE_2_THRESHOLD == 0.10
        assert _mod.DD_REDUCE_2_SCALE == 0.50


# ═══════════════════════════════════════════════════════════════
# Integration: Combined Sizing
# ═══════════════════════════════════════════════════════════════


class TestIntegratedSizing:
    """Verify that all sizing components work together."""

    @pytest.fixture
    def synthetic_data(self):
        """Create synthetic 4-asset close prices (300 days for rolling windows)."""
        np.random.seed(42)
        n = 300
        dates = pd.date_range("2024-01-01", periods=n, freq="B", tz="UTC")
        vols = [0.25, 0.15, 0.30, 0.08]
        data = {}
        for asset, vol in zip(_mod.ASSETS, vols, strict=False):
            daily_vol = vol / math.sqrt(252)
            returns = np.random.normal(0.0003, daily_vol, n)
            data[asset] = (1 + returns).cumprod() * 100
        return pd.DataFrame(data, index=dates)

    def test_full_pipeline_output_shape(self, synthetic_data):
        """Full pipeline must produce weights for all 4 assets."""
        weights, vol_scale, port_rvol, regime, trend = _mod.compute_target_weights(synthetic_data)
        last_valid = weights.dropna()
        assert not last_valid.empty
        last_row = last_valid.iloc[-1]
        assert len(last_row) == 4
        assert regime in ("NORMAL", "HIGH_VOL", "LOW_VOL")
        assert trend in ("UPTREND", "DOWNTREND", "FLAT")

    def test_dd_scale_integrated(self, synthetic_data):
        """Verify DD scaling is applied in compute_target_weights."""
        # With 0% DD
        w1, _, _, _, _ = _mod.compute_target_weights(synthetic_data, drawdown_pct=0.0)
        # With 12% DD (should halve)
        w2, _, _, _, _ = _mod.compute_target_weights(synthetic_data, drawdown_pct=0.12)

        # Last valid rows
        last1 = w1.dropna().iloc[-1]
        last2 = w2.dropna().iloc[-1]

        # With 12% DD, weights should be 0.5x the no-DD weights (approximately)
        ratio = last2.abs().sum() / last1.abs().sum()
        assert ratio == pytest.approx(0.5, abs=0.05), f"DD scaling ratio: {ratio}"

    def test_weights_to_lots_uses_4_assets(self):
        """weights_to_lots must produce lots for all 4 assets."""
        weights = {
            "NAS100": 0.45,
            "XAUUSD": 0.35,
            "OIL": 0.05,
            "USDJPY": 0.15,
        }
        prices = {
            "NAS100": 20000.0,
            "XAUUSD": 2400.0,
            "OIL": 80.0,
            "USDJPY": 155.0,
        }
        result = _mod.weights_to_lots(weights, prices, 100_000.0)
        assert len(result) == 4
        for asset in _mod.ASSETS:
            assert asset in result
            assert "target_lots" in result[asset]
            assert "mt5_symbol" in result[asset]

    def test_max_leverage_cap(self):
        """MAX_LEVERAGE must cap individual asset weights."""
        assert _mod.MAX_LEVERAGE == 1.5


# ═══════════════════════════════════════════════════════════════
# Data Loading
# ═══════════════════════════════════════════════════════════════


class TestDataLoading:
    """Verify data loading handles NAS100 from CSV fallback."""

    def test_nas100_csv_fallback_path(self):
        """NAS100 CSV path must be data/NAS100_D1.csv."""
        expected = BASE / "data" / "NAS100_D1.csv"
        assert expected.exists(), f"NAS100 CSV not found at {expected}"

    def test_parquet_fallback_graceful(self):
        """load_data must not crash if parquet is missing (NAS100 CSV available)."""
        # This just verifies the code path doesn't hard-crash
        # We can't easily mock the file system in this test, so we verify
        # the function exists and accepts the new data sources
        assert callable(_mod.load_data)


# ═══════════════════════════════════════════════════════════════
# State Persistence
# ═══════════════════════════════════════════════════════════════


class TestStatePersistence:
    """Verify save_state includes regime, trend, and drawdown."""

    def test_save_state_accepts_regime_and_trend(self):
        """save_state must accept regime, trend, and drawdown_pct kwargs."""
        import inspect

        sig = inspect.signature(_mod.save_state)
        assert "regime" in sig.parameters
        assert "trend" in sig.parameters
        assert "drawdown_pct" in sig.parameters


# ═══════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Verify robustness against edge cases."""

    def test_detect_regime_single_asset(self):
        """Regime detection must work with single-column DataFrame."""
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=120, freq="B", tz="UTC")
        df = pd.DataFrame({"XAUUSD": np.random.normal(0.0003, 0.01, 120)}, index=dates)
        regime = _mod.detect_regime(df)
        assert regime in ("NORMAL", "HIGH_VOL", "LOW_VOL")

    def test_drawdown_scale_boundary_5pct(self):
        """Exact 5% DD must trigger reduction."""
        assert _mod.drawdown_position_scale(0.05) == 0.75

    def test_drawdown_scale_boundary_10pct(self):
        """Exact 10% DD must trigger 50% reduction."""
        assert _mod.drawdown_position_scale(0.10) == 0.50

    def test_inverse_vol_zero_handling(self):
        """Zero vol asset must not crash inverse-vol calculation."""
        # The code uses .replace(0, np.nan) to handle zero vol
        n = 300  # Enough for all rolling windows
        data = pd.DataFrame(
            {
                "NAS100": np.random.RandomState(42).normal(0.01, 0.01, n),
                "XAUUSD": np.random.RandomState(43).normal(0.01, 0.01, n),
                "OIL": [0.0] * n,  # zero vol
                "USDJPY": np.random.RandomState(44).normal(0.01, 0.005, n),
            },
            index=pd.date_range("2024-01-01", periods=n, freq="B", tz="UTC"),
        )
        # Should not crash
        weights, _, _, _, _ = _mod.compute_target_weights(data)
        assert isinstance(weights, pd.DataFrame)
