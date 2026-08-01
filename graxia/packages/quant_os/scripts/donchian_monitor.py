"""
Donchian BTCUSD H1 — Performance Monitor

Compares live paper trading results against sacred holdout baseline.
Reads trades.jsonl and produces comparison reports.

Usage:
    python scripts/donchian_monitor.py              # one-shot report
    python scripts/donchian_monitor.py --watch      # live update every 5min
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
os.chdir(_project_root)
sys.path.insert(0, str(_project_root))

import numpy as np

LOG_DIR = _project_root / "logs" / "donchian_paper"
REPORTS_DIR = _project_root / "reports" / "paper_engine"

BASELINE = {
    "sharpe": 2.5706,
    "total_return_pct": 57.1,
    "max_dd_pct": 9.1,
    "win_rate": 50.8,
    "expectancy": 226.54,
    "profit_factor": 1.42,
    "tpy": 261.8,
    "avg_trade_duration_hrs": 33.5,
    "holdout_trades": 252,
}


def load_trades() -> list[dict]:
    """Load all trades from JSONL log."""
    trade_file = LOG_DIR / "trades.jsonl"
    if not trade_file.exists():
        return []
    trades = []
    with open(trade_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                trades.append(json.loads(line))
    return trades


def compute_live_metrics(trades: list[dict], capital: float = 100000) -> dict:
    """Compute metrics from live trade log."""
    if not trades:
        return {"trades": 0}

    pnls = np.array([t["pnl"] for t in trades])
    returns = pnls / capital

    total = len(pnls)
    wins = int(np.sum(pnls > 0))
    losses = int(np.sum(pnls <= 0))
    win_rate = wins / total * 100 if total > 0 else 0

    avg_win = float(np.mean(pnls[pnls > 0])) if wins > 0 else 0
    avg_loss = float(np.mean(pnls[pnls <= 0])) if losses > 0 else 0

    gross_profit = float(np.sum(pnls[pnls > 0])) if wins > 0 else 0
    gross_loss = abs(float(np.sum(pnls[pnls <= 0]))) if losses > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    expectancy = win_rate / 100 * avg_win + (1 - win_rate / 100) * avg_loss

    # Drawdown
    cumulative = np.cumsum(pnls)
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = running_max - cumulative
    max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0
    max_dd_pct = max_dd / capital * 100

    # Sharpe (annualized, assume H1 = ~6096 bars/year)
    mean_ret = float(np.mean(returns))
    std_ret = float(np.std(returns))
    bars_per_year = 6096
    sharpe = mean_ret / std_ret * np.sqrt(bars_per_year) if std_ret > 1e-10 else 0

    total_pnl = float(np.sum(pnls))
    total_return_pct = total_pnl / capital * 100

    return {
        "trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "expectancy": round(expectancy, 2),
        "profit_factor": round(profit_factor, 2),
        "sharpe": round(sharpe, 4),
        "total_pnl": round(total_pnl, 2),
        "total_return_pct": round(total_return_pct, 1),
        "max_drawdown": round(max_dd, 2),
        "max_dd_pct": round(max_dd_pct, 1),
    }


def print_comparison(live: dict, baseline: dict = BASELINE):
    """Print live vs baseline comparison."""
    print()
    print("=" * 80)
    print("DONCHIAN BTCUSD H1 — LIVE vs BACKTEST COMPARISON")
    print("=" * 80)
    print()

    if live["trades"] == 0:
        print("  No trades yet.")
        return

    rows = [
        ("Trades", live["trades"], baseline["holdout_trades"], "count"),
        ("Win Rate", f"{live['win_rate']}%", f"{baseline['win_rate']}%", "%"),
        ("Expectancy", f"${live['expectancy']:+,.2f}", f"${baseline['expectancy']:+,.2f}", "$/trade"),
        ("Profit Factor", f"{live['profit_factor']:.2f}", f"{baseline['profit_factor']:.2f}", "ratio"),
        ("Sharpe", f"{live['sharpe']:.4f}", f"{baseline['sharpe']:.4f}", "ratio"),
        ("Total Return", f"{live['total_return_pct']:+.1f}%", f"{baseline['total_return_pct']:+.1f}%", "%"),
        ("Max Drawdown", f"{live['max_dd_pct']:.1f}%", f"{baseline['max_dd_pct']:.1f}%", "%"),
        ("Total P&L", f"${live['total_pnl']:+,.2f}", "—", "$"),
    ]

    print(f"  {'Metric':<20} {'Live':>15} {'Baseline':>15} {'Unit':>10}")
    print("  " + "-" * 65)
    for name, live_val, base_val, unit in rows:
        print(f"  {name:<20} {str(live_val):>15} {str(base_val):>15} {unit:>10}")

    print()

    # Health check
    print("  HEALTH CHECK:")
    checks = []

    # Win rate within 10% of baseline
    wr_diff = abs(live["win_rate"] - baseline["win_rate"])
    wr_ok = wr_diff < 10
    checks.append(("Win rate within 10pp", wr_ok, f"{wr_diff:.1f}pp diff"))

    # PF > 1.0
    pf_ok = live["profit_factor"] > 1.0
    checks.append(("Profit factor > 1.0", pf_ok, f"{live['profit_factor']:.2f}"))

    # DD < 20%
    dd_ok = live["max_dd_pct"] < 20
    checks.append(("Max DD < 20%", dd_ok, f"{live['max_dd_pct']:.1f}%"))

    # Expectancy positive
    exp_ok = live["expectancy"] > 0
    checks.append(("Expectancy > 0", exp_ok, f"${live['expectancy']:+,.2f}"))

    for name, ok, detail in checks:
        status = "PASS" if ok else "WARN"
        print(f"    [{status}] {name}: {detail}")

    all_ok = all(ok for _, ok, _ in checks)
    print()
    print(f"  OVERALL: {'HEALTHY' if all_ok else 'NEEDS ATTENTION'}")
    print()
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Donchian Monitor")
    parser.add_argument("--watch", action="store_true", help="Live update every 5min")
    parser.add_argument("--capital", type=float, default=100000)
    args = parser.parse_args()

    if args.watch:
        print("Watching for new trades... (Ctrl+C to stop)")
        while True:
            trades = load_trades()
            live = compute_live_metrics(trades, args.capital)
            print_comparison(live)
            time.sleep(300)
    else:
        trades = load_trades()
        live = compute_live_metrics(trades, args.capital)
        print_comparison(live)

        # Save comparison report
        report = {"live": live, "baseline": BASELINE, "generated": datetime.now(UTC).isoformat()}
        path = REPORTS_DIR / "live_vs_baseline.json"
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"  Report saved: {path}")


if __name__ == "__main__":
    main()
