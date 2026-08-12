"""
Pipeline 8: Performance Attribution → Vault weekly.
Reads paper_trade_log.csv, decomposes P&L by multiple dimensions,
generates vault note with comprehensive attribution analysis.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

import pandas as pd

TRADE_LOG = Path(
    r"C:\Users\menum\graxia os\graxia\packages\quant_os\data\paper_trade_log.csv"
)
VAULT_OUT = Path(
    r"C:\Users\menum\Documents\ObsidianVault\Second Brain\03-resources\trading\attribution"
)

SESSIONS = {
    "Asian": (0, 8),
    "London": (8, 14),
    "NY": (14, 21),
}

REGIME_THRESHOLDS = {
    "trending": {"atr_pct_min": 0.0},
    "volatile": {"atr_pct_min": 0.8},
    "ranging": {"atr_pct_min": None},
}


def load_trades(path: Path = TRADE_LOG) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(
        df["timestamp"], format="%Y-%m-%d %H:%M", errors="coerce"
    )
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        return df
    df["hour"] = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.day_name()
    df["week"] = df["timestamp"].dt.isocalendar()["week"]
    df["year"] = df["timestamp"].dt.year
    df["pnl"] = df["pnl_net"].fillna(df["pnl_gross"])
    return df


def assign_session(hour: int) -> str:
    for name, (h_start, h_end) in SESSIONS.items():
        if h_start <= hour < h_end:
            return name
    return "Off-hours"


def assign_regime(row: pd.Series) -> str:
    notes = str(row.get("notes", "")).lower()
    if "trend" in notes:
        return "trending"
    if "volatil" in notes or "spike" in notes:
        return "volatile"
    return "ranging"


def load_strategy_map() -> dict[str, str]:
    strategy_path = TRADE_LOG.parent / "strategy_map.json"
    if strategy_path.exists():
        return json.loads(strategy_path.read_text())
    return {}


def attribute_trades(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {"empty": True, "total_trades": 0}

    df["session"] = df["hour"].apply(assign_session)
    df["regime"] = df.apply(assign_regime, axis=1)
    smap = load_strategy_map()
    df["strategy"] = df["notes"].apply(lambda n: _extract_strategy(n, smap))

    total_pnl = df["pnl"].sum()
    total_trades = len(df)
    win_trades = df[df["pnl"] > 0]
    loss_trades = df[df["pnl"] <= 0]
    win_rate = len(win_trades) / total_trades if total_trades else 0
    avg_win = win_trades["pnl"].mean() if len(win_trades) else 0
    avg_loss = loss_trades["pnl"].mean() if len(loss_trades) else 0
    profit_factor = (
        abs(win_trades["pnl"].sum() / loss_trades["pnl"].sum())
        if len(loss_trades) and loss_trades["pnl"].sum() != 0
        else float("inf")
    )
    expectancy = total_pnl / total_trades if total_trades else 0

    by_strategy = _group_agg(df, "strategy")
    by_regime = _group_agg(df, "regime")
    by_session = _group_agg(df, "session")
    by_dow = _group_agg(df, "day_of_week")
    by_direction = _group_agg(df, "direction")

    best_trades = (
        df.nlargest(3, "pnl")[
            [
                "timestamp",
                "direction",
                "entry_price",
                "exit_price",
                "pnl",
                "strategy",
                "notes",
            ]
        ].to_dict("records")
        if len(df) >= 3
        else df.to_dict("records")
    )
    worst_trades = (
        df.nsmallest(3, "pnl")[
            [
                "timestamp",
                "direction",
                "entry_price",
                "exit_price",
                "pnl",
                "strategy",
                "notes",
            ]
        ].to_dict("records")
        if len(df) >= 3
        else df.to_dict("records")
    )

    corr_matrix = _compute_correlation(df)
    weight_suggestion = _suggest_weights(by_strategy)

    return {
        "empty": False,
        "total_trades": total_trades,
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 4),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2)
        if profit_factor != float("inf")
        else "∞",
        "expectancy": round(expectancy, 2),
        "best_strategy": max(by_strategy, key=lambda s: by_strategy[s]["pnl"])
        if by_strategy
        else "N/A",
        "worst_strategy": min(by_strategy, key=lambda s: by_strategy[s]["pnl"])
        if by_strategy
        else "N/A",
        "by_strategy": by_strategy,
        "by_regime": by_regime,
        "by_session": by_session,
        "by_day_of_week": by_dow,
        "by_direction": by_direction,
        "best_trades": best_trades,
        "worst_trades": worst_trades,
        "correlation_matrix": corr_matrix,
        "weight_suggestion": weight_suggestion,
    }


def _extract_strategy(notes: str, smap: dict[str, str]) -> str:
    notes_lower = str(notes).lower()
    for key, strat in smap.items():
        if key.lower() in notes_lower:
            return strat
    if "rsi" in notes_lower:
        return "RSI-MeanReversion"
    if "macd" in notes_lower:
        return "MACD-Trend"
    if "breakout" in notes_lower:
        return "Breakout"
    if "grid" in notes_lower:
        return "Grid"
    if "ensemble" in notes_lower:
        return "Ensemble"
    return "default"


def _group_agg(df: pd.DataFrame, col: str) -> dict[str, dict]:
    result = {}
    for name, grp in df.groupby(col):
        pnl = grp["pnl"]
        result[str(name)] = {
            "trades": len(grp),
            "pnl": round(pnl.sum(), 2),
            "avg_pnl": round(pnl.mean(), 2),
            "win_rate": round((pnl > 0).mean(), 4),
            "max_win": round(pnl.max(), 2) if len(pnl) else 0,
            "max_loss": round(pnl.min(), 2) if len(pnl) else 0,
        }
    return result


def _compute_correlation(df: pd.DataFrame) -> dict[str, list]:
    strategies = df["strategy"].unique()
    if len(strategies) < 2:
        return {}
    pivot = df.pivot_table(
        index="timestamp",
        columns="strategy",
        values="pnl",
        aggfunc="sum",
    ).fillna(0)
    corr = pivot.corr()
    matrix: dict[str, list] = {}
    for s in strategies:
        matrix[s] = [round(corr.loc[s, s2], 3) for s2 in strategies]
    return matrix


def _suggest_weights(by_strategy: dict[str, dict]) -> dict[str, float]:
    if not by_strategy:
        return {}
    scores = {}
    for strat, stats in by_strategy.items():
        pf = stats["pnl"]
        wr = stats["win_rate"]
        scores[strat] = max(pf * wr, 0)
    total = sum(scores.values()) or 1
    return {s: round(v / total, 3) for s, v in scores.items()}


def render_markdown(attr: dict[str, Any], week: int, year: int) -> str:
    if attr.get("empty"):
        return _empty_note(week, year)

    best = attr["best_strategy"]
    worst = attr["worst_strategy"]
    lines = [
        "---",
        "type: attribution",
        f"week: {week}",
        f"year: {year}",
        f"total_pnl: {attr['total_pnl']}",
        f'best_strategy: "{best}"',
        f'worst_strategy: "{worst}"',
        f"generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "---",
        "",
        f"# Week {week} — Performance Attribution",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total P&L | **${attr['total_pnl']:,.2f}** |",
        f"| Total Trades | {attr['total_trades']} |",
        f"| Win Rate | {attr['win_rate']:.1%} |",
        f"| Avg Win | ${attr['avg_win']:,.2f} |",
        f"| Avg Loss | ${attr['avg_loss']:,.2f} |",
        f"| Profit Factor | {attr['profit_factor']} |",
        f"| Expectancy | ${attr['expectancy']:,.2f} |",
        "",
        "## P&L by Strategy",
        "",
        _render_table(
            attr["by_strategy"],
            ["Trades", "P&L", "Avg P&L", "Win Rate", "Max Win", "Max Loss"],
        ),
        "",
        "## P&L by Regime",
        "",
        _render_table(attr["by_regime"], ["Trades", "P&L", "Avg P&L", "Win Rate"]),
        "",
        "## P&L by Session",
        "",
        _render_table(attr["by_session"], ["Trades", "P&L", "Avg P&L", "Win Rate"]),
        "",
        "## P&L by Day of Week",
        "",
        _render_table(attr["by_day_of_week"], ["Trades", "P&L", "Avg P&L", "Win Rate"]),
        "",
        "## P&L by Direction",
        "",
        _render_table(attr["by_direction"], ["Trades", "P&L", "Avg P&L", "Win Rate"]),
        "",
        "## Best Trades",
        "",
        _render_trades_table(attr["best_trades"]),
        "",
        "## Worst Trades",
        "",
        _render_trades_table(attr["worst_trades"]),
        "",
        "## Strategy Correlation Matrix",
        "",
        _render_correlation(attr["correlation_matrix"]),
        "",
        "## Ensemble Weight Optimization",
        "",
        _render_weights(attr["weight_suggestion"]),
        "",
    ]
    return "\n".join(lines)


def _empty_note(week: int, year: int) -> str:
    return (
        "---\ntype: attribution\n"
        f"week: {week}\nyear: {year}\n"
        "total_pnl: 0\nbest_strategy: N/A\nworst_strategy: N/A\n"
        f"generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}\n---\n\n"
        f"# Week {week} — No Trades Recorded\n\nNo trades found for this week.\n"
    )


def _render_table(data: dict[str, dict], headers: list[str]) -> str:
    if not data:
        return "_No data._\n"
    cols = ["Metric"] + headers
    rows = [f"| {' | '.join(cols)} |"]
    rows.append(f"| {' | '.join(['---'] * len(cols))} |")
    for name, stats in sorted(data.items()):
        vals = [
            str(stats.get("trades", "")),
            f"${stats.get('pnl', 0):,.2f}",
            f"${stats.get('avg_pnl', 0):,.2f}",
            f"{stats.get('win_rate', 0):.1%}",
        ]
        if "max_win" in stats:
            vals.append(f"${stats.get('max_win', 0):,.2f}")
            vals.append(f"${stats.get('max_loss', 0):,.2f}")
        rows.append(f"| {name} | {' | '.join(vals)} |")
    return "\n".join(rows) + "\n"


def _render_trades_table(trades: list[dict]) -> str:
    if not trades:
        return "_No trades._\n"
    rows = [
        "| Timestamp | Direction | Entry | Exit | P&L | Strategy |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for t in trades:
        ts = t.get("timestamp", "")
        if hasattr(ts, "strftime"):
            ts = ts.strftime("%Y-%m-%d %H:%M")
        rows.append(
            f"| {ts} | {t.get('direction', '')} | {t.get('entry_price', '')} | "
            f"{t.get('exit_price', '')} | ${t.get('pnl', 0):,.2f} | {t.get('strategy', '')} |"
        )
    return "\n".join(rows) + "\n"


def _render_correlation(matrix: dict[str, list]) -> str:
    if not matrix:
        return "_Insufficient strategies for correlation._\n"
    strategies = list(matrix.keys())
    rows = ["| | " + " | ".join(strategies) + " |"]
    rows.append("| --- | " + " | ".join(["---"] * len(strategies)) + " |")
    for s in strategies:
        vals = " | ".join(f"{v:.3f}" for v in matrix[s])
        rows.append(f"| {s} | {vals} |")
    return "\n".join(rows) + "\n"


def _render_weights(weights: dict[str, float]) -> str:
    if not weights:
        return "_No weight suggestion available._\n"
    rows = [
        "| Strategy | Suggested Weight |",
        "| --- | --- |",
    ]
    for s, w in sorted(weights.items(), key=lambda x: -x[1]):
        rows.append(f"| {s} | {w:.1%} |")
    rows.append("")
    rows.append("> Weights derived from `pnl × win_rate` normalized. Rebalance weekly.")
    return "\n".join(rows) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline 8: Performance Attribution → Vault"
    )
    parser.add_argument(
        "--week", type=int, default=None, help="ISO week number (default: current)"
    )
    parser.add_argument(
        "--year", type=int, default=None, help="Year (default: current)"
    )
    parser.add_argument("--csv", type=str, default=None, help="Path to trade log CSV")
    args = parser.parse_args()

    today = dt.date.today()
    week = args.week or today.isocalendar()[1]
    year = args.year or today.year

    csv_path = Path(args.csv) if args.csv else TRADE_LOG
    df = load_trades(csv_path)

    if not df.empty:
        df = df[(df["week"] == week) & (df["year"] == year)]

    attr = attribute_trades(df)
    md = render_markdown(attr, week, year)

    VAULT_OUT.mkdir(parents=True, exist_ok=True)
    out_file = VAULT_OUT / f"week-{week}.md"
    out_file.write_text(md, encoding="utf-8")
    print(f"Attribution written to: {out_file}")


if __name__ == "__main__":
    main()
