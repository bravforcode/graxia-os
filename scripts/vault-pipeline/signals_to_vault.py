"""Signal-to-Vault: Precision, Recall, F1 per strategy

Analyzes signal-outcome pairs from quant_os data,
calculates classification metrics per strategy,
and outputs vault-compatible markdown.
"""

import csv
import json
import re
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

DATA_DIR = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os\data")
TRADE_LOG = DATA_DIR / "paper_trade_log.csv"
SESSION_JSON = DATA_DIR / "paper_trade_session.json"
VAULT_DIR = Path(
    r"C:\Users\menum\Documents\ObsidianVault\Second Brain\03-resources\trading\signals"
)


def parse_confidence(notes: str) -> float | None:
    m = re.search(r"conf=([\d.]+)", notes)
    return float(m.group(1)) if m else None


def load_trades() -> list[dict]:
    trades = []
    if not TRADE_LOG.exists():
        return trades
    with open(TRADE_LOG, "r") as f:
        for row in csv.DictReader(f):
            trades.append(row)
    return trades


def load_session() -> dict:
    if not SESSION_JSON.exists():
        return {}
    with open(SESSION_JSON, "r") as f:
        return json.load(f)


def classify(row: dict) -> dict[str, Any]:
    """Convert raw CSV row to classified signal-outcome pair"""
    direction = row.get("direction", "").strip()
    exit_price = row.get("exit_price", "").strip()
    pnl_net = row.get("pnl_net", "").strip()
    confidence = parse_confidence(row.get("notes", ""))

    # Binary classification: signal said trade → did it win?
    signal_fired = direction in ("long", "short")
    correct = False

    if pnl_net:
        correct = float(pnl_net) > 0
    elif exit_price and row.get("entry_price"):
        entry = float(row["entry_price"])
        exit_p = float(exit_price)
        if direction == "long":
            correct = exit_p > entry
        elif direction == "short":
            correct = exit_p < entry

    return {
        "timestamp": row.get("timestamp", ""),
        "direction": direction,
        "entry_price": float(row.get("entry_price", 0)),
        "exit_price": float(exit_price) if exit_price else None,
        "pnl_net": float(pnl_net) if pnl_net else None,
        "confidence": confidence,
        "signal_fired": signal_fired,
        "correct": correct,
        "outcome": "win" if correct else ("loss" if signal_fired else "no_signal"),
        "notes": row.get("notes", ""),
    }


def compute_classification_metrics(trades: list[dict]) -> dict[str, dict]:
    """Compute precision, recall, F1 per strategy group"""
    by_strategy: dict[str, list] = defaultdict(list)

    for t in trades:
        notes = t["notes"].lower()
        strat = "default"
        if "mtm" in notes:
            strat = "mtm"
        elif "mrb" in notes:
            strat = "mrb"
        elif "mlb" in notes:
            strat = "mlb"
        elif "ensemble" in notes:
            strat = "ensemble"
        by_strategy[strat].append(t)

    results = {}
    for strat, strat_trades in by_strategy.items():
        signals = [t for t in strat_trades if t["signal_fired"]]
        correct = [t for t in signals if t["correct"]]
        wins = len(correct)
        total_signals = len(signals)
        total_trades = len(strat_trades)

        # Precision: of signals fired, how many were correct?
        precision = wins / total_signals if total_signals > 0 else 0

        # Recall: of all winning opportunities, how many did we catch?
        # Simplified: wins / total_trades as proxy
        recall = wins / total_trades if total_trades > 0 else 0

        # F1
        f1 = (
            2 * (precision * recall) / (precision + recall)
            if (precision + recall) > 0
            else 0
        )

        # Confidence stats
        conf_values = [t["confidence"] for t in signals if t["confidence"] is not None]
        avg_conf = statistics.mean(conf_values) if conf_values else 0

        # PnL stats
        pnl_values = [t["pnl_net"] for t in signals if t["pnl_net"] is not None]

        results[strat] = {
            "total_signals": total_signals,
            "wins": wins,
            "losses": total_signals - wins,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "avg_confidence": avg_conf,
            "avg_pnl": statistics.mean(pnl_values) if pnl_values else 0,
            "total_pnl": sum(pnl_values) if pnl_values else 0,
        }

    return results


