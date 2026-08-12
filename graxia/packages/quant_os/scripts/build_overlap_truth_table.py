"""Build multi-asset overlap truth table.

Loads D1 CSVs for XAUUSD, EURUSD, BTCUSD, ETHUSD, computes:
- First/last dates per asset
- Missing trading days per asset
- Pairwise overlap windows
- Full-portfolio overlap window

Outputs to reports/mega_plan_evidence/multi_asset_overlap.md
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
REPORT_PATH = PROJECT_ROOT / "reports" / "mega_plan_evidence" / "multi_asset_overlap.md"

ASSETS = ["XAUUSD", "EURUSD", "BTCUSD", "ETHUSD"]


def load_d1(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}_D1.csv"
    if not path.exists():
        print(f"WARNING: {path} not found, skipping {symbol}")
        return pd.DataFrame()
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values("time").reset_index(drop=True)
    return df


def compute_missing_days(df: pd.DataFrame, label: str) -> dict:
    """Count missing weekdays between first and last date."""
    if df.empty:
        return {"first": None, "last": None, "rows": 0, "missing_weekdays": None}
    first = df["time"].min()
    last = df["time"].max()
    # Generate all weekdays in range
    all_days = pd.bdate_range(first, last, tz="UTC")
    actual_days = set(df["time"].dt.normalize().unique())
    expected_days = set(all_days.normalize())
    missing = expected_days - actual_days
    return {
        "first": first.strftime("%Y-%m-%d"),
        "last": last.strftime("%Y-%m-%d"),
        "rows": len(df),
        "unique_days": len(actual_days),
        "expected_weekdays": len(expected_days),
        "missing_weekdays": len(missing),
        "coverage_pct": round(100 * (1 - len(missing) / len(expected_days)), 2) if expected_days else 0,
    }


def main() -> int:
    frames = {}
    for sym in ASSETS:
        df = load_d1(sym)
        if not df.empty:
            frames[sym] = df

    if not frames:
        print("ERROR: No data files found", file=sys.stderr)
        return 1

    # Per-asset stats
    asset_stats = {}
    for sym, df in frames.items():
        asset_stats[sym] = compute_missing_days(df, sym)

    # Pairwise overlap
    pairwise = []
    for a, b in combinations(frames.keys(), 2):
        a_start = pd.Timestamp(asset_stats[a]["first"], tz="UTC")
        a_end = pd.Timestamp(asset_stats[a]["last"], tz="UTC")
        b_start = pd.Timestamp(asset_stats[b]["first"], tz="UTC")
        b_end = pd.Timestamp(asset_stats[b]["last"], tz="UTC")
        overlap_start = max(a_start, b_start)
        overlap_end = min(a_end, b_end)
        overlap_days = (overlap_end - overlap_start).days if overlap_end > overlap_start else 0
        # Count rows in overlap for each
        a_overlap = len(frames[a][(frames[a]["time"] >= overlap_start) & (frames[a]["time"] <= overlap_end)])
        b_overlap = len(frames[b][(frames[b]["time"] >= overlap_start) & (frames[b]["time"] <= overlap_end)])
        pairwise.append({
            "pair": f"{a}/{b}",
            "overlap_start": overlap_start.strftime("%Y-%m-%d"),
            "overlap_end": overlap_end.strftime("%Y-%m-%d"),
            "overlap_days": overlap_days,
            f"{a}_rows": a_overlap,
            f"{b}_rows": b_overlap,
        })

    # Full portfolio overlap
    all_starts = [pd.Timestamp(asset_stats[s]["first"], tz="UTC") for s in frames]
    all_ends = [pd.Timestamp(asset_stats[s]["last"], tz="UTC") for s in frames]
    full_start = max(all_starts)
    full_end = min(all_ends)
    full_overlap_days = (full_end - full_start).days if full_end > full_start else 0

    # Build report
    lines = [
        "# Multi-Asset Overlap Truth Table",
        "",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Assets:** {', '.join(frames.keys())}",
        "",
        "## Per-Asset Coverage",
        "",
        "| Asset | First Date | Last Date | Rows | Unique Days | Expected WD | Missing WD | Coverage % |",
        "|-------|-----------|-----------|------|-------------|-------------|------------|------------|",
    ]
    for sym, st in asset_stats.items():
        lines.append(
            f"| {sym} | {st['first']} | {st['last']} | {st['rows']} | {st['unique_days']} | "
            f"{st['expected_weekdays']} | {st['missing_weekdays']} | {st['coverage_pct']}% |"
        )

    lines += [
        "",
        "## Pairwise Overlap",
        "",
        "| Pair | Overlap Start | Overlap End | Overlap Days | Rows A | Rows B |",
        "|------|--------------|-------------|-------------|--------|--------|",
    ]
    for p in pairwise:
        lines.append(
            f"| {p['pair']} | {p['overlap_start']} | {p['overlap_end']} | {p['overlap_days']} | "
            f"{p[list(p.keys())[4]]} | {p[list(p.keys())[5]]} |"
        )

    lines += [
        "",
        "## Full Portfolio Overlap",
        "",
        f"- **Window:** {full_start.strftime('%Y-%m-%d')} to {full_end.strftime('%Y-%m-%d')}",
        f"- **Overlap days:** {full_overlap_days}",
        f"- **Overlap years:** {full_overlap_days / 365.25:.1f}",
        "",
        "## Key Findings",
        "",
    ]

    # Analysis
    crypto_only = [s for s in frames if s in ("BTCUSD", "ETHUSD")]
    if crypto_only and full_overlap_days > 0:
        lines.append(f"1. Full portfolio overlap is **{full_overlap_days} days** ({full_overlap_days/365.25:.1f} years), constrained by the shortest-history asset.")
    if full_overlap_days < 365 * 3:
        lines.append(f"2. **WARNING:** Full overlap is less than 3 years — insufficient for robust walk-forward validation on the full portfolio.")

    # Per-asset warnings
    for sym, st in asset_stats.items():
        if st['missing_weekdays'] and st['missing_weekdays'] > 100:
            lines.append(f"3. **{sym}** has {st['missing_weekdays']} missing weekdays ({100 - st['coverage_pct']}% gap) — investigate data source.")

    lines += [
        "",
        "## Verification",
        "```bash",
        "python scripts/build_overlap_truth_table.py",
        "```",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Report written to {REPORT_PATH.relative_to(PROJECT_ROOT)}")
    print(f"\nFull portfolio overlap: {full_start.strftime('%Y-%m-%d')} to {full_end.strftime('%Y-%m-%d')} ({full_overlap_days} days)")
    for sym, st in asset_stats.items():
        print(f"  {sym}: {st['first']} to {st['last']} ({st['rows']} rows, {st['coverage_pct']}% coverage)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
