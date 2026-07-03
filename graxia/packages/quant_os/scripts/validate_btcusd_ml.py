#!/usr/bin/env python3
"""
BTCUSD ML Paper Trade Validator — Live performance analysis.
===========================================================================
Reads the paper trade log and computes:
  - Win rate, avg return, Sharpe after costs
  - Confusion matrix (predicted vs actual)
  - Whether recall_0 > 0.20 maintained in live
  - Comparison with backtest metrics

Log: data/btcusd_ml_paper_log.csv

Usage:
    python scripts/validate_btcusd_ml.py
    python scripts/validate_btcusd_ml.py --log data/btcusd_ml_paper_log.csv
    python scripts/validate_btcusd_ml.py --days 7
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

DEFAULT_LOG = BASE / "data" / "btcusd_ml_paper_log.csv"
REPORT_DIR = BASE / "reports" / "btcusd_ml"

# Backtest reference metrics (from v2 gate)
BACKTEST_METRICS = {
    "balanced_acc": 0.5228,
    "recall_0": 0.41,
    "recall_1": 0.64,
    "precision_0": 0.46,
    "precision_1": 0.59,
}


def load_log(path: Path, days: int | None = None) -> pd.DataFrame:
    """Load paper trade log CSV."""
    if not path.exists():
        print(f"Log file not found: {path}")
        print("No paper trades yet. Start the paper trader first:")
        print("  python scripts/paper_trade_btcusd_ml.py")
        sys.exit(1)

    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    if days:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        df = df[df["timestamp"] >= cutoff]

    return df


def pair_trades(df: pd.DataFrame) -> pd.DataFrame:
    """Pair entry and exit trades into round-trip trades.

    Looks for:
    - Entry rows: have probability, no pnl
    - Close/reversal rows: have pnl or notes='reversal_close'
    """
    # Separate entries and exits
    entries = df[df["pnl"].isna() | (df["pnl"] == "")].copy()
    exits = df[df["pnl"].notna() & (df["pnl"] != "")].copy()

    if exits.empty:
        # No completed trades yet — try to pair by position tracking
        return _pair_by_sequence(df)

    # Match entries to exits by direction sequence
    trades = []
    open_entry = None

    for _, row in df.sort_values("timestamp").iterrows():
        is_entry = pd.isna(row.get("pnl")) or row.get("pnl") == ""
        is_exit = not is_entry

        if is_entry and open_entry is None:
            open_entry = row
        elif is_exit and open_entry is not None:
            trades.append(
                {
                    "entry_time": open_entry["timestamp"],
                    "exit_time": row["timestamp"],
                    "direction": open_entry["direction"],
                    "entry_price": float(open_entry["entry_price"]),
                    "exit_price": float(row.get("entry_price", 0)),  # exit price stored in entry_price for close rows
                    "lot_size": float(open_entry["lot_size"]),
                    "probability": float(open_entry["probability"]),
                    "pnl": float(row["pnl"]) if row["pnl"] else 0.0,
                    "spread": float(open_entry.get("spread", 0)),
                    "atr_14": float(open_entry.get("atr_14", 0)),
                    "notes": str(row.get("notes", "")),
                }
            )
            open_entry = None

    if not trades:
        return _pair_by_sequence(df)

    return pd.DataFrame(trades)


def _pair_by_sequence(df: pd.DataFrame) -> pd.DataFrame:
    """Fallback: pair consecutive rows as entry/exit."""
    trades = []
    df_sorted = df.sort_values("timestamp").reset_index(drop=True)

    i = 0
    while i < len(df_sorted) - 1:
        entry = df_sorted.iloc[i]
        exit_row = df_sorted.iloc[i + 1]

        if exit_row.get("notes", "") == "reversal_close":
            pnl_val = exit_row.get("pnl", 0)
            trades.append(
                {
                    "entry_time": entry["timestamp"],
                    "exit_time": exit_row["timestamp"],
                    "direction": entry["direction"],
                    "entry_price": float(entry["entry_price"]),
                    "exit_price": float(exit_row.get("entry_price", 0)),
                    "lot_size": float(entry["lot_size"]),
                    "probability": float(entry["probability"]),
                    "pnl": float(pnl_val) if pnl_val and pnl_val != "" else 0.0,
                    "spread": float(entry.get("spread", 0)),
                    "atr_14": float(entry.get("atr_14", 0)),
                    "notes": str(exit_row.get("notes", "")),
                }
            )
            i += 2
        else:
            i += 1

    return pd.DataFrame(trades)


def compute_returns(trades: pd.DataFrame) -> pd.DataFrame:
    """Compute per-trade returns."""
    if trades.empty:
        return trades

    trades = trades.copy()
    # Return as fraction of entry price
    trades["return_pct"] = np.where(
        trades["direction"].str.lower() == "buy",
        (trades["exit_price"] - trades["entry_price"]) / trades["entry_price"].replace(0, np.nan),
        (trades["entry_price"] - trades["exit_price"]) / trades["entry_price"].replace(0, np.nan),
    )
    # PnL per unit
    trades["pnl_per_lot"] = trades["pnl"] / trades["lot_size"].replace(0, np.nan)
    return trades


def compute_confusion_matrix(trades: pd.DataFrame) -> dict:
    """Compute confusion matrix: predicted direction vs actual outcome.

    Class 0 = sell/hold (model predicted class 0)
    Class 1 = buy (model predicted class 1)
    Actual: win=correct direction, lose=wrong direction
    """
    if trades.empty:
        return {}

    # Predicted: from probability
    # If prob > 0.5 → predicted buy (1), else predicted sell (0)
    trades = trades.copy()
    trades["predicted"] = (trades["probability"] > 0.5).astype(int)
    trades["actual"] = (trades["pnl"] > 0).astype(int)  # 1=win, 0=loss

    # Confusion matrix: predicted × actual
    tp = int(((trades["predicted"] == 1) & (trades["actual"] == 1)).sum())
    fp = int(((trades["predicted"] == 1) & (trades["actual"] == 0)).sum())
    tn = int(((trades["predicted"] == 0) & (trades["actual"] == 0)).sum())
    fn = int(((trades["predicted"] == 0) & (trades["actual"] == 1)).sum())

    total = tp + fp + tn + fn
    if total == 0:
        return {}

    accuracy = (tp + tn) / total
    recall_1 = tp / (tp + fn) if (tp + fn) > 0 else 0  # sensitivity (buy accuracy)
    recall_0 = tn / (tn + fp) if (tn + fp) > 0 else 0  # specificity (sell accuracy)
    precision_1 = tp / (tp + fp) if (tp + fp) > 0 else 0
    precision_0 = tn / (tn + fn) if (tn + fn) > 0 else 0
    balanced_acc = (recall_0 + recall_1) / 2

    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "total": total,
        "accuracy": accuracy,
        "recall_0": recall_0,
        "recall_1": recall_1,
        "precision_0": precision_0,
        "precision_1": precision_1,
        "balanced_acc": balanced_acc,
    }


def compute_sharpe(trades: pd.DataFrame, periods_per_year: int = 96 * 252) -> float:
    """Annualized Sharpe ratio from trade returns."""
    if trades.empty or "return_pct" not in trades.columns:
        return 0.0
    rets = trades["return_pct"].dropna()
    if len(rets) < 2 or rets.std() == 0:
        return 0.0
    # Annualize: trades are per-bar, 96 bars/day, 252 days/year
    # But trades are sparse, so use actual trade count
    mean_ret = rets.mean()
    std_ret = rets.std()
    n_trades = len(rets)
    # Approximate annualization
    trades_per_year = periods_per_year / max(n_trades, 1)
    sharpe = mean_ret / std_ret * np.sqrt(min(n_trades, trades_per_year))
    return sharpe


def compute_cost_analysis(trades: pd.DataFrame) -> dict:
    """Estimate trading costs."""
    if trades.empty:
        return {}

    avg_spread = trades["spread"].mean() if "spread" in trades.columns else 0
    total_spread_cost = (trades["spread"] * trades["lot_size"]).sum() if "spread" in trades.columns else 0
    gross_pnl = trades["pnl"].sum()
    net_pnl = gross_pnl  # spread already in MT5 fill prices

    return {
        "total_trades": len(trades),
        "avg_spread": avg_spread,
        "total_spread_cost_est": total_spread_cost,
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
    }


def generate_report(
    trades: pd.DataFrame,
    cm: dict,
    sharpe: float,
    costs: dict,
    days: int | None,
) -> str:
    """Generate markdown validation report."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    period = f"Last {days} days" if days else "All time"

    lines = [
        "# BTCUSD ML Paper Trading Validation",
        f"Generated: {now}",
        f"Period: {period}",
        "",
        "## Summary",
        "",
    ]

    if trades.empty:
        lines.append("**No completed trades yet.** Run the paper trader to generate data.")
        lines.append("")
        lines.append("```")
        lines.append("python scripts/paper_trade_btcusd_ml.py")
        lines.append("```")
        return "\n".join(lines)

    # Trade stats
    wins = (trades["pnl"] > 0).sum()
    losses = (trades["pnl"] < 0).sum()
    breakeven = (trades["pnl"] == 0).sum()
    win_rate = wins / len(trades) if len(trades) > 0 else 0
    avg_win = trades[trades["pnl"] > 0]["pnl"].mean() if wins > 0 else 0
    avg_loss = trades[trades["pnl"] < 0]["pnl"].mean() if losses > 0 else 0
    profit_factor = abs(wins * avg_win / (losses * avg_loss)) if losses > 0 and avg_loss != 0 else float("inf")

    lines.extend(
        [
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total trades | {len(trades)} |",
            f"| Wins / Losses / BE | {wins} / {losses} / {breakeven} |",
            f"| Win rate | {win_rate:.1%} |",
            f"| Avg win | ${avg_win:+.2f} |",
            f"| Avg loss | ${avg_loss:+.2f} |",
            f"| Profit factor | {profit_factor:.2f} |",
            f"| Total PnL | ${costs.get('net_pnl', 0):+.2f} |",
            f"| Avg spread | ${costs.get('avg_spread', 0):.2f} |",
            f"| Sharpe (est) | {sharpe:.3f} |",
            "",
        ]
    )

    # Confusion matrix
    if cm:
        lines.extend(
            [
                "## Confusion Matrix (Predicted vs Actual)",
                "",
                "| | Actual Win | Actual Loss |",
                "|--|-----------|-------------|",
                f"| **Predicted Buy** | TP={cm['tp']} | FP={cm['fp']} |",
                f"| **Predicted Sell** | FN={cm['fn']} | TN={cm['tn']} |",
                "",
                "## Live vs Backtest",
                "",
                "| Metric | Backtest | Live | Delta | Status |",
                "|--------|----------|------|-------|--------|",
            ]
        )

        for metric, bt_val in BACKTEST_METRICS.items():
            live_val = cm.get(metric, 0)
            delta = live_val - bt_val
            if metric == "recall_0":
                status = "✅ PASS" if live_val > 0.20 else "❌ FAIL (< 0.20)"
            elif metric == "balanced_acc":
                status = "✅ OK" if live_val > 0.50 else "⚠️ DEGRADED"
            else:
                status = "✅" if delta >= -0.05 else "⚠️"
            lines.append(f"| {metric} | {bt_val:.4f} | {live_val:.4f} | {delta:+.4f} | {status} |")

        lines.extend(
            [
                "",
                "## Recall-0 Live Check",
                "",
                f"Backtest recall_0: {BACKTEST_METRICS['recall_0']:.4f}",
                f"Live recall_0: {cm['recall_0']:.4f}",
                "",
            ]
        )

        if cm["recall_0"] > 0.20:
            lines.append("**✅ PASS** — recall_0 > 0.20 maintained in live trading.")
        else:
            lines.append("**❌ FAIL** — recall_0 dropped below 0.20. Model may be degenerate in live.")
            lines.append("")
            lines.append("Recommended actions:")
            lines.append("1. Check if feature distribution shifted")
            lines.append("2. Verify live features match training features")
            lines.append("3. Consider retraining with recent data")

    lines.extend(
        [
            "",
            "## Per-Trade Log (last 20)",
            "",
        ]
    )

    if len(trades) > 0:
        display_cols = ["entry_time", "direction", "entry_price", "exit_price", "probability", "pnl", "return_pct"]
        available_cols = [c for c in display_cols if c in trades.columns]
        tail = trades[available_cols].tail(20).copy()
        for col in tail.columns:
            if tail[col].dtype == float:
                tail[col] = tail[col].map(lambda x: f"{x:.4f}" if abs(x) < 1 else f"{x:.2f}")
        lines.append(tail.to_markdown(index=False))

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="BTCUSD ML Paper Trade Validator")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG, help="Path to paper trade log CSV")
    parser.add_argument("--days", type=int, default=None, help="Limit analysis to last N days")
    parser.add_argument("--output", type=Path, default=None, help="Output report path")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of markdown")
    args = parser.parse_args()

    print(f"Loading log: {args.log}")
    df = load_log(args.log, days=args.days)
    print(f"  {len(df)} log entries")

    trades = pair_trades(df)
    print(f"  {len(trades)} paired trades")

    if not trades.empty:
        trades = compute_returns(trades)

    cm = compute_confusion_matrix(trades)
    sharpe = compute_sharpe(trades)
    costs = compute_cost_analysis(trades)

    if args.json:
        output = {
            "trades": len(trades),
            "confusion_matrix": cm,
            "sharpe": sharpe,
            "costs": costs,
            "backtest_reference": BACKTEST_METRICS,
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        report = generate_report(trades, cm, sharpe, costs, args.days)
        print(report)

        # Save report
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = args.output or (REPORT_DIR / f"validation_{datetime.now(UTC).strftime('%Y%m%d_%H%M')}.md")
        out_path.write_text(report)
        print(f"\nReport saved: {out_path}")


if __name__ == "__main__":
    main()
