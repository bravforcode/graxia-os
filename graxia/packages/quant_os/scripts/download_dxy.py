"""
DXY (Dollar Index) Downloader — Multi-source with fallback.

Downloads DXY daily data from free sources:
1. Yahoo Finance (DX-Y.NYB) — primary
2. Stooq.com (dxy) — fallback

Output: data/DXY_D1.csv in standard OHLCV format.

Usage:
    python scripts/download_dxy.py
    python scripts/download_dxy.py --start 2015-01-01 --end 2026-07-01
    python scripts/download_dxy.py --source stooq
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date as Date, datetime, timedelta, UTC
from io import StringIO
from pathlib import Path

# ── Constants ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_FILE = DATA_DIR / "DXY_D1.csv"

YAHOO_SYMBOL = "DX-Y.NYB"
STOOQ_SYMBOL = "dxy"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def download_yahoo(symbol: str, start: Date, end: Date) -> list[dict] | None:
    """Download daily OHLCV from Yahoo Finance."""
    start_ts = int(datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp())
    end_ts = int(datetime(end.year, end.month, end.day, tzinfo=UTC).timestamp())

    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={start_ts}&period2={end_ts}&interval=1d"
    )

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        result = data.get("chart", {}).get("result", [])
        if not result:
            return None

        timestamps = result[0].get("timestamp", [])
        quote = result[0].get("indicators", {}).get("quote", [{}])[0]

        opens = quote.get("open", [])
        highs = quote.get("high", [])
        lows = quote.get("low", [])
        closes = quote.get("close", [])
        volumes = quote.get("volume", [])

        rows = []
        for i, ts in enumerate(timestamps):
            if ts is None:
                continue
            dt = datetime.fromtimestamp(ts, tz=UTC)
            o = opens[i] if i < len(opens) and opens[i] is not None else None
            h = highs[i] if i < len(highs) and highs[i] is not None else None
            l = lows[i] if i < len(lows) and lows[i] is not None else None
            c = closes[i] if i < len(closes) and closes[i] is not None else None
            v = volumes[i] if i < len(volumes) and volumes[i] is not None else 0

            if o is None or h is None or l is None or c is None:
                continue

            rows.append({
                "time": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "open": round(o, 4),
                "high": round(h, 4),
                "low": round(l, 4),
                "close": round(c, 4),
                "volume": int(v),
            })

        return rows if rows else None

    except Exception as e:
        print(f"  Yahoo download failed: {e}", file=sys.stderr)
        return None


def download_stooq(symbol: str, start: Date, end: Date) -> list[dict] | None:
    """Download daily OHLCV from Stooq.com."""
    url = (
        f"https://stooq.com/q/d/l/?s={symbol}&i=d"
        f"&d1={start.isoformat()}&d2={end.isoformat()}"
    )

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")

        if not text or "Date" not in text:
            return None

        rows = []
        reader = csv.DictReader(StringIO(text))
        for row in reader:
            try:
                dt = datetime.strptime(row["Date"], "%Y-%m-%d").replace(tzinfo=UTC)
                rows.append({
                    "time": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": int(float(row.get("Volume", 0))),
                })
            except (ValueError, KeyError):
                continue

        return rows if rows else None

    except Exception as e:
        print(f"  Stooq download failed: {e}", file=sys.stderr)
        return None


def save_csv(rows: list[dict], output_path: Path) -> int:
    """Save rows to CSV in standard OHLCV format."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "open", "high", "low", "close", "volume"])
        for row in rows:
            writer.writerow([
                row["time"],
                row["open"],
                row["high"],
                row["low"],
                row["close"],
                row["volume"],
            ])

    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Download DXY daily data")
    parser.add_argument("--start", type=str, default="2015-01-01",
                        help="Start date YYYY-MM-DD (default: 2015-01-01)")
    parser.add_argument("--end", type=str, default=None,
                        help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--source", type=str, default="auto",
                        choices=["auto", "yahoo", "stooq"],
                        help="Data source (default: auto)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output file path (default: data/DXY_D1.csv)")
    args = parser.parse_args()

    start_date = Date.fromisoformat(args.start)
    end_date = Date.fromisoformat(args.end) if args.end else Date.today()
    output_path = Path(args.output) if args.output else OUTPUT_FILE

    print(f"Downloading DXY data: {start_date} -> {end_date}")
    print(f"Output: {output_path}")

    rows = None

    # Try Yahoo Finance first
    if args.source in ("auto", "yahoo"):
        print("  Trying Yahoo Finance (DX-Y.NYB)...", end=" ", flush=True)
        rows = download_yahoo(YAHOO_SYMBOL, start_date, end_date)
        if rows:
            print(f"OK ({len(rows)} rows)")
        else:
            print("FAILED")

    # Fallback to Stooq
    if rows is None and args.source in ("auto", "stooq"):
        print("  Trying Stooq.com (dxy)...", end=" ", flush=True)
        rows = download_stooq(STOOQ_SYMBOL, start_date, end_date)
        if rows:
            print(f"OK ({len(rows)} rows)")
        else:
            print("FAILED")

    if not rows:
        print("ERROR: No data downloaded from any source")
        sys.exit(1)

    # Sort by date
    rows.sort(key=lambda r: r["time"])

    # Save
    n = save_csv(rows, output_path)
    print(f"\nSaved {n} rows to {output_path}")
    print(f"Date range: {rows[0]['time']} -> {rows[-1]['time']}")


if __name__ == "__main__":
    main()
