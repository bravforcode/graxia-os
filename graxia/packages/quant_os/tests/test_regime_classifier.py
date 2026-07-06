"""Tests for 4-class regime classifier (Stage 2: Regime Gate)."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Import by file path to avoid broken ml.__init__.py pipeline import
_root = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "ml.regime_classifier", str(_root / "ml" / "regime_classifier.py")
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

RegimeType = _mod.RegimeType
RegimeResult = _mod.RegimeResult
REGIME_SCALE = _mod.REGIME_SCALE
RegimeClassifier = _mod.RegimeClassifier


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_trending_data(n: int = 400, trend: float = 0.001, vol: float = 0.01, seed: int = 42):
    """Generate synthetic price series with configurable trend and vol."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(trend, vol, n)
    prices = 100 * np.exp(np.cumsum(returns))
    idx = pd.bdate_range("2023-01-01", periods=n)
    return pd.Series(prices, index=idx, name="close")


def _make_high_vol_data(n: int = 400, seed: int = 42):
    """High volatility bearish data."""
    return _make_trending_data(n, trend=-0.002, vol=0.04, seed=seed)


def _make_low_vol_bull(n: int = 400, seed: int = 42):
    """Low volatility bullish data."""
    return _make_trending_data(n, trend=0.001, vol=0.005, seed=seed)


def _make_flat_data(n: int = 400, seed: int = 42):
    """Flat / choppy data."""
    return _make_trending_data(n, trend=0.0, vol=0.015, seed=seed)


# ---------------------------------------------------------------------------
# RegimeType enum
# ---------------------------------------------------------------------------


class TestRegimeType:
    def test_values(self):
        assert RegimeType.CALM_BULL.value == "calm_bull"
        assert RegimeType.VOLATILE_BULL.value == "volatile_bull"
        assert RegimeType.CALM_BEAR.value == "calm_bear"
        assert RegimeType.VOLATILE_BEAR.value == "volatile_bear"

    def test_four_members(self):
        assert len(RegimeType) == 4


# ---------------------------------------------------------------------------
# REGIME_SCALE
# ---------------------------------------------------------------------------


class TestRegimeScale:
    def test_all_regimes_have_scale(self):
        for r in RegimeType:
            assert r in REGIME_SCALE

    def test_scales_in_range(self):
        for scale in REGIME_SCALE.values():
            assert 0.0 <= scale <= 1.5

    def test_calm_bull_is_max(self):
        assert REGIME_SCALE[RegimeType.CALM_BULL] == 1.5

    def test_volatile_bear_is_zero(self):
        assert REGIME_SCALE[RegimeType.VOLATILE_BEAR] == 0.0


# ---------------------------------------------------------------------------
# RegimeResult
# ---------------------------------------------------------------------------


class TestRegimeResult:
    def test_fields(self):
        r = RegimeResult(
            regime=RegimeType.CALM_BULL,
            confidence=0.8,
            position_scale=1.2,
            vol_regime="LOW",
            trend_regime="UP",
            features={"vol_percentile": 0.1},
        )
        assert r.regime == RegimeType.CALM_BULL
        assert r.confidence == 0.8
        assert r.position_scale == 1.2
        assert r.vol_regime == "LOW"
        assert r.trend_regime == "UP"


# ---------------------------------------------------------------------------
# RegimeClassifier.classify (single point)
# ---------------------------------------------------------------------------


class TestClassify:
    def test_calm_bull_detection(self):
        close = _make_low_vol_bull()
        clf = RegimeClassifier()
        result = clf.classify(close)
        assert isinstance(result, RegimeResult)
        # With low vol + uptrend, should be CALM_BULL or VOLATILE_BULL
        assert result.regime in (RegimeType.CALM_BULL, RegimeType.VOLATILE_BULL)

    def test_volatile_bear_detection(self):
        close = _make_high_vol_data()
        clf = RegimeClassifier()
        result = clf.classify(close)
        assert isinstance(result, RegimeResult)
        # With high vol + downtrend, should be VOLATILE_BEAR or CALM_BEAR
        assert result.regime in (RegimeType.VOLATILE_BEAR, RegimeType.CALM_BEAR)

    def test_position_scale_range(self):
        close = _make_trending_data()
        clf = RegimeClassifier()
        result = clf.classify(close)
        assert 0.0 <= result.position_scale <= 1.5

    def test_confidence_range(self):
        close = _make_trending_data()
        clf = RegimeClassifier()
        result = clf.classify(close)
        assert 0.0 <= result.confidence <= 1.0

    def test_vol_regime_values(self):
        close = _make_trending_data()
        clf = RegimeClassifier()
        result = clf.classify(close)
        assert result.vol_regime in ("LOW", "MED", "HIGH")

    def test_trend_regime_values(self):
        close = _make_trending_data()
        clf = RegimeClassifier()
        result = clf.classify(close)
        assert result.trend_regime in ("UP", "DOWN", "FLAT")

    def test_features_populated(self):
        close = _make_trending_data()
        clf = RegimeClassifier()
        result = clf.classify(close)
        assert "vol_percentile" in result.features
        assert "trend_strength" in result.features
        assert "realized_vol" in result.features
        assert "ema_short" in result.features
        assert "ema_long" in result.features

    def test_with_high_low(self):
        close = _make_trending_data()
        high = close * 1.01
        low = close * 0.99
        clf = RegimeClassifier()
        result = clf.classify(close, high=high, low=low)
        assert isinstance(result, RegimeResult)
        assert 0.0 <= result.position_scale <= 1.5

    def test_too_short_raises(self):
        close = pd.Series([100, 101, 102])
        clf = RegimeClassifier()
        with pytest.raises(ValueError, match="Need at least"):
            clf.classify(close)


