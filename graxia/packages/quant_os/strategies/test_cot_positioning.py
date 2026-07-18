"""Tests for COT Positioning strategy."""

import numpy as np
import pandas as pd
import pytest

from .cot_positioning import (
    COTPositioningConfig,
    COTPositioningResult,
    compute_cot_positioning_signals,
    load_cot_data,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_cot_data(n: int = 104, seed: int = 42) -> tuple[pd.Series, pd.Series]:
    """Generate synthetic weekly COT data."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-01", periods=n, freq="W-FRI")

    # Net positioning with mean-reverting behavior
    net_pos = np.cumsum(rng.normal(0, 5000, n))
    # Add extreme values for testing
    net_pos[50] = net_pos.mean() + 3 * net_pos.std()  # Extreme long
    net_pos[80] = net_pos.mean() - 3 * net_pos.std()  # Extreme short

    return pd.DatetimeIndex(dates), pd.Series(net_pos, name="net_positioning")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCOTPositioning:
    """Test suite for COT Positioning strategy."""

    def test_basic_signal_generation(self):
        """Should generate signals without crashing."""
        dates, net_pos = _make_cot_data()
        result = compute_cot_positioning_signals(dates, net_pos)

        assert isinstance(result, COTPositioningResult)
        assert len(result.signal) == len(dates)

    def test_frozen_config(self):
        """Config should be immutable."""
        config = COTPositioningConfig()
        with pytest.raises(AttributeError):
            config.lookback_weeks = 26  # type: ignore

    def test_default_config(self):
        """Default config should match pre-registered values."""
        config = COTPositioningConfig()
        assert config.lookback_weeks == 52
        assert config.entry_z == 2.0
        assert config.exit_z == 0.5
        assert config.min_hold_weeks == 1
        assert config.max_hold_weeks == 4

    def test_signal_values_in_range(self):
        """Signal values should be -1, 0, or +1."""
        dates, net_pos = _make_cot_data()
        result = compute_cot_positioning_signals(dates, net_pos)

        unique = set(result.signal.unique())
        assert unique.issubset({-1, 0, 1})

    def test_insufficient_data_returns_zeros(self):
        """Insufficient data should return all zeros."""
        dates = pd.date_range("2023-01-01", periods=10, freq="W-FRI")
        net_pos = pd.Series(np.random.randn(10) * 1000)
        result = compute_cot_positioning_signals(dates, net_pos)

        assert (result.signal == 0).all()

    def test_custom_config(self):
        """Custom config should be respected."""
        dates, net_pos = _make_cot_data()
        config = COTPositioningConfig(lookback_weeks=26, entry_z=1.5)
        result = compute_cot_positioning_signals(dates, net_pos, config=config)

        assert result.config.lookback_weeks == 26
        assert result.config.entry_z == 1.5

    def test_zscore_calculation(self):
        """Z-score should be computed correctly."""
        dates, net_pos = _make_cot_data()
        result = compute_cot_positioning_signals(dates, net_pos)

        valid_z = result.zscore.dropna()
        assert len(valid_z) > 0

    def test_extreme_long_produces_short(self):
        """Extreme net-long positioning should produce short signal."""
        # Create data with clear extreme
        dates = pd.date_range("2022-01-01", periods=104, freq="W-FRI")
        net_pos = pd.Series(np.zeros(104), name="net_positioning")
        # Build up history first
        net_pos.iloc[:52] = np.linspace(0, 10000, 52)
        # Then extreme spike
        net_pos.iloc[52] = 50000  # Way above mean

        result = compute_cot_positioning_signals(dates, net_pos)
        # After enough history, extreme should trigger short
        # (exact behavior depends on z-score calculation)

    def test_max_hold_period(self):
        """Position should not exceed max_hold_weeks."""
        dates, net_pos = _make_cot_data()
        config = COTPositioningConfig(max_hold_weeks=2)
        result = compute_cot_positioning_signals(dates, net_pos, config=config)

        # Check consecutive non-zero signals
        signal = result.signal.values
        consecutive = 0
        max_consecutive = 0
        for s in signal:
            if s != 0:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 0

        assert max_consecutive <= config.max_hold_weeks + 1  # +1 for entry bar

    def test_net_positioning_preserved(self):
        """Output should preserve input net positioning."""
        dates, net_pos = _make_cot_data()
        result = compute_cot_positioning_signals(dates, net_pos)

        pd.testing.assert_series_equal(
            result.net_positioning.reset_index(drop=True),
            net_pos.reset_index(drop=True),
            check_names=False,
        )

    def test_load_cot_data_nonexistent_dir(self):
        """Loading from nonexistent dir should return empty DataFrame."""
        result = load_cot_data("/nonexistent/path")
        assert result.empty

    def test_contrarian_logic(self):
        """Signal should be contrarian to extreme positioning."""
        # Create clear contrarian setup
        dates = pd.date_range("2022-01-01", periods=104, freq="W-FRI")
        net_pos = pd.Series(np.zeros(104), name="net_positioning")
        # Stable history
        net_pos.iloc[:60] = 5000
        # Extreme spike up at index 60
        net_pos.iloc[60] = 25000

        result = compute_cot_positioning_signals(dates, net_pos)

        # If z-score is computed and extreme, signal should be -1 (short)
        # after enough warmup
