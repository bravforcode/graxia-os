"""Regression test: cost unit must be return-units, with broker-realistic bounds.

Two test suites:
1. compute_fold_pnl (walk_forward.py) — existing tests for unit consistency
2. compute_trade_pnl (backtest_cost.py) — new tests for per-trade cost with actual prices
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from backtest_cost import compute_trade_pnl
from walk_forward import compute_fold_pnl


def _check_cost_sanity(spread_cost: float, slippage: float, label: str = ""):
    """Run compute_fold_pnl with synthetic data and assert cost/trade is $0.01-$5."""
    n = 100
    returns = np.random.default_rng(42).normal(0, 0.001, n).astype(np.float64)
    preds = np.random.default_rng(99).integers(0, 2, n).astype(np.float64)
    confs = np.full(n, 0.95, dtype=np.float64)

    close_prices = np.full(n, 2350.0, dtype=np.float64)
    result = compute_fold_pnl(
        returns,
        preds,
        confs,
        spread_cost=spread_cost,
        slippage_p90=slippage,
        min_confidence=0.5,
        close_prices=close_prices,
    )

    n_trades = result["n_trades"]
    total_cost = result["total_cost"]
    cost_per_trade = total_cost / n_trades if n_trades > 0 else 0.0

    # Expected: cost_per_trade = (spread_cost + slippage) * 2350
    expected = (spread_cost + slippage) * 2350.0

    msg = (
        f"[{label}] cost/trade ${cost_per_trade:.6f} "
        f"vs expected ${expected:.6f} (spread={spread_cost}, slippage={slippage})"
    )

    # Sanity bounds: $0.01 to $5.00 per trade for realistic params
    assert 0.01 <= cost_per_trade <= 5.0, (
        f"COST UNIT BUG: {msg}. "
        f"If cost/trade ≈ {cost_per_trade:.6f} (same magnitude as spread_cost={spread_cost}), "
        f"the *2350 multiplier is missing."
    )
    # Exact check: should be within float rounding of expected
    assert abs(cost_per_trade - expected) < 0.001, f"COST VALUE BUG: {msg}"
    return result


def test_cost_sanity_xauusd():
    """XAUUSD calibrated cost: spread=0.0001, slippage=0.000047 → $0.345/trade."""
    _check_cost_sanity(0.000100, 0.000047, "XAUUSD")


def test_cost_sanity_eurusd():
    """EURUSD calibrated cost: spread=0.000022, slippage=0.000004 → $0.061/trade."""
    _check_cost_sanity(0.000022, 0.000004, "EURUSD")


def test_cost_sanity_old_default():
    """Old conservative default: 0.0002 + 0.0001 → $0.705/trade."""
    _check_cost_sanity(0.000200, 0.000100, "old-default")


def test_cost_sanity_lowest():
    """Low realistic: 0.00001 + 0.000005 → $0.035/trade — still >= $0.01."""
    _check_cost_sanity(0.000010, 0.000005, "low-bound")


def test_cost_sanity_highest():
    """High realistic: 0.0005 + 0.0005 → $2.35/trade — still <= $5.00."""
    _check_cost_sanity(0.000500, 0.000500, "high-bound")


def test_cost_sanity_zero_trades():
    """Zero trades should return zero cost without crashing."""
    result = compute_fold_pnl(
        np.array([0.001], dtype=np.float64),
        np.array([1.0], dtype=np.float64),
        np.array([0.1], dtype=np.float64),  # conf < 0.5 → no trades
        spread_cost=0.0001,
        slippage_p90=0.00005,
        min_confidence=0.5,
        close_prices=np.array([2350.0], dtype=np.float64),
    )
    assert result["n_trades"] == 0
    assert result["total_cost"] == 0.0
    assert result["net_pnl"] == 0.0


# ============================================================
# compute_trade_pnl tests (backtest_cost.py)
# ============================================================


def _make_trade_df(n=100, close_price=2350.0):
    """Create synthetic feature dataframe with target_return and close."""
    rng = np.random.default_rng(42)
    df = pd.DataFrame(
        {
            "target_return": rng.normal(0, 0.001, n),
            "target": rng.integers(0, 2, n),
            "close": np.full(n, close_price),
        }
    )
    preds = rng.integers(0, 2, n).astype(float)
    return df, preds


def test_trade_pnl_uses_per_trade_price():
    """compute_trade_pnl must use actual close prices, not flat 2350."""
    df, preds = _make_trade_df(n=10, close_price=4000.0)
    result = compute_trade_pnl(
        df,
        preds,
        spread_cost=0.00005,
        slippage_p90=0.000027,
        lot_mult=1.0,
        close_prices=df["close"].values,
    )
    # cost_per_trade should be (0.00005+0.000027)*4000 = $0.308
    expected_cost = (0.00005 + 0.000027) * 4000.0
    actual_cost = result["cost_dollars"].iloc[0]
    assert (
        abs(actual_cost - expected_cost) < 0.001
    ), f"Per-trade cost ${actual_cost:.6f} != expected ${expected_cost:.6f} at price $4000"


def test_trade_pnl_flat_price_fallback():
    """Without close_prices, should fall back to 2350.0."""
    df, preds = _make_trade_df(n=10, close_price=4000.0)
    result = compute_trade_pnl(
        df,
        preds,
        spread_cost=0.00005,
        slippage_p90=0.000027,
        lot_mult=1.0,
        close_prices=None,
    )
    # cost_per_trade should be (0.00005+0.000027)*2350 = $0.181
    expected_cost = (0.00005 + 0.000027) * 2350.0
    actual_cost = result["cost_dollars"].iloc[0]
    assert (
        abs(actual_cost - expected_cost) < 0.001
    ), f"Fallback cost ${actual_cost:.6f} != expected ${expected_cost:.6f}"


def test_trade_pnl_broker_realistic_bounds():
    """0.01 lot XAUUSD cost per trade must be $0.05-$2.00 (broker-realistic)."""
    df, preds = _make_trade_df(n=100, close_price=2350.0)
    result = compute_trade_pnl(
        df,
        preds,
        spread_cost=0.00005,
        slippage_p90=0.000027,
        lot_mult=1.0,
        close_prices=df["close"].values,
    )
    cost_per_trade = result["cost_dollars"].mean()
    assert 0.05 <= cost_per_trade <= 2.0, f"Cost ${cost_per_trade:.4f}/trade outside broker-realistic range $0.05-$2.00"


def test_trade_pnl_cost_scales_with_price():
    """Cost must scale with actual price: $4000 → higher cost than $2350."""
    df1, preds1 = _make_trade_df(n=10, close_price=2350.0)
    df2, preds2 = _make_trade_df(n=10, close_price=4000.0)

    r1 = compute_trade_pnl(df1, preds1, 0.00005, 0.000027, 1.0, df1["close"].values)
    r2 = compute_trade_pnl(df2, preds2, 0.00005, 0.000027, 1.0, df2["close"].values)

    cost_2350 = r1["cost_dollars"].mean()
    cost_4000 = r2["cost_dollars"].mean()

    # Cost at $4000 should be ~1.7x cost at $2350
    ratio = cost_4000 / cost_2350
    assert 1.6 < ratio < 1.8, f"Cost ratio {ratio:.2f} should be ~1.7 (4000/2350)"


def test_trade_pnl_net_equals_gross_minus_cost():
    """net_pnl must equal raw_pnl_dollars - cost_dollars for every row."""
    df, preds = _make_trade_df(n=50, close_price=2350.0)
    result = compute_trade_pnl(df, preds, 0.00005, 0.000027, 1.0, df["close"].values)

    diff = result["net_pnl_dollars"] - (result["raw_pnl_dollars"] - result["cost_dollars"])
    assert abs(diff).max() < 1e-10, "net_pnl != raw_pnl - cost for some rows"


if __name__ == "__main__":
    # Run all standalone
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print(f"  PASS {name}")
            except Exception as e:
                print(f"  FAIL {name}: {e}")
                sys.exit(1)
    print("\nAll cost sanity checks passed.")
