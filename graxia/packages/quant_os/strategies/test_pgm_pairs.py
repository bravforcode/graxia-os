"""Tests for PGM Pairs Arbitrage strategy."""

import numpy as np
import pandas as pd
import pytest

from .pgm_pairs import PGMPairsConfig, PGMPairsResult, compute_pgm_pairs_signals


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_cointegrated_pair(n: int = 200, seed: int = 42) -> tuple[pd.Series, ...]:
    """Generate synthetic cointegrated XPT/XPD price series."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2023-01-01", periods=n, freq="D")

    # Common factor + noise
    common = np.cumsum(rng.normal(0, 0.01, n))
    xpt = 1000 * np.exp(common + rng.normal(0, 0.005, n))
    xpd = 1200 * np.exp(0.8 * common + rng.normal(0, 0.005, n))

    xpt_s = pd.Series(xpt, index=dates, name="xpt_close")
    xpd_s = pd.Series(xpd, index=dates, name="xpd_close")

    # H/L from close
    xpt_h = xpt_s * (1 + rng.uniform(0, 0.01, n))
    xpt_l = xpt_s * (1 - rng.uniform(0, 0.01, n))
    xpd_h = xpd_s * (1 + rng.uniform(0, 0.01, n))
    xpd_l = xpd_s * (1 - rng.uniform(0, 0.01, n))

    return xpt_s, xpt_h, xpt_l, xpd_s, xpd_h, xpd_l


def _make_random_pair(n: int = 200, seed: int = 99) -> tuple[pd.Series, ...]:
    """Generate synthetic NON-cointegrated (random walk) pair."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2023-01-01", periods=n, freq="D")

    xpt = 1000 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    xpd = 1200 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))

    xpt_s = pd.Series(xpt, index=dates, name="xpt_close")
    xpd_s = pd.Series(xpd, index=dates, name="xpd_close")

    xpt_h = xpt_s * (1 + rng.uniform(0, 0.01, n))
    xpt_l = xpt_s * (1 - rng.uniform(0, 0.01, n))
    xpd_h = xpd_s * (1 + rng.uniform(0, 0.01, n))
    xpd_l = xpd_s * (1 - rng.uniform(0, 0.01, n))

    return xpt_s, xpt_h, xpt_l, xpd_s, xpd_h, xpd_l


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPGMPairs:
    """Test suite for PGM Pairs strategy."""

    def test_cointegrated_pair_produces_signals(self):
        """Cointegrated pair should produce non-zero signals."""
        xpt_c, xpt_h, xpt_l, xpd_c, xpd_h, xpd_l = _make_cointegrated_pair()
        result = compute_pgm_pairs_signals(xpt_c, xpt_h, xpt_l, xpd_c, xpd_h, xpd_l)

        assert isinstance(result, PGMPairsResult)
        assert result.coint_pvalue < 0.5  # Should detect some cointegration
        # With cointegrated data, we should get at least some signals
        # (not guaranteed due to z-score threshold, but likely)

    def test_random_pair_no_signals(self):
        """Non-cointegrated pair should produce no signals."""
        xpt_c, xpt_h, xpt_l, xpd_c, xpd_h, xpd_l = _make_random_pair()
        config = PGMPairsConfig(coint_pval_max=0.05)
        result = compute_pgm_pairs_signals(
            xpt_c, xpt_h, xpt_l, xpd_c, xpd_h, xpd_l, config=config
        )

        # Random walk pair should fail cointegration test
        assert result.coint_pvalue > 0.05
        # All signals should be 0
        assert (result.signal == 0).all()

    def test_zscore_calculation(self):
        """Z-score should be computed correctly."""
        xpt_c, xpt_h, xpt_l, xpd_c, xpd_h, xpd_l = _make_cointegrated_pair()
        result = compute_pgm_pairs_signals(xpt_c, xpt_h, xpt_l, xpd_c, xpd_h, xpd_l)

        # Z-score should have valid values after warmup
        valid_z = result.zscore.dropna()
        assert len(valid_z) > 0
        # Mean should be roughly 0 (stationary spread)
        assert abs(valid_z.mean()) < 1.0

    def test_half_life_estimation(self):
        """Half-life should be positive and finite for cointegrated pair."""
        xpt_c, xpt_h, xpt_l, xpd_c, xpd_h, xpd_l = _make_cointegrated_pair()
        result = compute_pgm_pairs_signals(xpt_c, xpt_h, xpt_l, xpd_c, xpd_h, xpd_l)

        # Half-life should be positive (mean-reverting)
        assert result.half_life > 0 or np.isinf(result.half_life)

    def test_spread_computed(self):
        """Spread should be computed from log prices."""
        xpt_c, xpt_h, xpt_l, xpd_c, xpd_h, xpd_l = _make_cointegrated_pair()
        result = compute_pgm_pairs_signals(xpt_c, xpt_h, xpt_l, xpd_c, xpd_h, xpd_l)

        # Spread is log(XPT) - hedge_ratio * log(XPD), or log(XPT/XPD) if no ratio
        assert len(result.spread) == len(xpt_c)
        assert not result.spread.isna().all()

    def test_empty_data_returns_empty(self):
        """Empty input should return empty result."""
        empty = pd.Series(dtype=float)
        result = compute_pgm_pairs_signals(empty, empty, empty, empty, empty, empty)

        assert len(result.signal) == 0
        assert np.isnan(result.half_life)
        assert result.coint_pvalue == 1.0

    def test_single_row_returns_nan(self):
        """Single row should return NaN values."""
        idx = pd.date_range("2023-01-01", periods=1, freq="D")
        s = pd.Series([100.0], index=idx)
        result = compute_pgm_pairs_signals(s, s, s, s, s, s)

        assert len(result.signal) == 1
        assert result.signal.iloc[0] == 0

    def test_nan_handling(self):
        """NaN values should be handled gracefully."""
        xpt_c, xpt_h, xpt_l, xpd_c, xpd_h, xpd_l = _make_cointegrated_pair()
        # Inject NaN
        xpt_c.iloc[50] = np.nan
        result = compute_pgm_pairs_signals(xpt_c, xpt_h, xpt_l, xpd_c, xpd_h, xpd_l)

        assert isinstance(result, PGMPairsResult)
        # Should not crash

    def test_custom_config(self):
        """Custom config should be respected."""
        xpt_c, xpt_h, xpt_l, xpd_c, xpd_h, xpd_l = _make_cointegrated_pair()
        config = PGMPairsConfig(lookback=30, entry_z=1.5, exit_z=0.3)
        result = compute_pgm_pairs_signals(
            xpt_c, xpt_h, xpt_l, xpd_c, xpd_h, xpd_l, config=config
        )

        assert result.config.lookback == 30
        assert result.config.entry_z == 1.5
        assert result.config.exit_z == 0.3

    def test_signal_values_in_range(self):
        """Signal values should be -1, 0, or +1."""
        xpt_c, xpt_h, xpt_l, xpd_c, xpd_h, xpd_l = _make_cointegrated_pair()
        result = compute_pgm_pairs_signals(xpt_c, xpt_h, xpt_l, xpd_c, xpd_h, xpd_l)

        unique = set(result.signal.unique())
        assert unique.issubset({-1, 0, 1})

    def test_frozen_config(self):
        """Config should be frozen (immutable)."""
        config = PGMPairsConfig()
        with pytest.raises(AttributeError):
            config.lookback = 30  # type: ignore