def compute_confidence_bands(trades: list[dict]) -> list[dict]:
    """Compute metrics across confidence bands"""
    bands = [
        ("0.90–1.00", 0.90, 1.00),
        ("0.80–0.89", 0.80, 0.90),
        ("0.70–0.79", 0.70, 0.80),
        ("0.60–0.69", 0.60, 0.70),
        ("0.50–0.59", 0.50, 0.60),
        ("< 0.50", 0.0, 0.50),
    ]

    results = []
    for label, lo, hi in bands:
        subset = [
            t
            for t in trades
            if t["confidence"] is not None and lo <= t["confidence"] < hi
        ]
        if not subset:
            results.append({"band": label, "count": 0, "precision": 0, "win_rate": 0})
            continue

        wins = sum(1 for t in subset if t["correct"])
        total = len(subset)
        correct = [t for t in subset if t["correct"]]

        results.append(
            {
                "band": label,
                "count": total,
                "precision": wins / total if total > 0 else 0,
                "win_rate": wins / total if total > 0 else 0,
            }
        )

    return results


def generate_markdown(date_str: str, trades: list[dict], session: dict) -> str:
    """Generate vault-compatible markdown report"""
    strat_metrics = compute_classification_metrics(trades)
    conf_bands = compute_confidence_bands(trades)

    # Overall metrics
    total_signals = sum(s["total_signals"] for s in strat_metrics.values())
    total_wins = sum(s["wins"] for s in strat_metrics.values())
    overall_precision = total_wins / total_signals if total_signals > 0 else 0

    # Best strategy by F1
    if strat_metrics:
        best_strat = max(strat_metrics.items(), key=lambda x: x[1]["f1"])
        best_name = best_strat[0]
        best_f1 = best_strat[1].get("f1", 0)
    else:
        best_name = "N/A"
        best_f1 = 0

    lines = [
        "---",
        "type: signal-quality",
        f"date: {date_str}",
        f"overall_accuracy: {overall_precision:.2%}",
        f"best_strategy: {best_name}",
        "---",
        "",
        f"# Signal Quality Analysis — {date_str}",
        "",
        "## Precision / Recall / F1 per Strategy",
        "",
        "| Strategy | Signals | Wins | Precision | Recall | F1 | Avg Conf | Total PnL |",
        "|----------|---------|------|-----------|--------|-----|----------|-----------|",
    ]

    for strat in sorted(strat_metrics):
        s = strat_metrics[strat]
        lines.append(
            f"| {strat} | {s['total_signals']} | {s['wins']} | "
            f"{s['precision']:.2%} | {s['recall']:.2%} | {s['f1']:.3f} | "
            f"{s['avg_confidence']:.2f} | {s['total_pnl']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Confidence Band Analysis",
            "",
            "| Band | Signals | Precision | Win Rate |",
            "|------|---------|-----------|----------|",
        ]
    )

    for b in conf_bands:
        if b["count"] > 0:
            lines.append(
                f"| {b['band']} | {b['count']} | {b['precision']:.2%} | {b['win_rate']:.2%} |"
            )

    lines.extend(
        [
            "",
            "## Key Findings",
            "",
            f"- **Best Strategy (F1)**: {best_name} ({best_f1:.3f})",
            f"- **Overall Precision**: {overall_precision:.2%}",
            f"- **Total Signals Evaluated**: {total_signals}",
            "",
            "## Recommendations",
            "",
        ]
    )

    # Auto-generate recommendations
    for strat, s in strat_metrics.items():
        if s["precision"] < 0.4 and s["total_signals"] >= 2:
            lines.append(
                f"- **{strat}**: Low precision ({s['precision']:.2%}) — review signal generation"
            )
        if s["f1"] > 0.6:
            lines.append(
                f"- **{strat}**: Strong F1 ({s['f1']:.3f}) — consider increasing allocation"
            )

    high_conf = [b for b in conf_bands if "0.90" in b["band"] or "0.80" in b["band"]]
    for b in high_conf:
        if b["precision"] < 0.7 and b["count"] > 0:
            lines.append(
                f"- High-confidence band ({b['band']}) underperforming — review confidence calibration"
            )

    if not any("review" in l.lower() for l in lines):
        lines.append("- No critical issues detected — continue monitoring")

    lines.extend(
        [
            "",
            "---",
            f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} by Pipeline 9 — Signal-to-Vault*",
        ]
    )

    return "\n".join(lines)


def run(target_date: str | None = None) -> str:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = target_date or datetime.now().strftime("%Y-%m-%d")
    trades_raw = load_trades()
    session = load_session()
    trades = [classify(row) for row in trades_raw]
    md = generate_markdown(date_str, trades, session)

    out = VAULT_DIR / f"{date_str}_precision.md"
    out.write_text(md, encoding="utf-8")
    return str(out)


def main():
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else None
    path = run(target)
    print(f"Vault note written: {path}")


if __name__ == "__main__":
    main()
