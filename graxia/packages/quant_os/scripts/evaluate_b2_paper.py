#!/usr/bin/env python3
"""
B2 Paper Trade Evaluation — Block Bootstrap
============================================
Reads data/paper_trade_log.csv and evaluates against 3 locked criteria:
  1. avg_net ≥ $0.40
  2. win_rate ≥ 0.55
  3. t-stat ≥ 2.0 (block bootstrap 95% CI)

Usage: python scripts/evaluate_b2_paper.py [--csv PATH]
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent.parent
CSV_DEFAULT = BASE / "data" / "paper_trade_log.csv"
REPORT_PATH = BASE / "reports" / "b2_paper_evaluation.json"

# Locked criteria from pre_register_b2.md
CRITERIA = {
    "avg_net": 0.40,     # minimum $ per trade
    "win_rate": 0.55,    # minimum win rate
    "t_stat": 2.0,       # minimum t-statistic
}


def load_trades(csv_path: Path) -> list[dict]:
    """Load closed trades from CSV."""
    trades = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Only include trades with exit_price (closed trades)
            if row.get("exit_price", "").strip():
                try:
                    row["pnl_net"] = float(row.get("pnl_net", 0) or 0)
                    trades.append(row)
                except (ValueError, KeyError):
                    continue
    return trades


def block_bootstrap_ci(values: np.ndarray, n_boot: int = 10000,
                       block_size: int = 5, ci: float = 0.95) -> dict:
    """Block bootstrap for mean CI and t-statistic."""
    n = len(values)
    if n < block_size:
        block_size = max(1, n // 2)

    boot_means = []
    for _ in range(n_boot):
        blocks_needed = (n + block_size - 1) // block_size
        indices = []
        for _ in range(blocks_needed):
            start = np.random.randint(0, max(1, n - block_size + 1))
            indices.extend(range(start, min(start + block_size, n)))
        indices = indices[:n]
        boot_means.append(values[indices].mean())

    boot_means = np.array(boot_means)
    alpha = 1 - ci
    ci_lower = np.percentile(boot_means, 100 * alpha / 2)
    ci_upper = np.percentile(boot_means, 100 * (1 - alpha / 2))

    observed_mean = values.mean()
    observed_std = values.std(ddof=1)
    se = observed_std / np.sqrt(n)
    t_stat = observed_mean / se if se > 0 else 0.0

    return {
        "mean": float(observed_mean),
        "std": float(observed_std),
        "n": n,
        "ci_lower": float(ci_lower),
        "ci_upper": float(ci_upper),
        "t_stat": float(t_stat),
    }


def evaluate(csv_path: Path) -> dict:
    """Run full evaluation and return results."""
    trades = load_trades(csv_path)
    if not trades:
        return {"error": "No closed trades found", "trades": 0}

    pnl_values = np.array([t["pnl_net"] for t in trades])

    # Criterion 1: avg_net
    avg_net = float(pnl_values.mean())

    # Criterion 2: win_rate
    wins = (pnl_values > 0).sum()
    win_rate = float(wins / len(pnl_values))

    # Criterion 3: t-stat via block bootstrap
    bootstrap = block_bootstrap_ci(pnl_values)
    t_stat = bootstrap["t_stat"]

    # Verdict
    pass_avg = avg_net >= CRITERIA["avg_net"]
    pass_wr = win_rate >= CRITERIA["win_rate"]
    pass_t = t_stat >= CRITERIA["t_stat"]
    verdict = "PASS" if (pass_avg and pass_wr and pass_t) else "FAIL"

    # Contingency analysis
    contingency = ""
    if verdict == "FAIL":
        if not pass_avg and pass_wr:
            contingency = "Gap risk exceeded estimate. Next: stop at $7.00, repeat 4-week paper."
        elif not pass_wr:
            contingency = "Accuracy failure structural. Requires feature redesign. B2 alone dead."

    results = {
        "csv": str(csv_path),
        "total_trades": len(trades),
        "closed_trades": len(trades),
        "avg_net": round(avg_net, 4),
        "win_rate": round(win_rate, 4),
        "wins": int(wins),
        "losses": int(len(pnl_values) - wins),
        "total_pnl": round(float(pnl_values.sum()), 2),
        "t_stat": round(t_stat, 4),
        "bootstrap_ci_95": [round(bootstrap["ci_lower"], 4), round(bootstrap["ci_upper"], 4)],
        "criteria": CRITERIA,
        "pass_avg_net": pass_avg,
        "pass_win_rate": pass_wr,
        "pass_t_stat": pass_t,
        "verdict": verdict,
        "contingency": contingency,
    }
    return results


def main():
    parser = argparse.ArgumentParser(description="B2 Paper Trade Evaluation")
    parser.add_argument("--csv", type=Path, default=CSV_DEFAULT, help="Path to trade log CSV")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"ERROR: CSV not found: {args.csv}", file=sys.stderr)
        sys.exit(1)

    results = evaluate(args.csv)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print("=" * 60)
        print("B2 PAPER TRADE EVALUATION")
        print("=" * 60)
        print(f"Total trades:    {results.get('total_trades', 0)}")
        print(f"Avg net/trade:   ${results.get('avg_net', 0):.2f}  (≥ $0.40? {'✅' if results.get('pass_avg_net') else '❌'})")
        print(f"Win rate:        {results.get('win_rate', 0)*100:.1f}%  (≥ 55%? {'✅' if results.get('pass_win_rate') else '❌'})")
        print(f"t-statistic:     {results.get('t_stat', 0):.2f}  (≥ 2.0? {'✅' if results.get('pass_t_stat') else '❌'})")
        print(f"Total PnL:       ${results.get('total_pnl', 0):.2f}")
        print(f"95% CI:          [{results.get('bootstrap_ci_95', [0,0])[0]:.2f}, {results.get('bootstrap_ci_95', [0,0])[1]:.2f}]")
        print("-" * 60)
        verdict = results.get("verdict", "UNKNOWN")
        icon = "🟢" if verdict == "PASS" else "🔴"
        print(f"VERDICT: {icon} {verdict}")
        if results.get("contingency"):
            print(f"Contingency: {results['contingency']}")
        print("=" * 60)

    # Save report
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    if not args.json:
        print(f"\nReport saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()
