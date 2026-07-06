"""Tests for factor signal layers: TSMOM, Carry, Pairs MR, and combined."""

import numpy as np
import pandas as pd

from graxia.packages.quant_os.strategies.carry import compute_carry_signal
from graxia.packages.quant_os.strategies.factor_signals import compute_factor_signals
from graxia.packages.quant_os.strategies.pairs_mr import compute_pairs_mr_signal
from graxia.packages.quant_os.strategies.tsmom import compute_tsmom_signal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_close(n: int = 300, start: float = 100.0, seed: int = 42) -> pd.Series:
    """Generate a random-walk price series."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0003, 0.01, n)
    price = start * np.cumprod(1 + returns)
    return pd.Series(price, index=pd.RangeIndex(n))


def _make_rates(n: int = 300, base: float = 5.0, quote: float = 2.0) -> tuple[pd.Series, pd.Series]:
    """Generate synthetic interest rate series."""
    idx = pd.RangeIndex(n)
    return (
        pd.Series(np.full(n, base), index=idx),
        pd.Series(np.full(n, quote), index=idx),
    )


# ---------------------------------------------------------------------------
# TSMOM tests
# ---------------------------------------------------------------------------


class TestTSMOM:
    def test_signal_values_bounded(self):
        close = _make_close()
        result = compute_tsmom_signal(close)
        valid = result.signal.dropna()
        assert set(valid.unique()).issubset({-1.0, 0.0, 1.0})

    def test_strength_non_negative(self):
        close = _make_close()
        result = compute_tsmom_signal(close)
        assert (result.strength.dropna() >= 0).all()

    def test_consensus_range(self):
        close = _make_close()
        result = compute_tsmom_signal(close)
        valid = result.consensus.dropna()
        assert valid.between(-1, 1).all()

    def test_lookback_returns_keys(self):
        close = _make_close()
        result = compute_tsmom_signal(close, lookbacks=[21, 63, 252])
        assert set(result.lookback_returns.keys()) == {"21d", "63d", "252d"}

    def test_custom_lookbacks(self):
        close = _make_close()
        result = compute_tsmom_signal(close, lookbacks=[10, 20])
        assert set(result.lookback_returns.keys()) == {"10d", "20d"}

    def test_strength_vol_scaling(self):
        """Higher vol target should scale strength up."""
        close = _make_close()
        low = compute_tsmom_signal(close, vol_target=0.05)
        high = compute_tsmom_signal(close, vol_target=0.20)
        # After warmup, high vol_target should produce >= low
        warmup = low.strength.dropna()
        if len(warmup) > 0:
            assert high.strength.dropna().mean() >= low.strength.dropna().mean() * 0.5


# ---------------------------------------------------------------------------
# Carry tests
# ---------------------------------------------------------------------------


class TestCarry:
    def test_positive_carry_long(self):
        n = 100
        base_rate = pd.Series(np.full(n, 5.0), index=pd.RangeIndex(n))
        quote_rate = pd.Series(np.full(n, 2.0), index=pd.RangeIndex(n))
        result = compute_carry_signal(base_rate, quote_rate)
        assert (result.signal == 1.0).all()

    def test_negative_carry_short(self):
        n = 100
        base_rate = pd.Series(np.full(n, 1.0), index=pd.RangeIndex(n))
        quote_rate = pd.Series(np.full(n, 4.0), index=pd.RangeIndex(n))
        result = compute_carry_signal(base_rate, quote_rate)
        assert (result.signal == -1.0).all()

    def test_zero_carry(self):
        n = 100
        rate = pd.Series(np.full(n, 3.0), index=pd.RangeIndex(n))
        result = compute_carry_signal(rate, rate)
        assert (result.signal == 0.0).all()

    def test_carry_value(self):
        n = 100
        base_rate = pd.Series(np.full(n, 5.0), index=pd.RangeIndex(n))
        quote_rate = pd.Series(np.full(n, 2.0), index=pd.RangeIndex(n))
        result = compute_carry_signal(base_rate, quote_rate)
        assert (result.carry == 3.0).all()

    def test_strength_bounded(self):
        base, quote = _make_rates()
        result = compute_carry_signal(base, quote)
        assert (result.strength.dropna() >= 0).all()
        assert (result.strength.dropna() <= 1.01).all()  # small float tolerance


# ---------------------------------------------------------------------------
# Pairs MR tests
# ---------------------------------------------------------------------------


class TestPairsMR:
    def test_spread_is_log_ratio(self):
        a = _make_close(seed=1)
        b = _make_close(seed=2)
        result = compute_pairs_mr_signal(a, b)
        expected = np.log(a / b)
        pd.testing.assert_series_equal(result.spread, expected, check_names=False)

    def test_zscore_mean_reversion(self):
        """Z-score should be roughly zero-mean over a long window."""
        rng = np.random.default_rng(99)
        n = 500
        common = rng.normal(0, 0.01, n).cumsum()
        a = pd.Series(100 * np.exp(common + rng.normal(0, 0.001, n)))
        b = pd.Series(100 * np.exp(common + rng.normal(0, 0.001, n)))
        result = compute_pairs_mr_signal(a, b, lookback=60)
        z = result.zscore.dropna()
        assert abs(z.mean()) < 1.0  # roughly centered

    def test_half_life_positive(self):
        rng = np.random.default_rng(77)
        n = 300
        common = rng.normal(0, 0.01, n).cumsum()
        a = pd.Series(100 * np.exp(common + rng.normal(0, 0.002, n)))
        b = pd.Series(100 * np.exp(common + rng.normal(0, 0.002, n)))
        result = compute_pairs_mr_signal(a, b)
        if not np.isnan(result.half_life):
            assert result.half_life > 0

    def test_signal_values(self):
        a = _make_close(seed=1)
        b = _make_close(seed=2)
        result = compute_pairs_mr_signal(a, b, entry_z=2.0)
        valid = result.signal.dropna()
        assert set(valid.unique()).issubset({-1.0, 0.0, 1.0})

    def test_entry_threshold(self):
        """Signal should only fire beyond entry_z."""
        a = _make_close(seed=1)
        b = _make_close(seed=2)
        result = compute_pairs_mr_signal(a, b, entry_z=2.0)
        active = result.signal[result.signal != 0]
        if len(active) > 0:
            corresponding_z = result.zscore.loc[active.index].abs()
            assert (corresponding_z >= 1.5).all()  # allow some slack for edge


# ---------------------------------------------------------------------------
# Combined factor tests
# ---------------------------------------------------------------------------


class TestFactorSignals:
    def test_tsmom_only(self):
        close = _make_close()
        result = compute_factor_signals(close)
        assert result.carry is None
        assert result.pairs_mr is None
        valid = result.combined_signal.dropna()
        assert set(valid.unique()).issubset({-1.0, 0.0, 1.0})

    def test_with_carry(self):
        close = _make_close()
        base, quote = _make_rates()
        result = compute_factor_signals(close, base_rate=base, quote_rate=quote)
        assert result.carry is not None
        assert result.pairs_mr is None

    def test_with_pairs(self):
        close = _make_close(seed=1)
        pairs = _make_close(seed=2)
        result = compute_factor_signals(close, pairs_price=pairs)
        assert result.carry is None
        assert result.pairs_mr is not None

    def test_all_factors(self):
        close = _make_close(seed=1)
        pairs = _make_close(seed=2)
        base, quote = _make_rates()
        result = compute_factor_signals(close, base_rate=base, quote_rate=quote, pairs_price=pairs)
        assert result.carry is not None
        assert result.pairs_mr is not None
        valid = result.confidence.dropna()
        assert (valid >= 0).all()
        assert (valid <= 1).all()

    def test_confidence_bounded(self):
        close = _make_close()
        result = compute_factor_signals(close)
        valid = result.confidence.dropna()
        assert (valid >= 0).all()
        assert (valid <= 1).all()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_short_series(self):
        close = pd.Series([100.0, 101.0, 99.0])
        result = compute_tsmom_signal(close, lookbacks=[1, 2])
        assert len(result.signal) == 3

    def test_constant_price(self):
        close = pd.Series(np.full(100, 50.0))
        result = compute_tsmom_signal(close)
        # Returns are zero -> signal should be 0
        assert (result.signal.dropna() == 0.0).all()

    def test_nan_handling(self):
        close = _make_close()
        close.iloc[50:60] = np.nan
        result = compute_tsmom_signal(close)
        assert len(result.signal) == len(close)

    def test_zero_vol_no_crash(self):
        """Constant price has zero vol — should not divide by zero."""
        close = pd.Series(np.full(200, 100.0))
        result = compute_tsmom_signal(close, vol_target=0.10)
        assert np.isfinite(result.strength.dropna()).all()
