"""Inspect zero-spread ratio in backfilled ticks."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
TICK_DIR = ROOT / "data" / "ticks"

for sym in ["BTCUSD", "EURUSD"]:
    df = pd.read_parquet(TICK_DIR / f"{sym}_ticks_backfill.parquet")
    mid = (df["bid"] + df["ask"]) / 2.0
    sbps = (df["ask"] - df["bid"]) / mid.replace(0, pd.NA) * 10_000.0
    zero = (sbps == 0).sum()
    print(f"{sym}: N={len(df):,} | zero-spread: {zero:,} ({zero/len(df)*100:.1f}%)")
    print(
        f"  ask>bid: {(df['ask'] > df['bid']).sum():,} | ask<bid: {(df['ask'] < df['bid']).sum():,} | bid==ask: {(df['bid'] == df['ask']).sum():,}"
    )
