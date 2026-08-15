"""Dukascopy bi5 tick worker (datafeed.dukascopy.com, no auth, stdlib only).

Each hour of the day is a separate LZMA-compressed .bi5 file of 5xuint32
records: (time offset ms within hour, bid, ask, bid_vol, ask_vol). Prices
are scaled by 1e5 (5 decimal digits — XAUUSD 2300.00 stored as 230000000;
uint32 cannot hold a 1e12 scale for these price levels). Hours with no
data (404) are skipped; output is per-day parquet with
source="dukascopy". Idempotent per day.
"""

from __future__ import annotations

import lzma
import struct
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

BASE_URL = "https://datafeed.dukascopy.com/datafeed"
UNSUPPORTED = {"BTCUSD"}  # no crypto on Dukascopy
PRICE_SCALE = 1e5


def _parse_bi5(data: bytes, hour_start_msc: int) -> list[dict]:
    ticks = []
    off = 0
    while off + 20 <= len(data):
        t, bid, ask, bvol, avol = struct.unpack_from("<5I", data, off)
        off += 20
        ticks.append(
            {
                "time_msc": hour_start_msc + t,
                "bid": bid / PRICE_SCALE,
                "ask": ask / PRICE_SCALE,
                "last": 0.0,
                "volume": float(bvol + avol),
                "flags": 0,
            }
        )
    return ticks


def fetch_ticks(symbol: str, start_date: str, end_date: str, out_dir: str | Path) -> list[Path]:
    if symbol in UNSUPPORTED:
        print(f"[dukascopy] {symbol} unsupported — skipping")
        return []
    out_dir = Path(out_dir)
    written: list[Path] = []
    day = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    while day <= end:
        path = out_dir / f"{symbol}_{day.isoformat()}.parquet"
        if path.exists():
            day += timedelta(days=1)
            continue
        rows = []
        for hour in range(24):
            url = f"{BASE_URL}/{symbol}/{day.year:04d}/{day.month - 1:02d}/{day.day:02d}/" f"{hour:02d}h_ticks.bi5"
            try:
                with urllib.request.urlopen(url, timeout=60) as resp:
                    raw = lzma.decompress(resp.read())
            except Exception:
                continue  # hour with no data / 404
            hour_msc = int(datetime(day.year, day.month, day.day, hour, tzinfo=UTC).timestamp() * 1000)
            rows.extend(_parse_bi5(raw, hour_msc))
        if rows:
            df = pd.DataFrame(rows)
            df["symbol"] = symbol
            df["source"] = "dukascopy"
            df["data_quality"] = "VALID"
            df["timestamp_utc"] = pd.to_datetime(df["time_msc"], unit="ms", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            path.parent.mkdir(parents=True, exist_ok=True)
            df[
                [
                    "time_msc",
                    "timestamp_utc",
                    "symbol",
                    "bid",
                    "ask",
                    "last",
                    "volume",
                    "flags",
                    "source",
                    "data_quality",
                ]
            ].to_parquet(path, index=False)
            written.append(path)
        day += timedelta(days=1)
    return written
