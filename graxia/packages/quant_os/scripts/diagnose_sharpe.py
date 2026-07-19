"""
Sharpe Ratio Diagnostic — Trace exactly where Sharpe becomes 0.0000

This script runs Liquidity Sweep and instruments the entire metrics pipeline
to identify whether Sharpe=0 is:
  (a) A correct result (strategy has no edge)
  (b) A bug in equity curve calculation
  (c) A bug in _extract_returns or _sharpe_ratio
  (d) A bug in the validator's annualization factor
"""

import csv
import math
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant_os.backtest.engine import BacktestConfig, BacktestEngine
from quant_os.backtest.metrics import (
    _extract_returns,
    _sharpe_ratio,
    _std_dev,
)
from quant_os.strategies.liquidity_sweep import LiquiditySweepStrategy


def load_xauusd_d1():
    """Load XAUUSD D1 data."""
    for name in ["XAUUSD_D1_clean.csv", "XAUUSD_D1.csv", "XAUUSD_D1_original.csv"]:
        csv_path = Path(__file__).resolve().parent.parent / "data" / name
        if csv_path.exists():
            break
    else:
        raise FileNotFoundError("No XAUUSD D1 data found")

    data = {"open": [], "high": [], "low": [], "close": [], "volume": []}
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            vol = float(row.get("volume", "0"))
            if vol == 0:
                continue
            data["open"].append(float(row["open"]))
            data["high"].append(float(row["high"]))
            data["low"].append(float(row["low"]))
            data["close"].append(float(row["close"]))
            data["volume"].append(int(vol))
    return data


def generate_timestamps(n_bars):
    """Generate daily timestamps."""
    start = datetime(2007, 1, 2, tzinfo=UTC)
    return [start + timedelta(days=i) for i in range(n_bars)]


