"""Tests for Vol Regime Sizing strategy."""

import numpy as np
import pandas as pd
import pytest

from .vol_regime_sizing import (
    VolRegimeSizingConfig,
    VolRegimeSizingResult,
    compute_vol_regime_sizing,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_price_series(n: int = 300, seed: int = 42) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Generate synthetic OHLCV data."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-01", periods=n, freq="B")

    # Mix of low and high vol periods
    returns = rng.normal(0, 0.01, n)
    # Inject high-vol regime around index 150-200
    returns[150:200] = rng.normal(0, 0.03, 50)

    close = 2000 * np.exp(np.cumsum(returns))
    close_s = pd.Series(close, index=dates, name="close")
    high_s = close_s * (1 + rng.uniform(0, 0.005, n))
    low_s = close_s * (1 - rng.uniform(0, 0.005, n))

    return close_s, high_s, low_s


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestVolRegimeSizing:
    """Test suite for Vol Regime Sizing strategy."""

    def test_basic_computation(self):
        """Should compute size multipliers without crashing."""
        close, high, low = _make_price_series()
        result = compute_vol_regime_sizing(close, high, low)

        assert isinstance(result, VolRegimeSizingResult)
        assert len(result.size_multiplier) == len(close)

    def test_frozen_config(self):
        """Config should be immutable."""
        config = VolRegimeSizingConfig()
        with pytest.raises(AttributeError):
            config.vol_target_annual = 0.20  # type: ignore

    def test_default_config(self):
        """Default config should match pre-registered values."""
        config = VolRegimeSizingConfig()
        assert config.vol_target_annual == 0.10
        assert config.vol_lookback == 20
        assert config.regime_window == 252
        assert config.size_low == 1.5
        assert config.size_med == 1.0
        assert config.size_high == 0.5

    def test_size_multiplier_range(self):
        """Size multiplier should be in [size_high, size_low]."""
        close, high, low = _make_price_series()
        result = compute_vol_regime_sizing(close, high, low)

        valid = result.size_multiplier.dropna()
        assert (valid >= 0.5).all()
        assert (valid <= 1.5).all()

    def test_empty_input(self):
        """Empty input should return empty result."""
        empty = pd.Series(dtype=float)
        result = compute_vol_regime_sizing(empty)

        assert len(result.size_multiplier) == 0

    def test_short_data_returns_neutral(self):
        """Insufficient data should return neutral multiplier."""
        idx = pd.bdate_range("2023-01-01", periods=10, freq="B")
        close = pd.Series(np.linspace(100, 110, 10), index=idx)
        result = compute_vol_regime_sizing(close)

        assert (result.size_multiplier == 1.0).all()

    def test_custom_config(self):
        """Custom config should be respected."""
        close, high, low = _make_price_series()
        config = VolRegimeSizingConfig(size_low=2.0, size_high=0.3)
        result = compute_vol_regime_sizing(close, high, low, config=config)

        assert result.config.size_low == 2.0
        assert result.config.size_high == 0.3

    def test_realized_vol_positive(self):
        """Realized vol should be non-negative."""
        close, high, low = _make_price_series()
        result = compute_vol_regime_sizing(close, high, low)

        valid = result.realized_vol.dropna()
        assert (valid >= 0).all()

    def test_vol_regime_values(self):
        """Vol regime should be LOW, MED, or HIGH."""
        close, high, low = _make_price_series()
        result = compute_vol_regime_sizing(close, high, low)

        valid = result.vol_regime.dropna()
        unique = set(valid.unique())
        assert unique.issubset({"LOW", "MED", "HIGH"})

    def test_high_vol_regime_reduces_size(self):
        """High vol regime should produce smaller size multiplier."""
        close, high, low = _make_price_series()
        result = compute_vol_regime_sizing(close, high, low)

        # Find HIGH regime periods
        high_mask = result.vol_regime.astype(str) == "HIGH"
        if high_mask.any():
            high_sizes = result.size_multiplier[high_mask]
            assert (high_sizes == 0.5).all()

    def test_low_vol_regime_increases_size(self):
        """Low vol regime should produce larger size multiplier."""
        close, high, low = _make_price_series()
        result = compute_vol_regime_sizing(close, high, low)

        low_mask = result.vol_regime.astype(str) == "LOW"
        if low_mask.any():
            low_sizes = result.size_multiplier[low_mask]
            assert (low_sizes == 1.5).all()

    def test_close_only_input(self):
        """Should work with close-only input (no H/L)."""
        close, _, _ = _make_price_series()
        result = compute_vol_regime_sizing(close)

        assert isinstance(result, VolRegimeSizingResult)
        assert len(result.size_multiplier) == len(close)
