"""Tests for Orderflow Imbalance strategy."""

import numpy as np
import pandas as pd
import pytest

from .orderflow_imbalance import (
    OrderflowImbalanceConfig,
    OrderflowImbalanceResult,
    compute_orderflow_imbalance_signals,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_ohlcv(n: int = 200, seed: int = 42) -> tuple[pd.Series, ...]:
    """Generate synthetic OHLCV data."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-01", periods=n, freq="B")

    returns = rng.normal(0, 0.005, n)
    close = 2000 * np.exp(np.cumsum(returns))
    close_s = pd.Series(close, index=dates, name="close")
    high_s = close_s * (1 + rng.uniform(0, 0.005, n))
    low_s = close_s * (1 - rng.uniform(0, 0.005, n))
    open_s = close_s.shift(1).fillna(close_s.iloc[0])

    return open_s, high_s, low_s, close_s


def _make_buying_pressure_data(n: int = 200, seed: int = 42) -> tuple[pd.Series, ...]:
    """Generate data with sustained buying pressure (close near high)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-01", periods=n, freq="B")

    returns = rng.normal(0.001, 0.003, n)  # Upward drift
    close = 2000 * np.exp(np.cumsum(returns))
    close_s = pd.Series(close, index=dates, name="close")
    high_s = close_s * (1 + rng.uniform(0, 0.002, n))  # Close near high
    low_s = close_s * (1 - rng.uniform(0, 0.01, n))
    open_s = close_s.shift(1).fillna(close_s.iloc[0])

    return open_s, high_s, low_s, close_s


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOrderflowImbalance:
    """Test suite for Orderflow Imbalance strategy."""

    def test_basic_signal_generation(self):
        """Should generate signals without crashing."""
        o, h, l, c = _make_ohlcv()
        result = compute_orderflow_imbalance_signals(o, h, l, c)

        assert isinstance(result, OrderflowImbalanceResult)
        assert len(result.signal) == len(c)

    def test_frozen_config(self):
        """Config should be immutable."""
        config = OrderflowImbalanceConfig()
        with pytest.raises(AttributeError):
            config.clv_window = 20  # type: ignore

    def test_default_config(self):
        """Default config should match pre-registered values."""
        config = OrderflowImbalanceConfig()
        assert config.clv_window == 10
        assert config.entry_threshold == 5.0
        assert config.exit_threshold == 1.0
        assert config.atr_period == 14
        assert config.stop_atr == 2.0
        assert config.min_bars == 50

    def test_signal_values_in_range(self):
        """Signal values should be -1, 0, or +1."""
        o, h, l, c = _make_ohlcv()
        result = compute_orderflow_imbalance_signals(o, h, l, c)

        unique = set(result.signal.unique())
        assert unique.issubset({-1, 0, 1})

    def test_empty_input(self):
        """Empty input should return empty result."""
        empty = pd.Series(dtype=float)
        result = compute_orderflow_imbalance_signals(empty, empty, empty, empty)

        assert len(result.signal) == 0

    def test_short_data_returns_zeros(self):
        """Insufficient data should return all zeros."""
        idx = pd.bdate_range("2023-01-01", periods=10, freq="B")
        s = pd.Series(np.linspace(100, 110, 10), index=idx)
        result = compute_orderflow_imbalance_signals(s, s * 1.01, s * 0.99, s)

        assert (result.signal == 0).all()

    def test_clv_range(self):
        """CLV should be in [-1, 1]."""
        o, h, l, c = _make_ohlcv()
        result = compute_orderflow_imbalance_signals(o, h, l, c)

        valid = result.clv.dropna()
        assert (valid >= -1.01).all()  # Small float tolerance
        assert (valid <= 1.01).all()

    def test_custom_config(self):
        """Custom config should be respected."""
        o, h, l, c = _make_ohlcv()
        config = OrderflowImbalanceConfig(clv_window=20, entry_threshold=3.0)
        result = compute_orderflow_imbalance_signals(o, h, l, c, config=config)

        assert result.config.clv_window == 20
        assert result.config.entry_threshold == 3.0

    def test_buying_pressure_produces_long(self):
        """Sustained buying pressure should produce long signals."""
        o, h, l, c = _make_buying_pressure_data()
        config = OrderflowImbalanceConfig(entry_threshold=3.0, min_bars=30)
        result = compute_orderflow_imbalance_signals(o, h, l, c, config=config)

        # Should have at least some long signals
        assert (result.signal > 0).any()

    def test_nan_handling(self):
        """NaN values should be handled gracefully."""
        o, h, l, c = _make_ohlcv()
        c.iloc[50] = np.nan
        result = compute_orderflow_imbalance_signals(o, h, l, c)

        assert isinstance(result, OrderflowImbalanceResult)

    def test_zero_range_handling(self):
        """Zero high-low range should be handled (no division by zero)."""
        o, h, l, c = _make_ohlcv()
        # Set some bars to zero range
        h.iloc[60:65] = c.iloc[60:65]
        l.iloc[60:65] = c.iloc[60:65]
        result = compute_orderflow_imbalance_signals(o, h, l, c)

        assert not result.clv.isin([np.inf, -np.inf]).any()