def diagnose():
    print("=" * 80)
    print("SHARPE RATIO DIAGNOSTIC")
    print("=" * 80)

    # 1. Load data
    data = load_xauusd_d1()
    timestamps = generate_timestamps(len(data["close"]))
    print(f"\nData: {len(data['close'])} bars")
    print(f"Date range: {timestamps[0].date()} to {timestamps[-1].date()}")

    # 2. Run backtest
    strategy = LiquiditySweepStrategy()
    config = BacktestConfig(
        initial_capital=Decimal("10000"),
        spread_pips=0.3,
        slippage_pips=0.1,
        commission_per_lot=Decimal("0.0"),
        risk_per_trade_bps=100,
        strict_mtf=False,
        enable_swap=False,
    )

    engine = BacktestEngine(config=config)
    engine._symbol = "XAUUSD"  # Fix Bug #1: thread real symbol through engine
    engine.set_strategy(strategy)
    engine.load_data(data, timestamps)
    result = engine.run()

    metrics = result["metrics"]
    trades = result["trades"]

    # 3. Examine trades
    print(f"\n{'='*80}")
    print("TRADE ANALYSIS")
    print(f"{'='*80}")
    print(f"Total trades: {metrics.total_trades}")
    print(f"Winning trades: {metrics.winning_trades}")
    print(f"Losing trades: {metrics.losing_trades}")
    print(f"Win rate: {metrics.win_rate*100:.1f}%")
    print(f"Total PnL: ${metrics.total_pnl:.2f}")
    print(f"Total return: {metrics.total_return_pct:.2f}%")

    if trades:
        pnls = [float(t.pnl) for t in trades]
        print("\nPnL stats:")
        print(f"  Mean PnL: ${np.mean(pnls):.2f}")
        print(f"  Std PnL: ${np.std(pnls):.2f}")
        print(f"  Min PnL: ${min(pnls):.2f}")
        print(f"  Max PnL: ${max(pnls):.2f}")
        print(f"  Sum PnL: ${sum(pnls):.2f}")

        # Return pct from trades
        returns_pct = [float(t.return_pct) for t in trades]
        print("\nReturn % stats:")
        print(f"  Mean: {np.mean(returns_pct):.4f}%")
        print(f"  Std: {np.std(returns_pct):.4f}%")

    # 4. Examine equity curve
    print(f"\n{'='*80}")
    print("EQUITY CURVE ANALYSIS")
    print(f"{'='*80}")
    eq_curve = engine.equity_curve
    print(f"Equity curve length: {len(eq_curve)} bars")

    equities = [p.equity for p in eq_curve]
    print(f"Equity range: ${min(equities):.2f} - ${max(equities):.2f}")
    print(f"Equity start: ${equities[0]:.2f}")
    print(f"Equity end: ${equities[-1]:.2f}")

    # 5. Extract bar-level returns
    bar_returns = _extract_returns(eq_curve)
    print(f"\n{'='*80}")
    print("BAR-LEVEL RETURNS (from equity curve)")
    print(f"{'='*80}")
    print(f"Total bar-level returns: {len(bar_returns)}")
    non_zero = [r for r in bar_returns if r != 0.0]
    print(f"Non-zero returns: {len(non_zero)}")
    if non_zero:
        print(f"  Mean of non-zero: {np.mean(non_zero):.8f}")
        print(f"  Std of non-zero: {np.std(non_zero):.8f}")

    zero_count = sum(1 for r in bar_returns if r == 0.0)
    print(f"Zero returns: {zero_count} ({zero_count/len(bar_returns)*100:.1f}%)")

    avg_ret = np.mean(bar_returns) if bar_returns else 0.0
    std_ret = _std_dev(bar_returns)
    print(f"\nMean bar return: {avg_ret:.10f}")
    print(f"Std bar return: {std_ret:.10f}")

    # 6. Compute Sharpe with different annualization factors
    print(f"\n{'='*80}")
    print("SHARPE COMPUTATION (bar-level)")
    print(f"{'='*80}")
    for bpy in [252, 365, 24_192]:
        sharpe = _sharpe_ratio(bar_returns, 0.0, bpy)
        print(f"  bars_per_year={bpy:6d}: Sharpe={sharpe:.6f}")

    # 7. Compute Sharpe from TRADE-level returns
    print(f"\n{'='*80}")
    print("SHARPE COMPUTATION (trade-level)")
    print(f"{'='*80}")
    trade_returns = []
    for t in trades:
        ret = float(t.return_pct) / 100.0  # Convert % to fraction
        trade_returns.append(ret)

    if trade_returns:
        print(f"Trade returns: {len(trade_returns)}")
        print(f"  Mean: {np.mean(trade_returns):.8f}")
        print(f"  Std: {np.std(trade_returns, ddof=1):.8f}")

        # Annualize by trades_per_year
        n_years = len(data["close"]) / 252.0
        trades_per_year = len(trade_returns) / n_years
        print(f"  Trades/year: {trades_per_year:.1f}")

        ann_factor = int(trades_per_year)
        mean_r = np.mean(trade_returns)
        std_r = np.std(trade_returns, ddof=1)
        sharpe_trade = (mean_r / std_r) * math.sqrt(ann_factor) if std_r > 0 else 0.0
        print(f"  Annualization factor: {ann_factor}")
        print(f"  Sharpe (trade-level): {sharpe_trade:.6f}")

        # Also try with bar-level annualization
        sharpe_trade_252 = (mean_r / std_r) * math.sqrt(252) if std_r > 0 else 0.0
        print(f"  Sharpe (trade-level, 252 ann): {sharpe_trade_252:.6f}")
    else:
        print("  No trades!")

    # 8. What the validator computes
    print(f"\n{'='*80}")
    print("WHAT THE VALIDATOR COMPUTES")
    print(f"{'='*80}")
    print(f"  Baseline Sharpe (bar-level): {metrics.sharpe_ratio:.6f}")
    print(f"  Sortino (bar-level): {metrics.sortino_ratio:.6f}")

    # 9. Check the BARS_PER_YEAR lookup
    print(f"\n{'='*80}")
    print("BARS_PER_YEAR LOOKUP")
    print(f"{'='*80}")
    from quant_os.backtest.metrics import _DEFAULT_BARS_PER_YEAR, BARS_PER_YEAR

    for key, val in BARS_PER_YEAR.items():
        print(f"  {key}: {val}")
    print(f"  Default: {_DEFAULT_BARS_PER_YEAR}")

    # Simulate what engine does: asset_class="_default", timeframe="M15"
    asset_class = "_default"
    timeframe = "M15"
    bars_per_year = BARS_PER_YEAR.get(
        (asset_class, timeframe),
        BARS_PER_YEAR.get(("_default", timeframe), 252),
    )
    print("\n  Engine calls calculate_metrics with no asset_class/timeframe")
    print(f"  Default: asset_class='{asset_class}', timeframe='{timeframe}'")
    print(f"  Resolved bars_per_year: {bars_per_year}")
    print("  EXPECTED for D1 data: 252")

    # 10. ROOT CAUSE HYPOTHESIS
    print(f"\n{'='*80}")
    print("ROOT CAUSE ANALYSIS")
    print(f"{'='*80}")
    print(f"""
The backtest engine's _build_results() calls calculate_metrics() WITHOUT
passing asset_class or timeframe. This defaults to:
  asset_class='_default', timeframe='M15'
  → BARS_PER_YEAR lookup fails for ('_default','M15') → falls back to 252

But the equity curve has ONE point per bar. For D1 data, that's daily returns
annualized by sqrt(252) — which is CORRECT.

The REAL issue is:
  - Bar-level Sharpe = {metrics.sharpe_ratio:.6f}
  - The strategy has {metrics.total_trades} trades across {len(data['close'])} bars
  - {zero_count}/{len(bar_returns)} ({zero_count/len(bar_returns)*100:.1f}%) bars have zero return
  - The {len(non_zero)} non-zero bars carry ALL the PnL signal

If the strategy is break-even, avg bar return ≈ 0, so Sharpe ≈ 0.

Key question: IS the strategy break-even?
  Total PnL: ${metrics.total_pnl:.2f}
  Profit Factor: {metrics.profit_factor:.2f}
""")

    if metrics.profit_factor > 0.95 and metrics.profit_factor < 1.05:
        print("  >>> PROFIT FACTOR ≈ 1.0 — strategy is BREAK-EVEN. Sharpe=0 is CORRECT.")
    elif metrics.profit_factor > 1.05:
        print("  >>> PROFIT FACTOR > 1 — strategy has positive edge.")
        print("     Sharpe should NOT be zero. INVESTIGATE BUG.")
    else:
        print("  >>> PROFIT FACTOR < 1 — strategy loses money.")
        print("     Sharpe should be NEGATIVE, not zero. INVESTIGATE BUG.")


if __name__ == "__main__":
    diagnose()
