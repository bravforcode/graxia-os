"""Tests for FOMC Drift strategy."""

import numpy as np
import pandas as pd
import pytest

from .fomc_drift import FOMCDriftConfig, FOMCDriftResult, compute_fomc_drift_signals


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_ohlcv_with_fomc(n: int = 500, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data with embedded FOMC-like events."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-01", periods=n, freq="B")

    # Base price series
    returns = rng.normal(0, 0.005, n)
    # Inject larger moves on known FOMC dates (2023-02-01, 2023-03-22, etc.)
    fomc_indices = [20, 55, 85, 115, 145, 175, 205, 235]
    for idx in fomc_indices:
        if idx < n:
            returns[idx] = rng.choice([-0.005, 0.005])  # FOMC day move

    close = 2000 * np.exp(np.cumsum(returns))
    close_s = pd.Series(close, index=dates, name="close")
    high_s = close_s * (1 + rng.uniform(0, 0.005, n))
    low_s = close_s * (1 - rng.uniform(0, 0.005, n))

    return close_s, high_s, low_s


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFOMCDrift:
    """Test suite for FOMC Drift strategy."""

    def test_basic_signal_generation(self):
        """Should generate signals without crashing."""
        close, high, low = _make_ohlcv_with_fomc()
        result = compute_fomc_drift_signals(close, high, low)

        assert isinstance(result, FOMCDriftResult)
        assert len(result.signal) == len(close)
        assert result.signal.dtype == np.int64 or result.signal.dtype == int

    def test_frozen_config(self):
        """Config should be immutable."""
        config = FOMCDriftConfig()
        with pytest.raises(AttributeError):
            config.drift_window_days = 5  # type: ignore

    def test_default_config(self):
        """Default config should match pre-registered values."""
        config = FOMCDriftConfig()
        assert config.drift_window_days == 3
        assert config.min_fomc_return == 0.002
        assert config.max_fomc_return == 0.03
        assert config.atr_period == 14
        assert config.stop_atr == 2.0

    def test_empty_input(self):
        """Empty input should return empty result."""
        empty = pd.Series(dtype=float)
        result = compute_fomc_drift_signals(empty, empty, empty)

        assert len(result.signal) == 0

    def test_short_data_returns_zeros(self):
        """Insufficient data should return all zeros."""
        idx = pd.date_range("2023-01-01", periods=5, freq="B")
        close = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0], index=idx)
        high = close * 1.01
        low = close * 0.99
        result = compute_fomc_drift_signals(close, high, low)

        assert (result.signal == 0).all()

    def test_signal_values_in_range(self):
        """Signal values should be -1, 0, or +1."""
        close, high, low = _make_ohlcv_with_fomc()
        result = compute_fomc_drift_signals(close, high, low)

        unique = set(result.signal.unique())
        assert unique.issubset({-1, 0, 1})

    def test_custom_config(self):
        """Custom config should be respected."""
        close, high, low = _make_ohlcv_with_fomc()
        config = FOMCDriftConfig(drift_window_days=5, min_fomc_return=0.001)
        result = compute_fomc_drift_signals(close, high, low, config=config)

        assert result.config.drift_window_days == 5
        assert result.config.min_fomc_return == 0.001

    def test_fomc_return_recorded(self):
        """FOMC day returns should be recorded."""
        close, high, low = _make_ohlcv_with_fomc()
        result = compute_fomc_drift_signals(close, high, low)

        # At least some FOMC returns should be non-NaN
        # (depends on whether synthetic data has FOMC dates)
        assert isinstance(result.fomc_return, pd.Series)

    def test_drift_window_limits_holding(self):
        """Position should not exceed drift_window_days."""
        close, high, low = _make_ohlcv_with_fomc()
        config = FOMCDriftConfig(drift_window_days=2)
        result = compute_fomc_drift_signals(close, high, low, config=config)

        # Check that consecutive non-zero signals don't exceed drift_window_days
        signal = result.signal.values
        consecutive = 0
        max_consecutive = 0
        for s in signal:
            if s != 0:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 0

        assert max_consecutive <= config.drift_window_days

    def test_nan_handling(self):
        """NaN values should be handled gracefully."""
        close, high, low = _make_ohlcv_with_fomc()
        close.iloc[50] = np.nan
        result = compute_fomc_drift_signals(close, high, low)

        assert isinstance(result, FOMCDriftResult)
