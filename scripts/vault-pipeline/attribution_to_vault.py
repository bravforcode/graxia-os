"""
Pipeline 8 helper: Attribution → Vault (pandas-based aggregation).
Reads paper_trade_log.csv, performs pandas-driven aggregation across all
attribution dimensions, and writes vault-compatible markdown with tables.
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import pandas as pd

TRADE_LOG = Path(
    r"C:\Users\menum\graxia os\graxia\packages\quant_os\data\paper_trade_log.csv"
)
VAULT_OUT = Path(
    r"C:\Users\menum\Documents\ObsidianVault\Second Brain\03-resources\trading\attribution"
)

SESSION_MAP = {
    (0, 8): "Asian",
    (8, 14): "London",
    (14, 21): "NY",
}


def load_and_enrich(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df["timestamp"] = pd.to_datetime(
        df["timestamp"], format="%Y-%m-%d %H:%M", errors="coerce"
    )
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        return df

    df["pnl"] = df["pnl_net"].fillna(df["pnl_gross"])
    df["hour"] = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.day_name()
    df["week"] = df["timestamp"].dt.isocalendar()["week"]
    df["year"] = df["timestamp"].dt.year
    df["session"] = df["hour"].apply(_hour_to_session)
    df["strategy"] = df["notes"].apply(_extract_strategy)
    df["regime"] = df["notes"].apply(_extract_regime)
    return df


def _hour_to_session(h: int) -> str:
    for (lo, hi), name in SESSION_MAP.items():
        if lo <= h < hi:
            return name
    return "Off-hours"


def _extract_strategy(notes: str) -> str:
    n = str(notes).lower()
    if "rsi" in n:
        return "RSI-MeanReversion"
    if "macd" in n:
        return "MACD-Trend"
    if "breakout" in n:
        return "Breakout"
    if "grid" in n:
        return "Grid"
    if "ensemble" in n:
        return "Ensemble"
    return "default"


def _extract_regime(notes: str) -> str:
    n = str(notes).lower()
    if "trend" in n:
        return "trending"
    if "volatil" in n or "spike" in n:
        return "volatile"
    return "ranging"


def pivot_by_strategy_session(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return pd.pivot_table(
        df,
        index="strategy",
        columns="session",
        values="pnl",
        aggfunc="sum",
        fill_value=0,
    )


def compute_all_aggregations(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if df.empty:
        return {}

    dims = ["strategy", "regime", "session", "day_of_week", "direction"]
    aggs = {}
    for dim in dims:
        grp = df.groupby(dim)["pnl"].agg(["sum", "count", "mean", "median"])
        grp.columns = ["total_pnl", "trades", "avg_pnl", "median_pnl"]
        grp["win_rate"] = df.groupby(dim)["pnl"].apply(lambda x: (x > 0).mean())
        grp = grp.sort_values("total_pnl", ascending=False)
        aggs[dim] = grp

    aggs["pivot_strategy_session"] = pivot_by_strategy_session(df)

    if len(df) >= 5:
        pivot = df.pivot_table(
            index="timestamp", columns="strategy", values="pnl", aggfunc="sum"
        ).fillna(0)
        aggs["correlation"] = pivot.corr()
    else:
        aggs["correlation"] = pd.DataFrame()

    return aggs


def weights_from_aggs(aggs: dict[str, pd.DataFrame]) -> pd.Series:
    strat = aggs.get("strategy")
    if strat is None or strat.empty:
        return pd.Series(dtype=float)
    scores = strat["total_pnl"] * strat["win_rate"]
    scores = scores.clip(lower=0)
    total = scores.sum()
    if total == 0:
        return pd.Series(1.0 / len(scores), index=scores.index)
    return scores / total


def format_md_table(df: pd.DataFrame, money_cols: list[str] | None = None) -> str:
    if df.empty:
        return "_No data._\n"
    money_cols = money_cols or []
    rows = []
    header = "| " + " | ".join([df.index.name or "Metric"] + list(df.columns)) + " |"
    rows.append(header)
    rows.append("| " + " | ".join(["---"] * (len(df.columns) + 1)) + " |")
    for idx, row in df.iterrows():
        vals = []
        for c in df.columns:
            v = row[c]
            if c in money_cols:
                vals.append(f"${v:,.2f}")
            elif c == "win_rate":
                vals.append(f"{v:.1%}")
            elif c == "trades":
                vals.append(str(int(v)))
            else:
                vals.append(f"{v:.2f}")
        rows.append(f"| {idx} | {' | '.join(vals)} |")
    return "\n".join(rows) + "\n"


def render_vault_note(
    df: pd.DataFrame,
    aggs: dict[str, pd.DataFrame],
    weights: pd.Series,
    week: int,
    year: int,
) -> str:
    if df.empty:
        return _empty_note(week, year)

    total_pnl = df["pnl"].sum()
    total_trades = len(df)
    win_rate = (df["pnl"] > 0).mean()
    strat_agg = aggs.get("strategy", pd.DataFrame())
    best_s = strat_agg["total_pnl"].idxmax() if not strat_agg.empty else "N/A"
    worst_s = strat_agg["total_pnl"].idxmin() if not strat_agg.empty else "N/A"

    lines = [
        "---",
        "type: attribution",
        f"week: {week}",
        f"year: {year}",
        f"total_pnl: {round(total_pnl, 2)}",
        f'best_strategy: "{best_s}"',
        f'worst_strategy: "{worst_s}"',
        f"generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "---",
        "",
        f"# Week {week} — Performance Attribution (Pandas)",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total P&L | **${total_pnl:,.2f}** |",
        f"| Trades | {total_trades} |",
        f"| Win Rate | {win_rate:.1%} |",
        "",
    ]

    dim_labels = {
        "strategy": "Strategy",
        "regime": "Regime",
        "session": "Session",
        "day_of_week": "Day of Week",
        "direction": "Direction",
    }
    for dim, label in dim_labels.items():
        agg_df = aggs.get(dim, pd.DataFrame())
        lines.append(f"## P&L by {label}\n")
        lines.append(
            format_md_table(agg_df, money_cols=["total_pnl", "avg_pnl", "median_pnl"])
        )
        lines.append("")

    pivot = aggs.get("pivot_strategy_session", pd.DataFrame())
    if not pivot.empty:
        lines.append("## Strategy × Session Pivot\n")
        lines.append(format_md_table(pivot, money_cols=list(pivot.columns)))
        lines.append("")

    corr = aggs.get("correlation", pd.DataFrame())
    if not corr.empty:
        lines.append("## Strategy Correlation Matrix\n")
        lines.append(format_md_table(corr))
        lines.append("")

    if not weights.empty:
        lines.append("## Optimized Ensemble Weights\n")
        lines.append("| Strategy | Weight |")
        lines.append("| --- | --- |")
        for s, w in weights.sort_values(ascending=False).items():
            lines.append(f"| {s} | {w:.1%} |")
        lines.append("")
        lines.append(
            "> Derived from `total_pnl × win_rate`, normalized. Adjust weekly."
        )
        lines.append("")

    return "\n".join(lines)


def _empty_note(week: int, year: int) -> str:
    return (
        "---\ntype: attribution\n"
        f"week: {week}\nyear: {year}\n"
        "total_pnl: 0\nbest_strategy: N/A\nworst_strategy: N/A\n"
        f"generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}\n---\n\n"
        f"# Week {week} — No Trades\n\nNo trades recorded for this week.\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Attribution → Vault (pandas)")
    parser.add_argument("--week", type=int, default=None)
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--csv", type=str, default=None)
    parser.add_argument("--out", type=str, default=None, help="Override output path")
    args = parser.parse_args()

    today = dt.date.today()
    week = args.week or today.isocalendar()[1]
    year = args.year or today.year

    csv_path = Path(args.csv) if args.csv else TRADE_LOG
    df = load_and_enrich(csv_path)

    if not df.empty:
        df = df[(df["week"] == week) & (df["year"] == year)]

    aggs = compute_all_aggregations(df)
    weights = weights_from_aggs(aggs)
    md = render_vault_note(df, aggs, weights, week, year)

    out_dir = Path(args.out) if args.out else VAULT_OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"week-{week}.md"
    out_file.write_text(md, encoding="utf-8")
    print(f"Vault note written: {out_file}")


if __name__ == "__main__":
    main()
