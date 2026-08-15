"""Backfill historical ticks from MT5 for BTCUSD/EURUSD (Step 1 shortcut).

MT5 serves ~5.5 days of tick history (bid/ask). We pull the full available
window now, store to parquet, and compute spread stats immediately — no need
to wait 7 days of 5-min polling for usable calibration numbers. The live
daemon keeps appending ticks past NFP (2026-08-07); rerun recalibrate later.

Usage:
    python scripts/backfill_ticks_shortcut.py            # both symbols, all available
    python scripts/backfill_ticks_shortcut.py --symbols EURUSD
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import MetaTrader5 as mt5  # noqa: N813 — canonical MT5 alias used across the repo
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
TICK_DIR = ROOT / "data" / "ticks"
TICK_DIR.mkdir(parents=True, exist_ok=True)

LOOKBACK_DAYS = 8  # MT5 caps tick history ~5.5d; ask for more, take what's served


def fetch_ticks(sym: str, days: int) -> pd.DataFrame | None:
    from_dt = datetime.now(UTC) - timedelta(days=days)
    to_dt = datetime.now(UTC)
    ticks = mt5.copy_ticks_range(sym, from_dt, to_dt, mt5.COPY_TICKS_ALL)
    if ticks is None or len(ticks) == 0:
        return None
    df = pd.DataFrame(ticks)
    df = df[["time_msc", "bid", "ask", "last", "volume"]]
    df["time"] = pd.to_datetime(df["time_msc"], unit="ms", utc=True)
    # Match DuckDBStore tick schema (view projection expects these columns).
    df["symbol"] = sym
    df["source"] = "mt5_backfill"
    df["data_quality"] = "ok"
    df = df.sort_values("time").drop_duplicates(subset=["time_msc", "bid", "ask"])
    return df


def compute_stats(df: pd.DataFrame, sym: str) -> None:
    if df is None or len(df) == 0:
        print(f"  {sym}: NO TICKS")
        return
    mid = (df["bid"] + df["ask"]) / 2.0
    spread_bps = ((df["ask"] - df["bid"]) / mid.replace(0, pd.NA) * 10_000.0).dropna()
    if len(spread_bps) == 0:
        print(f"  {sym}: all zero spreads")
        return
    qs = spread_bps.quantile([0.5, 0.9, 0.95, 0.99]).round(4)
    print(
        f"  {sym}: N={len(df):,} ticks | median={qs[0.5]:.4f} p90={qs[0.9]:.4f} "
        f"p95={qs[0.95]:.4f} p99={qs[0.99]:.4f} bps | "
        f"range {df['time'].min().date()} -> {df['time'].max().date()}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill MT5 ticks for spread stats")
    parser.add_argument("--symbols", nargs="+", default=["BTCUSD", "EURUSD"])
    parser.add_argument("--days", type=int, default=LOOKBACK_DAYS)
    args = parser.parse_args()

    ok = mt5.initialize()
    if not ok:
        print("MT5 init failed:", mt5.last_error())
        sys.exit(1)

    for sym in args.symbols:
        df = fetch_ticks(sym, args.days)
        compute_stats(df, sym)
        if df is not None and len(df):
            out = TICK_DIR / f"{sym}_ticks_backfill.parquet"
            df.to_parquet(out, index=False)
            print(f"  saved {out} ({len(df):,} rows)")

    mt5.shutdown()
    print("done")


if __name__ == "__main__":
    main()