# ---------------------------------------------------------------------------
# RegimeClassifier.classify_batch
# ---------------------------------------------------------------------------


class TestClassifyBatch:
    def test_returns_dataframe(self):
        close = _make_trending_data()
        clf = RegimeClassifier()
        df = clf.classify_batch(close)
        assert isinstance(df, pd.DataFrame)

    def test_batch_columns(self):
        close = _make_trending_data()
        clf = RegimeClassifier()
        df = clf.classify_batch(close)
        expected = {"timestamp", "regime", "confidence", "position_scale", "vol_regime", "trend_regime"}
        assert set(df.columns) == expected

    def test_batch_regime_values(self):
        close = _make_trending_data()
        clf = RegimeClassifier()
        df = clf.classify_batch(close)
        valid = {r.value for r in RegimeType}
        assert set(df["regime"].unique()).issubset(valid)

    def test_batch_scale_range(self):
        close = _make_trending_data()
        clf = RegimeClassifier()
        df = clf.classify_batch(close)
        assert df["position_scale"].between(0.0, 1.5).all()

    def test_batch_confidence_range(self):
        close = _make_trending_data()
        clf = RegimeClassifier()
        df = clf.classify_batch(close)
        assert df["confidence"].between(0.0, 1.0).all()

    def test_batch_nonempty(self):
        close = _make_trending_data(n=400)
        clf = RegimeClassifier()
        df = clf.classify_batch(close)
        assert len(df) > 0

    def test_batch_too_short_returns_empty(self):
        close = pd.Series([100, 101])
        clf = RegimeClassifier()
        df = clf.classify_batch(close)
        assert len(df) == 0

    def test_batch_with_high_low(self):
        close = _make_trending_data()
        high = close * 1.01
        low = close * 0.99
        clf = RegimeClassifier()
        df = clf.classify_batch(close, high=high, low=low)
        assert len(df) > 0
        assert df["position_scale"].between(0.0, 1.5).all()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_flat_market(self):
        close = _make_flat_data()
        clf = RegimeClassifier()
        result = clf.classify(close)
        assert isinstance(result, RegimeResult)
        assert 0.0 <= result.position_scale <= 1.5

    def test_extreme_vol(self):
        # Data with a vol spike: calm period then high vol period.
        # The spike should make vol_percentile > 0.67 = HIGH.
        rng = np.random.default_rng(42)
        calm = rng.normal(0.001, 0.005, 300)
        spike = rng.normal(-0.002, 0.06, 100)
        returns = np.concatenate([calm, spike])
        prices = 100 * np.exp(np.cumsum(returns))
        close = pd.Series(prices, index=pd.bdate_range("2023-01-01", periods=400))
        clf = RegimeClassifier()
        result = clf.classify(close)
        assert result.vol_regime == "HIGH"
        assert 0.0 <= result.position_scale <= 1.5

    def test_near_zero_vol(self):
        close = pd.Series(np.full(400, 100.0))
        close = close + np.random.default_rng(0).normal(0, 0.0001, 400)
        clf = RegimeClassifier()
        result = clf.classify(close)
        assert isinstance(result, RegimeResult)

    def test_custom_thresholds(self):
        close = _make_trending_data()
        clf = RegimeClassifier(
            vol_threshold_high=0.9,
            vol_threshold_low=0.1,
            trend_threshold=0.05,
        )
        result = clf.classify(close)
        assert isinstance(result, RegimeResult)

    def test_monotonic_up(self):
        close = pd.Series(np.linspace(100, 200, 400))
        clf = RegimeClassifier()
        result = clf.classify(close)
        assert result.trend_regime == "UP"

    def test_monotonic_down(self):
        close = pd.Series(np.linspace(200, 100, 400))
        clf = RegimeClassifier()
        result = clf.classify(close)
        assert result.trend_regime == "DOWN"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_input_same_output(self):
        close = _make_trending_data()
        clf = RegimeClassifier()
        r1 = clf.classify(close)
        r2 = clf.classify(close)
        assert r1.regime == r2.regime
        assert r1.position_scale == r2.position_scale
        assert r1.confidence == r2.confidence
