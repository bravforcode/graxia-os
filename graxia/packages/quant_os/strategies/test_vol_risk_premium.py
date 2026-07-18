"""Tests for Vol Risk Premium strategy."""

import numpy as np
import pandas as pd
import pytest

from .vol_risk_premium import (
    VolRiskPremiumConfig,
    VolRiskPremiumResult,
    compute_vol_risk_premium_signals,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_price_series(n: int = 300, seed: int = 42) -> pd.Series:
    """Generate synthetic daily close prices."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-01", periods=n, freq="B")
    returns = rng.normal(0, 0.01, n)
    close = 2000 * np.exp(np.cumsum(returns))
    return pd.Series(close, index=dates, name="close")


def _make_implied_vol(n: int = 300, seed: int = 99) -> pd.Series:
    """Generate synthetic implied vol (higher than realized)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-01", periods=n, freq="B")
    # Implied vol typically > realized vol
    iv = 0.15 + rng.normal(0, 0.03, n)
    return pd.Series(np.abs(iv), index=dates, name="gvz")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestVolRiskPremium:
    """Test suite for Vol Risk Premium strategy."""

    def test_basic_computation(self):
        """Should compute signals without crashing."""
        close = _make_price_series()
        iv = _make_implied_vol()
        result = compute_vol_risk_premium_signals(close, iv)

        assert isinstance(result, VolRiskPremiumResult)
        assert len(result.signal) == len(close)

    def test_frozen_config(self):
        """Config should be immutable."""
        config = VolRiskPremiumConfig()
        with pytest.raises(AttributeError):
            config.vrp_lookback = 30  # type: ignore

    def test_default_config(self):
        """Default config should match pre-registered values."""
        config = VolRiskPremiumConfig()
        assert config.vrp_lookback == 20
        assert config.entry_z == 1.5
        assert config.exit_z == 0.5
        assert config.realized_vol_window == 20
        assert config.gvz_smoothing == 5
        assert config.regime_threshold == 0.0

    def test_signal_values_in_range(self):
        """Signal values should be -1, 0, or +1."""
        close = _make_price_series()
        iv = _make_implied_vol()
        result = compute_vol_risk_premium_signals(close, iv)

        unique = set(result.signal.unique())
        assert unique.issubset({-1, 0, 1})

    def test_empty_input(self):
        """Empty input should return empty result."""
        empty = pd.Series(dtype=float)
        result = compute_vol_risk_premium_signals(empty)

        assert len(result.signal) == 0

    def test_short_data_returns_zeros(self):
        """Insufficient data should return all zeros."""
        idx = pd.bdate_range("2023-01-01", periods=10, freq="B")
        close = pd.Series(np.linspace(100, 110, 10), index=idx)
        result = compute_vol_risk_premium_signals(close)

        assert (result.signal == 0).all()

    def test_no_implied_vol_degraded_mode(self):
        """Should work without implied vol (degraded mode)."""
        close = _make_price_series()
        result = compute_vol_risk_premium_signals(close, implied_vol=None)

        assert isinstance(result, VolRiskPremiumResult)
        # VRP should be ~0 (implied = realized)
        valid_vrp = result.vrp.dropna()
        assert abs(valid_vrp.mean()) < 0.01

    def test_custom_config(self):
        """Custom config should be respected."""
        close = _make_price_series()
        iv = _make_implied_vol()
        config = VolRiskPremiumConfig(entry_z=2.0, exit_z=1.0)
        result = compute_vol_risk_premium_signals(close, iv, config=config)

        assert result.config.entry_z == 2.0
        assert result.config.exit_z == 1.0

    def test_realized_vol_positive(self):
        """Realized vol should be non-negative."""
        close = _make_price_series()
        result = compute_vol_risk_premium_signals(close)

        valid = result.realized_vol.dropna()
        assert (valid >= 0).all()

    def test_vrp_calculation(self):
        """VRP should equal implied - realized vol."""
        close = _make_price_series()
        iv = _make_implied_vol()
        result = compute_vol_risk_premium_signals(close, iv)

        valid_idx = result.vrp.dropna().index
        if len(valid_idx) > 0:
            expected = result.implied_vol.loc[valid_idx] - result.realized_vol.loc[valid_idx]
            np.testing.assert_array_almost_equal(
                result.vrp.loc[valid_idx].values,
                expected.values,
                decimal=10,
            )

    def test_high_vrp_produces_long(self):
        """High VRP (implied >> realized) should produce long signals."""
        rng = np.random.default_rng(42)
        dates = pd.bdate_range("2023-01-01", periods=300, freq="B")
        close = pd.Series(2000 * np.exp(np.cumsum(rng.normal(0, 0.005, 300))), index=dates)
        # Implied vol much higher than realized → high VRP
        iv = pd.Series(np.full(300, 0.30), index=dates)
        config = VolRiskPremiumConfig(entry_z=0.5, vrp_lookback=10)

        result = compute_vol_risk_premium_signals(close, iv, config=config)

        # Should have some long signals
        assert (result.signal > 0).any()
