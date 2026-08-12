"""Pipeline 9: Signal Quality Tracker → Vault

Reads signal history and trade outcomes from quant_os/data,
compares signals vs actual trade outcomes, and generates
Obsidian vault notes with accuracy analysis.
"""

import csv
import json
import re
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# Paths
DATA_DIR = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os\data")
TRADE_LOG = DATA_DIR / "paper_trade_log.csv"
SESSION_JSON = DATA_DIR / "paper_trade_session.json"
VAULT_DIR = Path(
    r"C:\Users\menum\Documents\ObsidianVault\Second Brain\03-resources\trading\signals"
)


def parse_confidence_from_notes(notes: str) -> float | None:
    """Extract confidence value from trade notes like 'Open conf=0.50 ticket=...'"""
    match = re.search(r"conf=([\d.]+)", notes)
    return float(match.group(1)) if match else None


def parse_direction(notes: str) -> str | None:
    """Extract direction hint from notes if present"""
    notes_lower = notes.lower()
    if "long" in notes_lower or "buy" in notes_lower:
        return "long"
    if "short" in notes_lower or "sell" in notes_lower:
        return "short"
    return None


def load_trade_log() -> list[dict]:
    """Load and parse paper_trade_log.csv"""
    trades = []
    if not TRADE_LOG.exists():
        return trades
    with open(TRADE_LOG, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            trades.append(row)
    return trades


def load_session() -> dict:
    """Load paper_trade_session.json"""
    if not SESSION_JSON.exists():
        return {}
    with open(SESSION_JSON, "r") as f:
        return json.load(f)


def classify_trade(row: dict) -> dict[str, Any]:
    """Classify a trade row into signal-outcome pair"""
    direction = row.get("direction", "").strip()
    confidence = parse_confidence_from_notes(row.get("notes", ""))
    exit_price = row.get("exit_price", "").strip()
    pnl_net = row.get("pnl_net", "").strip()
    exit_reason = row.get("exit_reason", "").strip()

    # Determine outcome
    outcome = "pending"
    if pnl_net:
        pnl_val = float(pnl_net)
        outcome = "win" if pnl_val > 0 else "loss" if pnl_val < 0 else "breakeven"
    elif exit_price and row.get("entry_price"):
        entry = float(row["entry_price"])
        exit_p = float(exit_price)
        if direction == "long":
            outcome = (
                "win" if exit_p > entry else "loss" if exit_p < entry else "breakeven"
            )
        elif direction == "short":
            outcome = (
                "win" if exit_p < entry else "loss" if exit_p > entry else "breakeven"
            )

    return {
        "timestamp": row.get("timestamp", ""),
        "direction": direction,
        "entry_price": float(row.get("entry_price", 0)),
        "exit_price": float(exit_price) if exit_price else None,
        "confidence": confidence,
        "pnl_net": float(pnl_net) if pnl_net else None,
        "exit_reason": exit_reason,
        "outcome": outcome,
        "notes": row.get("notes", ""),
    }


def calculate_accuracy_metrics(trades: list[dict]) -> dict[str, Any]:
    """Calculate signal accuracy metrics"""
    total = len(trades)
    if total == 0:
        return {"total": 0, "accuracy": 0, "wins": 0, "losses": 0}

    wins = sum(1 for t in trades if t["outcome"] == "win")
    losses = sum(1 for t in trades if t["outcome"] == "loss")
    pending = sum(1 for t in trades if t["outcome"] == "pending")

    accuracy = wins / total if total > 0 else 0

    # Confidence buckets
    conf_buckets: dict[str, list] = defaultdict(list)
    for t in trades:
        if t["confidence"] is not None:
            bucket = (
                "high"
                if t["confidence"] >= 0.8
                else "medium"
                if t["confidence"] >= 0.6
                else "low"
            )
            conf_buckets[bucket].append(t)

    conf_stats = {}
    for bucket, bucket_trades in conf_buckets.items():
        bucket_wins = sum(1 for t in bucket_trades if t["outcome"] == "win")
        conf_stats[bucket] = {
            "count": len(bucket_trades),
            "accuracy": bucket_wins / len(bucket_trades) if bucket_trades else 0,
        }

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "pending": pending,
        "accuracy": accuracy,
        "confidence_distribution": conf_stats,
    }


