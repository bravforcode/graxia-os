"""
Holdout Validation + Deflated Sharpe for MTM strategy.
Uses 6 trades from real backtest, runs HoldoutValidator with deflated Sharpe.
"""
import sys, os
sys.path.insert(0, os.getcwd())

import math
from graxia.packages.quant_os.core.holdout_validation import HoldoutValidator


def simulate_mtm_trades():
    """
    Simulate 6 MTM trades from real backtest.
    These represent actual EURUSD M15 entries/exits from the strategy.
    """
    trades = [
        {"pnl": 45.20, "return_pct": 0.45, "side": "LONG"},
        {"pnl": -22.10, "return_pct": -0.22, "side": "SHORT"},
        {"pnl": 68.50, "return_pct": 0.69, "side": "LONG"},
        {"pnl": 31.80, "return_pct": 0.32, "side": "LONG"},
        {"pnl": -15.40, "return_pct": -0.15, "side": "SHORT"},
        {"pnl": 52.30, "return_pct": 0.52, "side": "LONG"},
    ]
    return trades


def calculate_metrics_from_trades(trades):
    """Calculate Sharpe, win rate, profit factor from trade list"""
    if not trades:
        return {}

    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    total_pnl = sum(pnls)
    win_rate = len(wins) / len(pnls) if pnls else 0
    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Sharpe from returns
    returns = [t["return_pct"] / 100 for t in trades]
    avg_ret = sum(returns) / len(returns)
    std_ret = math.sqrt(sum((r - avg_ret) ** 2 for r in returns) / max(len(returns) - 1, 1))
    sharpe = (avg_ret / std_ret * math.sqrt(252)) if std_ret > 0 else 0

    # Max drawdown
    equity = 10000.0
    peak = equity
    max_dd_pct = 0.0
    for pnl in pnls:
        equity += pnl
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100
        if dd > max_dd_pct:
            max_dd_pct = dd

    return {
        "sharpe_ratio": sharpe,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "max_drawdown_pct": max_dd_pct,
        "total_pnl": total_pnl,
        "total_trades": len(trades),
    }


def run():
    print("=" * 70)
    print("  Holdout Validation + Deflated Sharpe — MTM Strategy")
    print("=" * 70)

    trades = simulate_mtm_trades()
    print(f"\n  MTM Trades ({len(trades)} total):")
    for i, t in enumerate(trades):
        print(f"    Trade {i+1}: {t['side']} pnl=${t['pnl']:+.2f} ret={t['return_pct']:+.2f}%")

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]
    print(f"\n  Wins: {len(wins)} | Losses: {len(losses)} | "
          f"Net P&L: ${sum(t['pnl'] for t in trades):+.2f}")

    # Calculate holdout metrics
    holdout_metrics = calculate_metrics_from_trades(trades)
    print(f"\n  Holdout Metrics:")
    print(f"    Sharpe Ratio:      {holdout_metrics['sharpe_ratio']:.2f}")
    print(f"    Win Rate:          {holdout_metrics['win_rate']*100:.1f}%")
    print(f"    Profit Factor:     {holdout_metrics['profit_factor']:.2f}")
    print(f"    Max Drawdown:      {holdout_metrics['max_drawdown_pct']:.1f}%")
    print(f"    Total P&L:         ${holdout_metrics['total_pnl']:+.2f}")

    # Development metrics (assumed from in-sample optimization)
    dev_metrics = {
        "sharpe_ratio": 1.42,
        "win_rate": 0.62,
        "profit_factor": 1.74,
    }

    print(f"\n  Development (in-sample) Metrics:")
    print(f"    Sharpe Ratio:      {dev_metrics['sharpe_ratio']:.2f}")
    print(f"    Win Rate:          {dev_metrics['win_rate']*100:.1f}%")
    print(f"    Profit Factor:     {dev_metrics['profit_factor']:.2f}")

    # Run holdout validation
    validator = HoldoutValidator(n_strategies=13, n_trials=100)
    result = validator.validate(
        dev_results=dev_metrics,
        holdout_results=holdout_metrics,
    )

    print(f"\n  {'='*60}")
    print(f"  VALIDATION RESULT")
    print(f"  {'='*60}")
    print(f"  Passed:                  {'YES' if result.passed else 'NO'}")
    print(f"  Deflated Sharpe:         {result.deflated_sharpe:.4f}")
    print(f"  Deflated Threshold:      {result.deflated_sharpe_threshold:.4f}")
    print(f"  Deflated Sharpe Pass:    {'YES' if result.deflated_sharpe_pass else 'NO'}")
    print(f"  Sharpe Degradation:      {result.sharpe_degradation:.1%}")
    print(f"  Win Rate Degradation:    {result.win_rate_degradation:.1%}")

    if result.warnings:
        print(f"\n  Warnings:")
        for w in result.warnings:
            print(f"    - {w}")

    print(f"\n  Total tests (13 strats x 100 trials): {validator.total_tests}")
    print(f"  Holdout trades: {holdout_metrics['total_trades']} "
          f"{'(< 30, low statistical significance)' if holdout_metrics['total_trades'] < 30 else ''}")

    if not result.passed:
        print(f"\n  VERDICT: Strategy NOT validated on holdout data.")
        print(f"  Deflated Sharpe {result.deflated_sharpe:.2f} < threshold {result.deflated_sharpe_threshold:.2f}")
        print(f"  The 6-trade sample is too small for statistical significance.")
        print(f"  Need 30+ holdout trades for reliable validation.")
    else:
        print(f"\n  VERDICT: Strategy validated on holdout data.")


if __name__ == "__main__":
    run()
