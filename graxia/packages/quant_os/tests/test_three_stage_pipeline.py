"""
Tests for 3-stage trading pipeline.
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Load dependencies by file path to avoid __init__.py import chains
# ---------------------------------------------------------------------------
_root = Path(__file__).resolve().parent.parent


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, str(_root / rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Stage 1 deps
_vol_mod = _load("core.volatility_features", "core/volatility_features.py")
_har_mod = _load("ml.har_model", "ml/har_model.py")

# Stage 2 dep
_regime_mod = _load("ml.regime_classifier", "ml/regime_classifier.py")

# Stage 3 deps (order matters: tsmom, carry, pairs_mr before factor_signals)
_tsmom_mod = _load("strategies.tsmom", "strategies/tsmom.py")
_carry_mod = _load("strategies.carry", "strategies/carry.py")
_pairs_mod = _load("strategies.pairs_mr", "strategies/pairs_mr.py")
_factor_mod = _load("strategies.factor_signals", "strategies/factor_signals.py")

# Pipeline
_pipe_mod = _load("strategies.three_stage_pipeline", "strategies/three_stage_pipeline.py")

PipelineResult = _pipe_mod.PipelineResult
ThreeStagePipeline = _pipe_mod.ThreeStagePipeline


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_ohlcv():
    """Generate synthetic OHLCV data with enough history for all stages."""
    np.random.seed(42)
    n = 500
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    close = 100 * np.exp(np.cumsum(np.random.randn(n) * 0.01))
    high = close * (1 + np.abs(np.random.randn(n) * 0.005))
    low = close * (1 - np.abs(np.random.randn(n) * 0.005))
    open_ = close * (1 + np.random.randn(n) * 0.002)
    volume = np.random.randint(1000, 10000, n).astype(float)

    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=dates)


@pytest.fixture
def flat_ohlcv():
    """Flat market — no price movement."""
    n = 500
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    close = pd.Series(100.0, index=dates)
    return pd.DataFrame({
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": pd.Series(1000.0, index=dates),
    })


@pytest.fixture
def pipeline():
    return ThreeStagePipeline(vol_target=0.10, capital=100_000, max_position_pct=0.20)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPipelineRuns:
    """Test 1: Pipeline runs without error."""

    def test_run_basic(self, pipeline, sample_ohlcv):
        result = pipeline.run(sample_ohlcv)
        assert isinstance(result, PipelineResult)

    def test_run_returns_all_fields(self, pipeline, sample_ohlcv):
        result = pipeline.run(sample_ohlcv)
        assert result.forecast_vol is not None
        assert result.realized_vol is not None
        assert result.regime is not None
        assert result.regime_scale is not None
        assert result.factor_signal is not None
        assert result.factor_confidence is not None
        assert result.position_size is not None
        assert result.position_side is not None
        assert result.vol_target is not None
        assert result.vol_ratio is not None


class TestStageOutputs:
    """Test 2: All 3 stages produce outputs."""

    def test_stage1_vol_positive(self, pipeline, sample_ohlcv):
        result = pipeline.run(sample_ohlcv)
        assert result.forecast_vol >= 0
        assert result.realized_vol >= 0

    def test_stage2_regime_valid(self, pipeline, sample_ohlcv):
        result = pipeline.run(sample_ohlcv)
        assert result.regime in ("calm_bull", "volatile_bull", "calm_bear", "volatile_bear")
        assert 0 <= result.regime_scale <= 1.5

    def test_stage3_signal_bounded(self, pipeline, sample_ohlcv):
        result = pipeline.run(sample_ohlcv)
        assert result.factor_signal in (-1, 0, 1)
        assert 0 <= result.factor_confidence <= 1


class TestPositionBounded:
    """Test 3: Position size is bounded."""

    def test_position_within_capital(self, pipeline, sample_ohlcv):
        result = pipeline.run(sample_ohlcv)
        max_pos = pipeline.capital * pipeline.max_position_pct
        assert result.position_size <= max_pos + 1e-6

    def test_position_non_negative(self, pipeline, sample_ohlcv):
        result = pipeline.run(sample_ohlcv)
        assert result.position_size >= 0


class TestPositionSide:
    """Test 4: Position side is LONG/SHORT/FLAT."""

    def test_side_valid(self, pipeline, sample_ohlcv):
        result = pipeline.run(sample_ohlcv)
        assert result.position_side in ("LONG", "SHORT", "FLAT")

    def test_long_sign_matches(self, pipeline, sample_ohlcv):
        result = pipeline.run(sample_ohlcv)
        if result.position_side == "LONG":
            assert result.factor_signal > 0
        elif result.position_side == "SHORT":
            assert result.factor_signal < 0
        elif result.position_side == "FLAT":
            assert result.factor_signal == 0 or result.position_size == 0


class TestVolRatioCapped:
    """Test 5: Vol ratio is capped at 2x."""

    def test_vol_ratio_cap(self, pipeline, sample_ohlcv):
        result = pipeline.run(sample_ohlcv)
        assert result.vol_ratio <= 2.0 + 1e-6

    def test_vol_ratio_positive(self, pipeline, sample_ohlcv):
        result = pipeline.run(sample_ohlcv)
        assert result.vol_ratio > 0


class TestWalkForward:
    """Test 6: Walk-forward produces results."""

    def test_walk_forward_returns_df(self, pipeline, sample_ohlcv):
        wf = pipeline.run_walk_forward(sample_ohlcv, train_pct=0.7)
        assert isinstance(wf, pd.DataFrame)
        assert len(wf) > 0

    def test_walk_forward_columns(self, pipeline, sample_ohlcv):
        wf = pipeline.run_walk_forward(sample_ohlcv, train_pct=0.7)
        expected_cols = {
            "timestamp", "regime", "regime_scale", "factor_signal",
            "position_size", "position_side", "forecast_vol",
            "realized_vol", "vol_ratio",
        }
        assert expected_cols.issubset(set(wf.columns))

    def test_walk_forward_regime_values(self, pipeline, sample_ohlcv):
        wf = pipeline.run_walk_forward(sample_ohlcv, train_pct=0.7)
        valid_regimes = {"calm_bull", "volatile_bull", "calm_bear", "volatile_bear"}
        assert set(wf["regime"].unique()).issubset(valid_regimes)


class TestEdgeCases:
    """Test 7: Edge cases."""

    def test_flat_market(self, pipeline, flat_ohlcv):
        result = pipeline.run(flat_ohlcv)
        assert result.position_side == "FLAT"
        assert result.position_size == 0

    def test_short_data_returns_normal(self):
        """Insufficient data should raise ValueError."""
        short_df = pd.DataFrame({
            "open": [100, 101, 102],
            "high": [101, 102, 103],
            "low": [99, 100, 101],
            "close": [100, 101, 102],
            "volume": [1000, 1000, 1000],
        })
        p = ThreeStagePipeline()
        with pytest.raises((ValueError, IndexError)):
            p.run(short_df)

    def test_zero_vol_target(self, sample_ohlcv):
        p = ThreeStagePipeline(vol_target=0.0)
        result = p.run(sample_ohlcv)
        assert result.position_size >= 0
        assert result.vol_ratio == 0.0

    def test_high_vol_target(self, sample_ohlcv):
        p = ThreeStagePipeline(vol_target=0.50)
        result = p.run(sample_ohlcv)
        assert result.position_size >= 0

    def test_custom_capital(self, sample_ohlcv):
        p = ThreeStagePipeline(capital=1_000_000, max_position_pct=0.10)
        result = p.run(sample_ohlcv)
        assert result.position_size <= 1_000_000 * 0.10 + 1e-6