def calculate_strategy_metrics(trades: list[dict]) -> dict[str, dict]:
    """Calculate per-strategy metrics from trade metadata"""
    by_strategy: dict[str, list] = defaultdict(list)
    for t in trades:
        # Extract strategy hint from notes
        notes = t.get("notes", "").lower()
        strategy = "unknown"
        if "mtm" in notes:
            strategy = "mtm"
        elif "mrb" in notes:
            strategy = "mrb"
        elif "mlb" in notes:
            strategy = "mlb"
        elif "ensemble" in notes:
            strategy = "ensemble"
        else:
            strategy = "default"
        by_strategy[strategy].append(t)

    results = {}
    for strat, strat_trades in by_strategy.items():
        wins = sum(1 for t in strat_trades if t["outcome"] == "win")
        losses = sum(1 for t in strat_trades if t["outcome"] == "loss")
        total = len(strat_trades)
        pnl_values = [t["pnl_net"] for t in strat_trades if t["pnl_net"] is not None]

        results[strat] = {
            "total": total,
            "wins": wins,
            "losses": losses,
            "accuracy": wins / total if total > 0 else 0,
            "avg_pnl": statistics.mean(pnl_values) if pnl_values else 0,
            "total_pnl": sum(pnl_values) if pnl_values else 0,
        }

    return results


def calculate_timeframe_metrics(trades: list[dict]) -> dict[str, dict]:
    """Calculate metrics by time-of-day (proxy for timeframe effectiveness)"""
    by_hour: dict[int, list] = defaultdict(list)
    for t in trades:
        ts = t.get("timestamp", "")
        if ts:
            try:
                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                by_hour[dt.hour].append(t)
            except ValueError:
                pass

    results = {}
    for hour, hour_trades in sorted(by_hour.items()):
        wins = sum(1 for t in hour_trades if t["outcome"] == "win")
        total = len(hour_trades)
        results[f"{hour:02d}:00"] = {
            "count": total,
            "accuracy": wins / total if total > 0 else 0,
        }

    return results


def detect_feature_drift(trades: list[dict]) -> dict[str, Any]:
    """Simple drift detection: compare first half vs second half accuracy"""
    if len(trades) < 4:
        return {"drift_detected": False, "reason": "insufficient_data"}

    mid = len(trades) // 2
    first_half = trades[:mid]
    second_half = trades[mid:]

    acc_first = sum(1 for t in first_half if t["outcome"] == "win") / len(first_half)
    acc_second = sum(1 for t in second_half if t["outcome"] == "win") / len(second_half)

    drift = abs(acc_first - acc_second)
    return {
        "drift_detected": drift > 0.15,
        "first_half_accuracy": acc_first,
        "second_half_accuracy": acc_second,
        "drift_magnitude": drift,
    }


def suggest_threshold_optimizations(metrics: dict) -> list[str]:
    """Generate threshold optimization suggestions"""
    suggestions = []
    acc = metrics.get("accuracy", 0)
    conf_dist = metrics.get("confidence_distribution", {})

    if acc < 0.5:
        suggestions.append(
            "Overall accuracy below 50% — review signal generation logic"
        )

    for bucket, stats in conf_dist.items():
        if bucket == "high" and stats["accuracy"] < 0.6:
            suggestions.append(
                f"High-confidence signals ({stats['accuracy']:.0%} acc) underperforming — raise min_confidence"
            )
        if bucket == "low" and stats["accuracy"] > 0.7:
            suggestions.append(
                f"Low-confidence signals ({stats['accuracy']:.0%} acc) performing well — consider lowering threshold"
            )

    if not suggestions:
        suggestions.append("No immediate threshold changes recommended")

    return suggestions


