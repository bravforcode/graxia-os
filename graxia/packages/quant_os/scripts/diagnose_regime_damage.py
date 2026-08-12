#!/usr/bin/env python3
"""Diagnose per-regime Sharpe for each strategy.

Reads trade logs and computes Sharpe ratio broken down by market regime
(trend / range / volatile).  Writes a Markdown report to
reports/mega_plan_evidence/regime_damage.md.

Usage:
    python scripts/diagnose_regime_damage.py [--data-dir data] [--output reports/mega_plan_evidence/regime_damage.md]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

# Ensure the package root is on sys.path so we can import quant_os modules
_THIS_DIR = Path(__file__).resolve().parent
_PKG_ROOT = _THIS_DIR.parent
sys.path.insert(0, str(_PKG_ROOT.parent))

from quant_os.backtest.metrics import _DEFAULT_BARS_PER_YEAR, BARS_PER_YEAR

# ── Helpers ─────────────────────────────────────────────────────────────


def _load_trades(path: Path) -> list[dict]:
    """Load trades from a JSONL trade log."""
    trades: list[dict] = []
    if not path.exists():
        return trades
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                trades.append(json.loads(line))
    return trades


def _load_trades_from_parquet(path: Path) -> list[dict]:
    """Load trades from a Parquet trade log (position_manager format)."""
    if not path.exists():
        return []
    try:
        import pandas as pd

        df = pd.read_parquet(path)
        return df.to_dict("records")
    except Exception:
        return []


def _classify_regime(trade: dict) -> str:
    """Infer market regime from trade metadata.

    Uses explicit 'regime' field if present; otherwise falls back to ATR-based
    heuristic or defaults to 'unknown'.
    """
    # Explicit regime field (from TradingView payload or strategy metadata)
    regime = trade.get("regime") or trade.get("market_regime")
    if regime:
        return str(regime).lower()

    # ATR-based heuristic
    atr = trade.get("atr") or trade.get("atr_value")
    if atr is not None:
        atr = float(atr)
        if atr > 3.0:  # high ATR for XAUUSD M15
            return "volatile"
        elif atr > 1.5:
            return "trend"
        else:
            return "range"

    return "unknown"


def _sharpe_from_pnl(pnl_series: list[float], bars_per_year: int = _DEFAULT_BARS_PER_YEAR) -> float:
    """Compute Sharpe ratio from a list of per-trade PnL values.

    Treats each trade as one 'bar'.  For small samples (<5 trades) returns 0.
    """
    if len(pnl_series) < 5:
        return 0.0
    mean = sum(pnl_series) / len(pnl_series)
    var = sum((x - mean) ** 2 for x in pnl_series) / (len(pnl_series) - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    if std == 0:
        return 0.0
    # Annualize assuming ~625 trades/year for M15 metals strategy
    trades_per_year = bars_per_year / 4  # ~4 bars per trade on average
    return (mean / std) * math.sqrt(trades_per_year)


def diagnose(trades: list[dict], asset_class: str = "metals", timeframe: str = "M15") -> dict:
    """Compute per-strategy, per-regime Sharpe ratios.

    Returns:
        {
            "strategy_name": {
                "regime": {"sharpe": float, "trades": int, "mean_pnl": float},
                ...
            },
            ...
        }
    """
    bars_per_year = BARS_PER_YEAR.get((asset_class, timeframe), _DEFAULT_BARS_PER_YEAR)

    # Group by strategy → regime → pnl list
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for t in trades:
        strategy = t.get("strategy_id") or t.get("strategy") or "unknown"
        regime = _classify_regime(t)
        pnl = float(t.get("pnl", 0.0))
        grouped[strategy][regime].append(pnl)

    results: dict[str, dict] = {}
    for strategy, regimes in sorted(grouped.items()):
        results[strategy] = {}
        for regime, pnl_list in sorted(regimes.items()):
            sharpe = _sharpe_from_pnl(pnl_list, bars_per_year)
            results[strategy][regime] = {
                "sharpe": round(sharpe, 4),
                "trades": len(pnl_list),
                "mean_pnl": round(sum(pnl_list) / len(pnl_list), 4) if pnl_list else 0.0,
                "total_pnl": round(sum(pnl_list), 2),
            }

    return results


def _write_report(results: dict, output_path: Path, asset_class: str, timeframe: str) -> None:
    """Write Markdown report."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Regime Damage Report",
        "",
        f"**Generated:** {datetime.now(UTC).isoformat()}Z",
        f"**Asset class:** {asset_class} | **Timeframe:** {timeframe}",
        "",
        "## Summary",
        "",
        "| Strategy | Regime | Trades | Sharpe | Mean PnL | Total PnL |",
        "|----------|--------|------:|-------:|---------:|----------:|",
    ]

    for strategy, regimes in sorted(results.items()):
        for regime, stats in sorted(regimes.items()):
            lines.append(
                f"| {strategy} | {regime} | {stats['trades']} "
                f"| {stats['sharpe']:.4f} | {stats['mean_pnl']:.4f} | {stats['total_pnl']:.2f} |"
            )

    # Diagnosis: flag regimes where Sharpe < 0 for any strategy
    warnings: list[str] = []
    for strategy, regimes in results.items():
        for regime, stats in regimes.items():
            if stats["sharpe"] < 0 and stats["trades"] >= 5:
                warnings.append(
                    f"- **{strategy}** in **{regime}** regime: Sharpe = {stats['sharpe']:.4f} "
                    f"({stats['trades']} trades, total PnL = {stats['total_pnl']:.2f})"
                )

    lines.extend(["", "## Regime Damage Flags", ""])
    if warnings:
        lines.extend(warnings)
        lines.extend(
            [
                "",
                "> Strategies with negative Sharpe in a specific regime should be disabled or",
                "> have reduced allocation during that regime to avoid systematic losses.",
            ]
        )
    else:
        lines.append("No regime damage detected (all strategy-regime Sharpe ≥ 0 or sample < 5 trades).")

    lines.extend(
        [
            "",
            "## Recommendations",
            "",
            "1. Disable or reduce position size for strategies with persistent negative regime Sharpe.",
            "2. Add regime detection to the live signal path to dynamically adjust allocation.",
            "3. Re-run this analysis monthly as market microstructure evolves.",
            "",
        ]
    )

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to {output_path}")


# ── CLI ─────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose per-regime strategy damage.")
    parser.add_argument("--data-dir", default="data", help="Directory with trade logs")
    parser.add_argument(
        "--output",
        default="reports/mega_plan_evidence/regime_damage.md",
        help="Output Markdown report path",
    )
    parser.add_argument("--asset-class", default="metals", help="Asset class for annualization")
    parser.add_argument("--timeframe", default="M15", help="Timeframe for annualization")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)

    # Try Parquet first, then JSONL
    trades = _load_trades_from_parquet(data_dir / "trade_log.parquet")
    if not trades:
        trades = _load_trades(data_dir / "trade_log.jsonl")
    if not trades:
        # Try backtest results
        for p in data_dir.glob("**/*trades*.json"):
            trades.extend(_load_trades(p))
        for p in data_dir.glob("**/*trades*.jsonl"):
            trades.extend(_load_trades(p))

    if not trades:
        print("No trades found. Provide --data-dir pointing to a directory with trade logs.")
        sys.exit(1)

    print(f"Loaded {len(trades)} trades")
    results = diagnose(trades, asset_class=args.asset_class, timeframe=args.timeframe)
    _write_report(results, Path(args.output), args.asset_class, args.timeframe)


if __name__ == "__main__":
    main()
