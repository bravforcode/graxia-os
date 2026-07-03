"""
backtest_to_vault.py — Convert quant_os backtest results to Obsidian vault notes.

Reads BacktestMetrics (dataclass) or JSON backtest output files and generates
vault-compatible markdown with YAML frontmatter.

Usage:
    # From a JSON results file
    python backtest_to_vault.py --input results/backtest_results.json --output-dir vault/backtest

    # From a suite JSON (multi-symbol)
    python backtest_to_vault.py --input results/backtest_suite_20260626.json --output-dir vault/backtest

    # Programmatic — pass a BacktestMetrics instance
    from backtest_to_vault import metrics_to_vault_note
    note = metrics_to_vault_note(metrics, strategy="Momentum", symbol="XAUUSD")
"""

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional


# ---------------------------------------------------------------------------
# Lightweight metric holder (mirrors backtest.metrics.BacktestMetrics fields)
# ---------------------------------------------------------------------------


@dataclass
class BacktestMetrics:
    """Subset of fields needed for vault notes.  Matches quant_os BacktestMetrics."""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    total_return_pct: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_rr: float = 0.0
    expectancy: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    cagr: float = 0.0
    total_fees: float = 0.0
    long_trades: int = 0
    short_trades: int = 0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------


def _frontmatter(date_str: str, strategies: List[str], symbol: str) -> str:
    """YAML frontmatter block."""
    strat_list = ", ".join(strategies) if strategies else "unknown"
    return (
        "---\n"
        f"type: backtest\n"
        f"date: {date_str}\n"
        f"symbol: {symbol}\n"
        f"strategies: [{strat_list}]\n"
        "status: auto-generated\n"
        "---\n"
    )


def _fmt(val: Any, decimals: int = 2, pct: bool = False) -> str:
    """Format a numeric value for display."""
    if isinstance(val, str):
        return val
    if val is None:
        return "N/A"
    if pct:
        return f"{val:.{decimals}f}%"
    return f"{val:.{decimals}f}"


def metrics_to_vault_note(
    metrics: BacktestMetrics,
    strategy: str = "Unknown",
    symbol: str = "Unknown",
    date: Optional[str] = None,
) -> str:
    """Render a BacktestMetrics instance into a vault-compatible markdown string."""
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = [
        _frontmatter(date, [strategy], symbol),
        f"# Backtest: {strategy} — {symbol}",
        "",
        f"**Date:** {date}  ",
        f"**Strategy:** {strategy}  ",
        f"**Symbol:** {symbol}  ",
        "",
        "## Performance Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Trades | {metrics.total_trades} |",
        f"| Win Rate | {_fmt(metrics.win_rate * 100, 1)}% |",
        f"| Profit Factor | {_fmt(metrics.profit_factor)} |",
        f"| Sharpe Ratio | {_fmt(metrics.sharpe_ratio)} |",
        f"| Sortino Ratio | {_fmt(metrics.sortino_ratio)} |",
        f"| Max Drawdown | {_fmt(metrics.max_drawdown_pct, 1)}% |",
        f"| Total Return | {_fmt(metrics.total_return_pct, 2)}% |",
        f"| Expectancy | {_fmt(metrics.expectancy)} |",
        f"| Avg R:R | {_fmt(metrics.avg_rr)} |",
        f"| CAGR | {_fmt(metrics.cagr, 2)}% |",
        "",
        "## Trade Breakdown",
        "",
        f"- **Wins / Losses:** {metrics.winning_trades} / {metrics.losing_trades}",
        f"- **Long / Short:** {metrics.long_trades} / {metrics.short_trades}",
        f"- **Avg Win:** {_fmt(metrics.avg_win)}",
        f"- **Avg Loss:** {_fmt(metrics.avg_loss)}",
        f"- **Max Consecutive Wins:** {metrics.max_consecutive_wins}",
        f"- **Max Consecutive Losses:** {metrics.max_consecutive_losses}",
        f"- **Total Fees:** {_fmt(metrics.total_fees)}",
        "",
        "## Assessment",
        "",
    ]

    # Simple quality tag
    if metrics.profit_factor >= 1.5 and metrics.sharpe_ratio >= 1.0:
        lines.append("> **PASS** — Profitable with acceptable risk-adjusted return.")
    elif metrics.profit_factor >= 1.0 and metrics.sharpe_ratio >= 0.5:
        lines.append(
            "> **MARGINAL** — Profitable but risk-adjusted returns need monitoring."
        )
    elif metrics.total_trades == 0:
        lines.append("> **NO TRADES** — Strategy produced zero trades in this window.")
    else:
        lines.append("> **FAIL** — Below profitability or risk thresholds.")

    lines.extend(
        [
            "",
            "## Related",
            "",
            "- [[trading/backtest/index]]",
            "",
        ]
    )

    return "\n".join(lines)