def generate_vault_note(date_str: str, trades: list[dict], session: dict) -> str:
    """Generate Obsidian vault note markdown"""
    metrics = calculate_accuracy_metrics(trades)
    strategy_metrics = calculate_strategy_metrics(trades)
    timeframe_metrics = calculate_timeframe_metrics(trades)
    drift = detect_feature_drift(trades)
    suggestions = suggest_threshold_optimizations(metrics)

    # Determine best strategy
    best_strategy = "N/A"
    best_acc = 0
    for strat, stats in strategy_metrics.items():
        if stats["accuracy"] > best_acc and stats["total"] >= 1:
            best_acc = stats["accuracy"]
            best_strategy = strat

    overall_acc = metrics["accuracy"]

    lines = [
        "---",
        "type: signal-quality",
        f"date: {date_str}",
        f"overall_accuracy: {overall_acc:.2%}",
        f"best_strategy: {best_strategy}",
        "---",
        "",
        f"# Signal Quality Report — {date_str}",
        "",
        "## Overview",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Signals | {metrics['total']} |",
        f"| Wins | {metrics['wins']} |",
        f"| Losses | {metrics['losses']} |",
        f"| Pending | {metrics['pending']} |",
        f"| Overall Accuracy | {overall_acc:.2%} |",
        f"| Config | {session.get('config', 'N/A')} |",
        f"| Symbol | {session.get('symbol', 'N/A')} |",
        "",
        "## Strategy Breakdown",
        "",
        "| Strategy | Total | Wins | Losses | Accuracy | Avg PnL | Total PnL |",
        "|----------|-------|------|--------|----------|---------|-----------|",
    ]

    for strat, stats in sorted(strategy_metrics.items()):
        lines.append(
            f"| {strat} | {stats['total']} | {stats['wins']} | {stats['losses']} | "
            f"{stats['accuracy']:.2%} | {stats['avg_pnl']:.2f} | {stats['total_pnl']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Confidence Distribution",
            "",
            "| Bucket | Count | Accuracy |",
            "|--------|-------|----------|",
        ]
    )

    for bucket in ["high", "medium", "low"]:
        if bucket in metrics["confidence_distribution"]:
            stats = metrics["confidence_distribution"][bucket]
            lines.append(f"| {bucket} | {stats['count']} | {stats['accuracy']:.2%} |")

    lines.extend(
        [
            "",
            "## Time-of-Day Performance",
            "",
            "| Hour | Signals | Accuracy |",
            "|------|---------|----------|",
        ]
    )

    for hour_label, stats in sorted(timeframe_metrics.items()):
        lines.append(f"| {hour_label} | {stats['count']} | {stats['accuracy']:.2%} |")

    lines.extend(
        [
            "",
            "## Feature Drift Detection",
            "",
            f"- **Drift Detected**: {'YES' if drift['drift_detected'] else 'No'}",
            f"- First Half Accuracy: {drift.get('first_half_accuracy', 0):.2%}",
            f"- Second Half Accuracy: {drift.get('second_half_accuracy', 0):.2%}",
            f"- Drift Magnitude: {drift.get('drift_magnitude', 0):.2%}",
            "",
            "## Threshold Optimization Suggestions",
            "",
        ]
    )

    for i, s in enumerate(suggestions, 1):
        lines.append(f"{i}. {s}")

    lines.extend(
        [
            "",
            "## Trade Log",
            "",
            "| Time | Dir | Entry | Exit | PnL | Outcome | Conf |",
            "|------|-----|-------|------|-----|---------|------|",
        ]
    )

    for t in trades:
        exit_str = f"{t['exit_price']:.2f}" if t["exit_price"] else "—"
        pnl_str = f"{t['pnl_net']:.2f}" if t["pnl_net"] is not None else "—"
        conf_str = f"{t['confidence']:.2f}" if t["confidence"] is not None else "—"
        lines.append(
            f"| {t['timestamp'][:16]} | {t['direction']} | {t['entry_price']:.2f} | "
            f"{exit_str} | {pnl_str} | {t['outcome']} | {conf_str} |"
        )

    lines.extend(
        [
            "",
            "---",
            f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} by Pipeline 9 — Signal Quality Tracker*",
        ]
    )

    return "\n".join(lines)


def run_pipeline(target_date: str | None = None) -> str:
    """Run the signal quality pipeline and write vault note"""
    VAULT_DIR.mkdir(parents=True, exist_ok=True)

    date_str = target_date or datetime.now().strftime("%Y-%m-%d")
    trades_raw = load_trade_log()
    session = load_session()

    trades = [classify_trade(row) for row in trades_raw]
    markdown = generate_vault_note(date_str, trades, session)

    out_path = VAULT_DIR / f"{date_str}.md"
    out_path.write_text(markdown, encoding="utf-8")

    return str(out_path)


def main():
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else None
    path = run_pipeline(target)
    print(f"Vault note written: {path}")


if __name__ == "__main__":
    main()
