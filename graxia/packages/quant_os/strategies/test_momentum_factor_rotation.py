"""Tests for Momentum Factor Rotation strategy."""

import numpy as np
import pandas as pd
import pytest

from .momentum_factor_rotation import (
    MomentumFactorRotationConfig,
    MomentumFactorRotationResult,
    compute_momentum_factor_rotation,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_multi_asset_prices(
    n: int = 300, assets: int = 4, seed: int = 42
) -> pd.DataFrame:
    """Generate synthetic multi-asset price data."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-01", periods=n, freq="B")

    data = {}
    for i in range(assets):
        # Different drift for each asset to create ranking
        drift = 0.0002 * (i - assets / 2)
        returns = rng.normal(drift, 0.01, n)
        data[f"asset_{i}"] = 100 * np.exp(np.cumsum(returns))

    return pd.DataFrame(data, index=dates)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMomentumFactorRotation:
    """Test suite for Momentum Factor Rotation strategy."""

    def test_basic_computation(self):
        """Should compute signals without crashing."""
        prices = _make_multi_asset_prices()
        result = compute_momentum_factor_rotation(prices)

        assert isinstance(result, MomentumFactorRotationResult)
        assert result.signal.shape == prices.shape

    def test_frozen_config(self):
        """Config should be immutable."""
        config = MomentumFactorRotationConfig()
        with pytest.raises(AttributeError):
            config.top_n = 3  # type: ignore

    def test_default_config(self):
        """Default config should match pre-registered values."""
        config = MomentumFactorRotationConfig()
        assert config.lookbacks == (21, 63, 252)
        assert config.vol_target == 0.10
        assert config.top_n == 2
        assert config.bottom_n == 0
        assert config.rebalance_freq == 5
        assert config.min_signal_strength == 0.3

    def test_signal_values_in_range(self):
        """Signal values should be -1, 0, or +1."""
        prices = _make_multi_asset_prices()
        result = compute_momentum_factor_rotation(prices)

        unique = set(result.signal.values.flatten())
        assert unique.issubset({-1, 0, 1})

    def test_empty_input(self):
        """Empty input should return empty result."""
        empty = pd.DataFrame()
        result = compute_momentum_factor_rotation(empty)

        assert result.signal.empty

    def test_single_asset(self):
        """Should work with single asset."""
        prices = _make_multi_asset_prices(assets=1)
        result = compute_momentum_factor_rotation(prices)

        assert result.signal.shape[1] == 1

    def test_custom_config(self):
        """Custom config should be respected."""
        prices = _make_multi_asset_prices()
        config = MomentumFactorRotationConfig(top_n=1, rebalance_freq=10)
        result = compute_momentum_factor_rotation(prices, config=config)

        assert result.config.top_n == 1
        assert result.config.rebalance_freq == 10

    def test_rank_ordering(self):
        """Ranks should be ordered 1..N at each rebalance point."""
        prices = _make_multi_asset_prices()
        result = compute_momentum_factor_rotation(prices)

        # At each bar, ranks should be 1..N (with possible ties)
        for i in range(0, len(prices), result.config.rebalance_freq):
            bar_rank = result.rank.iloc[i].dropna()
            if len(bar_rank) > 0:
                assert bar_rank.min() >= 1
                assert bar_rank.max() <= len(prices.columns)

    def test_strength_non_negative(self):
        """Strength should be non-negative."""
        prices = _make_multi_asset_prices()
        result = compute_momentum_factor_rotation(prices)

        valid = result.strength.dropna()
        assert (valid >= 0).all().all()

    def test_long_only_mode(self):
        """With bottom_n=0, no short signals should exist."""
        prices = _make_multi_asset_prices()
        config = MomentumFactorRotationConfig(bottom_n=0)
        result = compute_momentum_factor_rotation(prices, config=config)

        assert (result.signal >= 0).all().all()

    def test_rebalance_frequency(self):
        """Signals should only change at rebalance points."""
        prices = _make_multi_asset_prices(n=50)
        config = MomentumFactorRotationConfig(rebalance_freq=10)
        result = compute_momentum_factor_rotation(prices, config=config)

        # Between rebalances, signal should be forward-filled
        for i in range(1, len(prices)):
            if i % config.rebalance_freq != 0:
                prev = result.signal.iloc[i - 1]
                curr = result.signal.iloc[i]
                pd.testing.assert_series_equal(curr, prev, check_names=False)
