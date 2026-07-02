"""
EMA & RSI Indicator Tests — converted from script-only to real pytest tests.

Tests verify that the indicator calculations produce correct results
against known mathematical values (not just "runs without error").
"""

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Indicator implementations (pure, testable)
# ---------------------------------------------------------------------------


def ema(prices: np.ndarray, period: int) -> np.ndarray:
    """Exponential Moving Average.

    Args:
        prices: 1-D price series.
        period: EMA lookback period.

    Returns:
        1-D array of same length; first *period*-1 values are NaN.
    """
    if len(prices) < period:
        return np.full_like(prices, np.nan, dtype=float)

    alpha = 2.0 / (period + 1)
    result = np.full_like(prices, np.nan, dtype=float)
    # Seed with SMA of first *period* values
    result[period - 1] = np.mean(prices[:period])
    for i in range(period, len(prices)):
        result[i] = alpha * prices[i] + (1 - alpha) * result[i - 1]
    return result


def rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
    """Relative Strength Index (Wilder smoothing).

    Args:
        prices: 1-D price series.
        period: RSI lookback period (default 14).

    Returns:
        1-D array of same length; first *period* values are NaN.
    """
    if len(prices) <= period:
        return np.full_like(prices, np.nan, dtype=float)

    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    result = np.full(len(prices), np.nan, dtype=float)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - (100.0 / (1.0 + rs))

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i + 1] = 100.0 - (100.0 / (1.0 + rs))

    return result


# ---------------------------------------------------------------------------
# Tests — EMA
# ---------------------------------------------------------------------------


class TestEmaCorrect:
    """EMA must match hand-calculated values."""

    def test_ema_seed_is_sma(self):
        """First non-NaN value equals SMA of first *period* prices."""
        prices = np.array([10.0, 11.0, 12.0, 13.0, 14.0])
        result = ema(prices, period=3)
        # SMA of [10, 11, 12] = 11.0
        assert result[2] == pytest.approx(11.0, abs=1e-10)

    def test_ema_known_values(self):
        """EMA(5) of constant series equals that constant."""
        prices = np.full(20, 50.0)
        result = ema(prices, period=5)
        # All non-NaN values should be 50.0
        valid = result[~np.isnan(result)]
        np.testing.assert_allclose(valid, 50.0, atol=1e-10)

    def test_ema_short_series_returns_nan(self):
        """Series shorter than period returns all NaN."""
        prices = np.array([1.0, 2.0])
        result = ema(prices, period=5)
        assert np.all(np.isnan(result))

    def test_ema_length_matches_input(self):
        prices = np.arange(50, dtype=float)
        result = ema(prices, period=10)
        assert len(result) == len(prices)

    def test_ema_first_period_minus_1_are_nan(self):
        prices = np.arange(30, dtype=float)
        period = 10
        result = ema(prices, period=period)
        assert np.all(np.isnan(result[: period - 1]))
        assert not np.isnan(result[period - 1])


# ---------------------------------------------------------------------------
# Tests — RSI
# ---------------------------------------------------------------------------


class TestRsiCorrect:
    """RSI must match hand-calculated values."""

    def test_rsi_all_gains_is_100(self):
        """Monotonically increasing prices → RSI = 100."""
        prices = np.arange(1, 20, dtype=float)  # 1, 2, ..., 19
        result = rsi(prices, period=5)
        valid = result[~np.isnan(result)]
        np.testing.assert_allclose(valid, 100.0, atol=1e-10)

    def test_rsi_all_losses_is_0(self):
        """Monotonically decreasing prices → RSI = 0."""
        prices = np.arange(20, 1, -1, dtype=float)  # 20, 19, ..., 2
        result = rsi(prices, period=5)
        valid = result[~np.isnan(result)]
        np.testing.assert_allclose(valid, 0.0, atol=1e-10)

    def test_rsi_range_0_to_100(self):
        """RSI must always be in [0, 100]."""
        np.random.seed(42)
        prices = np.cumsum(np.random.randn(200)) + 100
        result = rsi(prices, period=14)
        valid = result[~np.isnan(result)]
        assert np.all(valid >= 0.0 - 1e-10)
        assert np.all(valid <= 100.0 + 1e-10)

    def test_rsi_short_series_returns_nan(self):
        """Series ≤ period returns all NaN."""
        prices = np.array([1.0, 2.0, 3.0])
        result = rsi(prices, period=14)
        assert np.all(np.isnan(result))

    def test_rsi_first_period_values_are_nan(self):
        prices = np.arange(1, 30, dtype=float)
        period = 14
        result = rsi(prices, period=period)
        # First *period* values (indices 0..period-1) should be NaN
        assert np.all(np.isnan(result[:period]))
        # Index *period* should be valid
        assert not np.isnan(result[period])
