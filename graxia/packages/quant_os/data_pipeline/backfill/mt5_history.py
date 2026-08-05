"""MT5 history backfill worker — copy_ticks_range into per-UTC-day parquet.

Idempotent per day file: days already written are skipped on re-run.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from broker.mt5_gateway import get_ticks_range


def _get_ticks_range(symbol, from_msc, to_msc, count=100000, flags=None):
    return get_ticks_range(symbol, from_msc, to_msc, count=count)


def fetch_ticks(symbol: str, from_msc: int, to_msc: int, out_dir: str | Path) -> list[Path]:
    out_dir = Path(out_dir)
    written: list[Path] = []
    all_ticks: list[dict] = []
    cursor = from_msc
    while cursor <= to_msc:
        batch = _get_ticks_range(symbol, cursor, to_msc)
        if not batch:
            break
        all_ticks.extend(batch)
        last = max(t["time_msc"] for t in batch)
        if last >= to_msc or last < cursor:
            break  # caught up, or batch did not advance — stop
        cursor = last + 1
    if not all_ticks:
        return []
    df = pd.DataFrame(all_ticks)
    df["timestamp_utc"] = pd.to_datetime(df["time_msc"], unit="ms", utc=True)
    df["symbol"] = symbol
    df["source"] = "mt5_history"
    df["data_quality"] = "VALID"
    for day, group in df.groupby(df["timestamp_utc"].dt.date):
        path = out_dir / f"{symbol}_{day.isoformat()}.parquet"
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        group.sort_values("time_msc")[
            ["time_msc", "timestamp_utc", "symbol", "bid", "ask", "last", "volume", "flags", "source", "data_quality"]
        ].to_parquet(path, index=False)
        written.append(path)
    return written
