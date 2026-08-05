"""Probe MT5 tick history depth for BTCUSD/EURUSD (shortcut for Step 1)."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

import MetaTrader5 as mt5  # noqa: N813 — canonical MT5 alias used across the repo
import pandas as pd


def probe(sym: str, days: int) -> None:
    from_dt = datetime.now(UTC) - timedelta(days=days)
    to_dt = datetime.now(UTC)
    ticks = mt5.copy_ticks_range(sym, from_dt, to_dt, mt5.COPY_TICKS_ALL)
    if ticks is not None and len(ticks):
        df = pd.DataFrame(ticks)
        first = datetime.fromtimestamp(df.iloc[0]["time_msc"] / 1000, tz=UTC)
        last = datetime.fromtimestamp(df.iloc[-1]["time_msc"] / 1000, tz=UTC)
        print(f"{sym} {days}d: {len(ticks):,} ticks | {first.date()} -> {last.date()}")
    else:
        print(f"{sym} {days}d: EMPTY/FAILED ({mt5.last_error()})")


def main() -> None:
    ok = mt5.initialize()
    if not ok:
        print("MT5 init failed:", mt5.last_error())
        sys.exit(1)
    for sym in ["BTCUSD", "EURUSD"]:
        for days in [7, 10, 30, 90]:
            probe(sym, days)
    mt5.shutdown()


if __name__ == "__main__":
    main()
