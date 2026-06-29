"""Download Binance spot M1 klines for crypto pairs (BTCUSDT, ETHUSDT).

Usage:
    python scripts/download_binance_m1.py --symbol BTCUSDT --start 2024-01-01 --end 2024-01-31
    python scripts/download_binance_m1.py --symbol ETHUSDT --start 2024-01-01 --end 2024-01-31

Output is written to data/<symbol>_M1.csv with columns:
    time, open, high, low, close, volume

Binance public spot klines endpoint:
    GET https://api.binance.com/api/v3/klines

Rate limit: 1200 request weight / minute on /api/v3/klines (1 weight per call).
1000 candles max per call, so one month of M1 needs ~45 calls.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

BASE_URL = "https://api.binance.com/api/v3/klines"
COLUMNS = ["time", "open", "high", "low", "close", "volume"]
CANDLE_LIMIT = 1000
SLEEP_SECONDS = 0.06  # ~16 req/s, well under 1200 weight/min


def to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC)


def fetch_klines(symbol: str, interval: str, start_ms: int, end_ms: int) -> list[list]:
    """Fetch one page of klines from Binance spot API."""
    url = (
        f"{BASE_URL}?symbol={symbol}&interval={interval}"
        f"&startTime={start_ms}&endTime={end_ms}&limit={CANDLE_LIMIT}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "quant_os-binance-m1/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            logger.warning("HTTP %d for %s: %s", e.code, url, e.reason)
            if e.code == 429:
                time.sleep(2.0)
            else:
                time.sleep(0.5 * (attempt + 1))
        except Exception as e:
            logger.warning("Error fetching %s: %s (attempt %d/3)", url, e, attempt + 1)
            time.sleep(0.5 * (attempt + 1))
    return []



def download_symbol(symbol: str, start: datetime, end: datetime, interval: str = "1m") -> pd.DataFrame:
    """Download all klines for a symbol between start and end (UTC)."""
    all_rows: list[list] = []
    current = start
    page = 0
    while current < end:
        start_ms = to_ms(current)
        end_ms = to_ms(min(current + timedelta(minutes=CANDLE_LIMIT), end))
        rows = fetch_klines(symbol, interval, start_ms, end_ms)
        if not rows:
            break
        for row in rows:
            all_rows.append([
                from_ms(row[0]).strftime("%Y-%m-%d %H:%M:%S"),
                float(row[1]),
                float(row[2]),
                float(row[3]),
                float(row[4]),
                float(row[5]),
            ])
        last_close_ms = rows[-1][6]
        next_start = from_ms(last_close_ms) + timedelta(milliseconds=1)
        if next_start <= current:
            break
        current = next_start
        page += 1
        if page % 10 == 0:
            logger.info("  fetched %d pages, %d rows so far", page, len(all_rows))
        time.sleep(SLEEP_SECONDS)
    df = pd.DataFrame(all_rows, columns=COLUMNS)
    df.drop_duplicates(subset=["time"], keep="first", inplace=True)
    return df


def merge_with_existing(df: pd.DataFrame, path: Path) -> pd.DataFrame:
    """Merge newly downloaded rows with existing CSV, drop duplicates."""
    if not path.exists():
        return df
    try:
        existing = pd.read_csv(path)
        combined = pd.concat([existing, df], ignore_index=True)
        combined.drop_duplicates(subset=["time"], keep="last", inplace=True)
        combined.sort_values("time", inplace=True)
        return combined
    except Exception as e:
        logger.warning("Could not merge with existing %s: %s", path, e)
        return df


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download Binance spot M1 klines")
    parser.add_argument("--symbol", required=True, help="e.g. BTCUSDT or ETHUSDT")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--interval", default="1m", help="Kline interval (default: 1m)")
    parser.add_argument("--output", type=str, default=str(DATA_DIR), help="Output directory")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=UTC)
    end = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=UTC) + timedelta(days=1)
    if start >= end:
        logger.error("Start must be before end")
        return 1

    logger.info("Downloading %s %s from %s to %s", args.symbol, args.interval, start.date(), end.date())
    df = download_symbol(args.symbol, start, end, args.interval)
    if df.empty:
        logger.error("No data downloaded")
        return 1

    # Map symbol to internal CSV name (BTCUSDT -> BTCUSD_M1.csv to match repo convention)
    internal_symbol = args.symbol.replace("USDT", "USD").replace("USD", "USD")  # keep BTCUSD style
    out_path = out_dir / f"{internal_symbol}_M1.csv"
    df = merge_with_existing(df, out_path)
    df.to_csv(out_path, index=False)
    logger.info("Saved %d rows to %s", len(df), out_path)
    logger.info("Range: %s -> %s", df["time"].min(), df["time"].max())
    return 0


if __name__ == "__main__":
    sys.exit(main())