def suite_to_vault_notes(
    suite_path: Path,
    output_dir: Path,
) -> List[Path]:
    """Parse a backtest_suite JSON and write one vault note per symbol+strategy.

    Suite format (from quant_os/results/backtest_suite_*.json):
    {
      "timestamp": "...",
      "results": {
        "XAUUSD": {
          "strategies": {
            "Momentum": { "strategy": ..., "total_return_pct": ..., ... }
          }
        }
      }
    }

    Returns list of written file paths.
    """
    raw = json.loads(suite_path.read_text(encoding="utf-8"))

    # Handle Infinity in JSON (Python json.loads already handles it if parsed
    # with custom decoder, but the file might have literal Infinity)
    text = suite_path.read_text(encoding="utf-8")
    text = text.replace("Infinity", "1e999")
    raw = json.loads(text)

    ts = raw.get("timestamp", datetime.now(timezone.utc).isoformat())
    date_str = ts[:10]  # "2026-06-26" from "2026-06-26 16:48 UTC"
    results = raw.get("results", {})
    written: List[Path] = []

    for symbol, sym_data in results.items():
        strategies = sym_data.get("strategies", {})
        for strat_name, strat_data in strategies.items():
            m = BacktestMetrics(
                total_trades=strat_data.get("n_trades", 0),
                win_rate=strat_data.get("win_rate_pct", 0) / 100,
                profit_factor=strat_data.get("profit_factor", 0),
                sharpe_ratio=strat_data.get("sharpe", 0),
                max_drawdown_pct=strat_data.get("max_drawdown_pct", 0),
                total_return_pct=strat_data.get("total_return_pct", 0),
            )
            note = metrics_to_vault_note(
                m, strategy=strat_name, symbol=symbol, date=date_str
            )

            fname = f"{date_str}_{symbol}_{strat_name}.md"
            out_path = output_dir / fname
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(note, encoding="utf-8")
            written.append(out_path)

    return written


