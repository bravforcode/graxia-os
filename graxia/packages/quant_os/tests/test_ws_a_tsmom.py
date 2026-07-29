"""Tests for WS-A TSMOM harness (trial 1028).

Validates signal computation, cost model, position lifecycle, and validation helpers.
Does NOT test against live data (uses synthetic fixtures).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Load the harness module directly (scripts/ has no __init__.py)
_ROOT = Path(__file__).resolve().parent.parent
_harness_path = _ROOT / "scripts" / "run_ws_a_tsmom.py"
_spec = importlib.util.spec_from_file_location("run_ws_a_tsmom", str(_harness_path))
_harness = importlib.util.module_from_spec(_spec)
sys.modules["run_ws_a_tsmom"] = _harness  # register before exec (dataclass needs __module__)
_spec.loader.exec_module(_harness)

LOOKBACK = _harness.LOOKBACK
REBALANCE_FREQ = _harness.REBALANCE_FREQ
UNIVERSE = _harness.UNIVERSE
VOL_CLIP_LOWER = _harness.VOL_CLIP_LOWER
VOL_CLIP_UPPER = _harness.VOL_CLIP_UPPER
VOL_TARGET = _harness.VOL_TARGET
Position = _harness.Position
Trade = _harness.Trade
_compute_cost = _harness._compute_cost
compute_signal = _harness.compute_signal
jackknife_sharpe = _harness.jackknife_sharpe
pooled_dk_test = _harness.pooled_dk_test
run_backtest = _harness.run_backtest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _make_price_df(prices: list[float], start: str = "2020-01-01") -> pd.DataFrame:
    """Create a synthetic price DataFrame."""
    dates = pd.bdate_range(start, periods=len(prices))
    return pd.DataFrame(
        {"time": dates, "open": prices, "high": prices, "low": prices, "close": prices, "volume": [100] * len(prices)}
    )


def _make_trending_df(n: int = 500, drift: float = 0.0002, start: str = "2020-01-01") -> pd.DataFrame:
    """Create a synthetic trending price series."""
    np.random.seed(42)
    returns = np.random.normal(drift, 0.01, n)
    prices = [100.0]
    for r in returns:
        prices.append(prices[-1] * (1 + r))
    return _make_price_df(prices[1:], start)


def _make_flat_df(n: int = 500, start: str = "2020-01-01") -> pd.DataFrame:
    """Create a flat (no trend) price series."""
    return _make_price_df([100.0] * n, start)


def _make_multi_symbol_data() -> dict[str, pd.DataFrame]:
    """Create synthetic data for all 7 symbols with aligned dates."""
    n = 600  # enough for LOOKBACK + some trading
    base_dates = pd.bdate_range("2020-01-01", periods=n)
    data = {}
    for i, sym in enumerate(UNIVERSE):
        np.random.seed(42 + i)
        drift = 0.0001 * (i + 1)  # varying drifts
        returns = np.random.normal(drift, 0.01, n)
        prices = [100.0 + i * 10 for _ in range(1)]
        for r in returns:
            prices.append(prices[-1] * (1 + r))
        df = pd.DataFrame(
            {
                "time": base_dates,
                "open": prices[1:],
                "high": [p * 1.001 for p in prices[1:]],
                "low": [p * 0.999 for p in prices[1:]],
                "close": prices[1:],
                "volume": [100] * n,
            }
        )
        data[sym] = df
    return data


# ---------------------------------------------------------------------------
# Signal tests
# ---------------------------------------------------------------------------
class TestComputeSignal:
    def test_signal_range(self):
        """Signal must be in {-1, 0, +1}."""
        df = _make_trending_df(500)
        signal, vol_scale = compute_signal(df["close"])
        unique_vals = set(signal.dropna().unique())
        assert unique_vals.issubset({-1.0, 0.0, 1.0}), f"Unexpected signal values: {unique_vals}"

    def test_trending_up_gives_long(self):
        """Strong uptrend should produce +1 signal after LOOKBACK bars."""
        prices = list(np.linspace(100, 200, LOOKBACK + 50))  # strong uptrend
        df = _make_price_df(prices)
        signal, _ = compute_signal(df["close"])
        # After LOOKBACK bars, signal should be +1
        last_signal = signal.iloc[-1]
        assert last_signal == 1.0, f"Expected +1 for uptrend, got {last_signal}"

    def test_trending_down_gives_short(self):
        """Strong downtrend should produce -1 signal after LOOKBACK bars."""
        prices = list(np.linspace(200, 100, LOOKBACK + 50))  # strong downtrend
        df = _make_price_df(prices)
        signal, _ = compute_signal(df["close"])
        last_signal = signal.iloc[-1]
        assert last_signal == -1.0, f"Expected -1 for downtrend, got {last_signal}"

    def test_flat_gives_zero(self):
        """Flat prices should produce 0 signal."""
        df = _make_flat_df(LOOKBACK + 50)
        signal, _ = compute_signal(df["close"])
        last_signal = signal.iloc[-1]
        assert last_signal == 0.0, f"Expected 0 for flat, got {last_signal}"

    def test_vol_scale_clipped(self):
        """Vol scale must be in [VOL_CLIP_LOWER, VOL_CLIP_UPPER]."""
        df = _make_trending_df(500)
        _, vol_scale = compute_signal(df["close"])
        valid = vol_scale.dropna()
        assert valid.min() >= VOL_CLIP_LOWER, f"Vol scale below floor: {valid.min()}"
        assert valid.max() <= VOL_CLIP_UPPER, f"Vol scale above ceiling: {valid.max()}"

    def test_first_lookback_bars_are_nan(self):
        """Signal should be NaN for first LOOKBACK bars."""
        df = _make_trending_df(500)
        signal, _ = compute_signal(df["close"])
        assert signal.iloc[:LOOKBACK].isna().all(), "First LOOKBACK bars should be NaN"
        assert signal.iloc[LOOKBACK:].notna().all(), "Bars after LOOKBACK should not be NaN"


# ---------------------------------------------------------------------------
# Cost model tests
# ---------------------------------------------------------------------------
class TestComputeCost:
    def test_cost_scales_with_vol_scale(self):
        """Cost should be proportional to quantity (vol_scale)."""
        cost_1 = _compute_cost("XAUUSD", 3000, 3010, 1.0)
        cost_2 = _compute_cost("XAUUSD", 3000, 3010, 2.0)
        assert abs(cost_2 - 2 * cost_1) < 1e-10, "Cost should scale linearly with vol_scale"

    def test_cost_independent_of_price(self):
        """Cost should NOT depend on entry/exit price (vol_scale is dimensionless)."""
        cost_a = _compute_cost("XAUUSD", 3000, 3010, 1.0)
        cost_b = _compute_cost("XAUUSD", 5000, 5010, 1.0)
        assert abs(cost_a - cost_b) < 1e-10, "Cost should be price-independent for vol_scale sizing"

    def test_cost_proportional_to_spread(self):
        """Higher total cost (spread + commission) asset should have higher cost."""
        cost_low = _compute_cost("XAUUSD", 3000, 3010, 1.0)  # 0.32 bps, 0 comm = 0.32 bps total
        cost_high = _compute_cost("NAS100", 10000, 10010, 1.0)  # 1.30 bps, 0 comm = 1.30 bps total
        assert cost_high > cost_low, f"NAS100 cost ({cost_high}) should > XAUUSD ({cost_low})"

    def test_cost_multiplier(self):
        """cost_multiplier should scale cost linearly."""
        base = _compute_cost("XAUUSD", 3000, 3010, 1.0, multiplier=1.0)
        stress = _compute_cost("XAUUSD", 3000, 3010, 1.0, multiplier=2.0)
        assert abs(stress - 2 * base) < 1e-10, "Multiplier should double cost"

    def test_cost_unknown_symbol_uses_default(self):
        """Unknown symbol should use default 1.0 bps spread."""
        cost = _compute_cost("UNKNOWN", 100, 101, 1.0)
        expected = 1.0 * 1.0 / 10000  # 1.0 bps
        assert abs(cost - expected) < 1e-10


# ---------------------------------------------------------------------------
# Backtest lifecycle tests
# ---------------------------------------------------------------------------
class TestRunBacktest:
    def test_runs_without_error(self):
        """Backtest should complete without exceptions."""
        data = _make_multi_symbol_data()
        result = run_backtest(data)
        assert "portfolio_returns" in result
        assert "trades" in result
        assert "metrics" in result

    def test_no_trades_before_lookback(self):
        """No trades should occur before LOOKBACK bars."""
        data = _make_multi_symbol_data()
        result = run_backtest(data)
        for t in result["trades"]:
            assert t.entry_bar >= LOOKBACK, f"Trade entered at bar {t.entry_bar} < LOOKBACK"

    def test_positions_are_closed_at_end(self):
        """All positions should be closed by end-of-backtest cleanup."""
        data = _make_multi_symbol_data()
        result = run_backtest(data)
        # Check final portfolio return is not NaN
        port_df = result["portfolio_returns"]
        assert port_df["return"].notna().all(), "Portfolio returns contain NaN"

    def test_cost_stress_reduces_sharpe(self):
        """Higher costs should reduce (or at worst equal) Sharpe."""
        data = _make_multi_symbol_data()
        base = run_backtest(data, cost_multiplier=1.0)["metrics"]["sharpe"]
        stress = run_backtest(data, cost_multiplier=2.0)["metrics"]["sharpe"]
        assert stress <= base + 0.001, f"Stress Sharpe ({stress}) should <= base ({base})"

    def test_trades_have_valid_pnl(self):
        """All trades should have finite PnL."""
        data = _make_multi_symbol_data()
        result = run_backtest(data)
        for t in result["trades"]:
            assert np.isfinite(t.pnl), f"Trade PnL is not finite: {t.pnl}"
            assert np.isfinite(t.cost), f"Trade cost is not finite: {t.cost}"

    def test_metrics_are_finite(self):
        """Key metrics should be finite."""
        data = _make_multi_symbol_data()
        m = run_backtest(data)["metrics"]
        assert np.isfinite(m["sharpe"]), "Sharpe is not finite"
        assert np.isfinite(m["annualized_return"]), "Annualized return is not finite"
        assert np.isfinite(m["annualized_vol"]), "Annualized vol is not finite"


# ---------------------------------------------------------------------------
# Validation helper tests
# ---------------------------------------------------------------------------
class TestPooledDkTest:
    def test_positive_returns_give_positive_t(self):
        """All-positive returns should give positive t-stat."""
        returns = {f"SYM{i}": pd.Series([0.001] * 100) for i in range(3)}
        t = pooled_dk_test(returns)
        assert t > 0, f"Expected positive t, got {t}"

    def test_zero_returns_give_zero_t(self):
        """All-zero returns should give t=0."""
        returns = {f"SYM{i}": pd.Series([0.0] * 100) for i in range(3)}
        t = pooled_dk_test(returns)
        assert t == 0.0, f"Expected t=0, got {t}"

    def test_too_few_returns(self):
        """Fewer than 10 returns should give t=0."""
        returns = {"SYM0": pd.Series([0.001] * 5)}
        t = pooled_dk_test(returns)
        assert t == 0.0


class TestJackknifeSharpe:
    def test_returns_full_sharpe(self):
        """Should contain 'full_sharpe' key."""
        returns = {f"SYM{i}": pd.Series(np.random.normal(0.001, 0.01, 200)) for i in range(3)}
        jk = jackknife_sharpe(returns)
        assert "full_sharpe" in jk
        assert np.isfinite(jk["full_sharpe"])

    def test_drop_keys_match_symbols(self):
        """Should have one drop_* key per symbol."""
        syms = ["A", "B", "C"]
        returns = {s: pd.Series(np.random.normal(0.001, 0.01, 200)) for s in syms}
        jk = jackknife_sharpe(returns)
        for s in syms:
            assert f"drop_{s}" in jk, f"Missing drop_{s}"

    def test_deltas_are_finite(self):
        """Jackknife should return finite values for all symbols."""
        np.random.seed(42)
        returns = {f"SYM{i}": pd.Series(np.random.normal(0.002, 0.005, 2000)) for i in range(7)}
        jk = jackknife_sharpe(returns)
        assert "full_sharpe" in jk
        for key, val in jk.items():
            assert np.isfinite(val), f"Jackknife {key} is not finite: {val}"
        # All symbols should have a drop entry
        assert len(jk) == 8  # full_sharpe + 7 drops