def simple_results_to_vault_notes(
    results_path: Path,
    output_dir: Path,
) -> List[Path]:
    """Parse a simple backtest_results.json and write vault notes.

    Simple format:
    {
      "timestamp": "...",
      "strategies": {
        "MTM": { "metrics": { ... } }
      }
    }
    """
    raw = json.loads(results_path.read_text(encoding="utf-8"))
    ts = raw.get("timestamp", datetime.now(timezone.utc).isoformat())
    date_str = ts[:10]
    strategies = raw.get("strategies", {})
    written: List[Path] = []

    for strat_name, strat_data in strategies.items():
        m_data = strat_data.get("metrics", strat_data)
        m = BacktestMetrics(
            total_trades=m_data.get("total_trades", 0),
            winning_trades=m_data.get("winning_trades", 0),
            losing_trades=m_data.get("losing_trades", 0),
            win_rate=m_data.get("win_rate", 0),
            total_return_pct=m_data.get("total_return_pct", 0),
            avg_win=m_data.get("avg_win", 0),
            avg_loss=m_data.get("avg_loss", 0),
            avg_rr=m_data.get("avg_rr", 0),
            expectancy=m_data.get("expectancy", 0),
            profit_factor=m_data.get("profit_factor", 0),
            max_drawdown=m_data.get("max_drawdown", 0),
            max_drawdown_pct=m_data.get("max_drawdown_pct", 0),
            sharpe_ratio=m_data.get("sharpe_ratio", 0),
            sortino_ratio=m_data.get("sortino_ratio", 0),
            calmar_ratio=m_data.get("calmar_ratio", 0),
            cagr=m_data.get("cagr", 0),
        )
        note = metrics_to_vault_note(
            m, strategy=strat_name, symbol="XAUUSD", date=date_str
        )

        fname = f"{date_str}_{strat_name}.md"
        out_path = output_dir / fname
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(note, encoding="utf-8")
        written.append(out_path)

    return written


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _find_backtest_files(quant_os_root: Path) -> List[Path]:
    """Auto-discover backtest JSON files from quant_os results/reports/artifacts."""
    candidates: List[Path] = []
    search_dirs = ["results", "reports", "artifacts"]
    patterns = ["backtest_suite_*.json", "backtest_results*.json", "backtest_*.json"]

    for subdir in search_dirs:
        d = quant_os_root / subdir
        if not d.is_dir():
            continue
        for pat in patterns:
            for f in sorted(d.glob(pat), key=lambda p: p.stat().st_mtime, reverse=True):
                candidates.append(f)

    return candidates


def _detect_format(raw: dict) -> str:
    """Detect whether a JSON is suite, simple, or unknown."""
    if "results" in raw and isinstance(raw["results"], dict):
        first_val = next(iter(raw["results"].values()), None)
        if isinstance(first_val, dict) and "strategies" in first_val:
            return "suite"
        return "simple"
    if "strategies" in raw:
        return "simple"
    return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert backtest results to Obsidian vault notes"
    )
    parser.add_argument(
        "--input",
        "-i",
        default=None,
        help="Path to backtest JSON results file (omit for auto-discovery)",
    )
    parser.add_argument(
        "--output-dir", "-o", required=True, help="Directory to write vault notes"
    )
    parser.add_argument(
        "--strategy", "-s", default=None, help="Strategy name (for simple results)"
    )
    parser.add_argument(
        "--symbol", default=None, help="Symbol name (for simple results)"
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto-discover latest backtest files from quant_os",
    )
    parser.add_argument(
        "--quant-os-root",
        default=None,
        help="quant_os root (default: ..\\graxia\\packages\\quant_os)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    input_path: Optional[Path] = None

    if args.input:
        input_path = Path(args.input)
    elif args.auto:
        # Resolve quant_os root relative to this script's location
        if args.quant_os_root:
            qroot = Path(args.quant_os_root)
        else:
            qroot = (
                Path(__file__).resolve().parent.parent.parent
                / "graxia"
                / "packages"
                / "quant_os"
            )
        if not qroot.is_dir():
            print(f"Error: quant_os root not found at {qroot}", file=sys.stderr)
            sys.exit(1)
        candidates = _find_backtest_files(qroot)
        if not candidates:
            print(f"No backtest JSON files found under {qroot}", file=sys.stderr)
            sys.exit(1)
        input_path = candidates[0]  # most recent by mtime
        print(f"Auto-discovered: {input_path}")
    else:
        parser.error("--input or --auto is required")

    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    text = input_path.read_text(encoding="utf-8")
    raw = json.loads(text.replace("Infinity", "1e999"))

    fmt = _detect_format(raw)
    if fmt == "suite":
        written = suite_to_vault_notes(input_path, output_dir)
    elif fmt == "simple":
        written = simple_results_to_vault_notes(input_path, output_dir)
    else:
        print(
            "Unrecognised JSON format — expected 'results' or 'strategies' key",
            file=sys.stderr,
        )
        sys.exit(1)

    for p in written:
        print(p)


if __name__ == "__main__":
    main()
