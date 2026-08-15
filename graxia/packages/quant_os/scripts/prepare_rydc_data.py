"""
RYDC Data Preparation Pipeline

Downloads and aligns all data needed for Real-Yield Divergence Continuation hypothesis:
1. XAUUSD daily OHLCV (from Dukascopy or existing data)
2. DXY daily close (from Yahoo/Stooq)
3. DFII10 real yield (from FRED)
4. FOMC/CPI event dates (from event_filter module)

Output: data/rydc/ directory with aligned, merged data.

Usage:
    python scripts/prepare_rydc_data.py
    python scripts/prepare_rydc_data.py --start 2018-01-01 --end 2026-07-01
    python scripts/prepare_rydc_data.py --fred-api-key YOUR_KEY
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date as Date, datetime, timedelta, UTC
from io import StringIO
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── Constants ──
DATA_DIR = PROJECT_ROOT / "data"
RYDC_DIR = DATA_DIR / "rydc"
FRED_DIR = DATA_DIR / "market_data" / "fred"

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def download_xauusd(start: Date, end: Date) -> list[dict] | None:
    """Load XAUUSD daily data from existing CSV."""
    xau_file = DATA_DIR / "XAUUSD_D1.csv"
    if not xau_file.exists():
        print(f"  XAUUSD file not found: {xau_file}")
        return None

    rows = []
    with open(xau_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                dt = datetime.strptime(row["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
                if start <= dt.date() <= end:
                    rows.append({
                        "date": dt.strftime("%Y-%m-%d"),
                        "xau_close": float(row["close"]),
                        "xau_high": float(row["high"]),
                        "xau_low": float(row["low"]),
                    })
            except (ValueError, KeyError):
                continue

    if not rows:
        print("  No XAUUSD data in date range")
        return None

    print(f"  XAUUSD: {len(rows)} rows ({rows[0]['date']} -> {rows[-1]['date']})")
    return rows


def download_dxy(start: Date, end: Date) -> list[dict] | None:
    """Download DXY daily data from Yahoo Finance."""
    start_ts = int(datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp())
    end_ts = int(datetime(end.year, end.month, end.day, tzinfo=UTC).timestamp())

    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB"
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
        closes = quote.get("close", [])

        rows = []
        for i, ts in enumerate(timestamps):
            if ts is None or i >= len(closes) or closes[i] is None:
                continue
            dt = datetime.fromtimestamp(ts, tz=UTC)
            rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "dxy_close": round(float(closes[i]), 4),
            })

        print(f"  DXY: {len(rows)} rows ({rows[0]['date']} -> {rows[-1]['date']})")
        return rows

    except Exception as e:
        print(f"  DXY download failed: {e}")
        return None


def download_dfii10(api_key: str, start: Date, end: Date) -> list[dict] | None:
    """Download DFII10 (10Y TIPS real yield) from FRED API."""
    url = (
        f"{FRED_BASE_URL}?series_id=DFII10"
        f"&api_key={api_key}"
        f"&file_type=json"
        f"&observation_start={start.isoformat()}"
        f"&observation_end={end.isoformat()}"
        f"&frequency=d&aggregation_method=avg"
    )

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        observations = data.get("observations", [])
        rows = []
        for obs in observations:
            value = obs.get("value", ".")
            if value == ".":
                continue
            rows.append({
                "date": obs["date"],
                "dfii10": round(float(value), 4),
            })

        if rows:
            print(f"  DFII10: {len(rows)} rows ({rows[0]['date']} -> {rows[-1]['date']})")
        return rows if rows else None

    except Exception as e:
        print(f"  DFII10 download failed: {e}")
        return None


def load_dfii10_from_cache(start: Date, end: Date) -> list[dict] | None:
    """Try to load DFII10 from existing FRED cache."""
    cache_file = FRED_DIR / "DFII10.csv"
    if not cache_file.exists():
        return None

    rows = []
    with open(cache_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                dt = datetime.strptime(row["date"], "%Y-%m-%d").replace(tzinfo=UTC)
                if start <= dt.date() <= end:
                    rows.append({
                        "date": dt.strftime("%Y-%m-%d"),
                        "dfii10": round(float(row["value"]), 4),
                    })
            except (ValueError, KeyError):
                continue

    if rows:
        print(f"  DFII10 (cache): {len(rows)} rows ({rows[0]['date']} -> {rows[-1]['date']})")
    return rows if rows else None


def merge_data(
    xau: list[dict],
    dxy: list[dict],
    dfii: list[dict],
) -> list[dict]:
    """Merge all data series on date, forward-fill missing values."""
    # Build date index
    xau_by_date = {r["date"]: r for r in xau}
    dxy_by_date = {r["date"]: r for r in dxy}
    dfii_by_date = {r["date"]: r for r in dfii}

    # Get all unique dates from XAUUSD (primary series)
    all_dates = sorted(xau_by_date.keys())

    merged = []
    last_dxy = None
    last_dfii = None

    for date_str in all_dates:
        xau_row = xau_by_date[date_str]

        # DXY: forward-fill if missing
        if date_str in dxy_by_date:
            last_dxy = dxy_by_date[date_str]["dxy_close"]

        # DFII10: forward-fill if missing
        if date_str in dfii_by_date:
            last_dfii = dfii_by_date[date_str]["dfii10"]

        if last_dxy is None or last_dfii is None:
            continue  # Skip if we don't have all series yet

        merged.append({
            "date": date_str,
            "xau_close": xau_row["xau_close"],
            "xau_high": xau_row["xau_high"],
            "xau_low": xau_row["xau_low"],
            "dxy_close": last_dxy,
            "dfii10": last_dfii,
        })

    return merged


def save_csv(rows: list[dict], output_path: Path) -> int:
    """Save merged data to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "xau_close", "xau_high", "xau_low", "dxy_close", "dfii10"])
        for row in rows:
            writer.writerow([
                row["date"],
                row["xau_close"],
                row["xau_high"],
                row["xau_low"],
                row["dxy_close"],
                row["dfii10"],
            ])

    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Prepare RYDC data")
    parser.add_argument("--start", type=str, default="2018-01-01",
                        help="Start date YYYY-MM-DD (default: 2018-01-01)")
    parser.add_argument("--end", type=str, default=None,
                        help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--fred-api-key", type=str, default=None,
                        help="FRED API key (or set FRED_API_KEY env var)")
    args = parser.parse_args()

    start_date = Date.fromisoformat(args.start)
    end_date = Date.fromisoformat(args.end) if args.end else Date.today()
    fred_key = args.fred_api_key or os.environ.get("FRED_API_KEY", "")

    print("=" * 60)
    print("RYDC Data Preparation Pipeline")
    print("=" * 60)
    print(f"Date range: {start_date} -> {end_date}")
    print(f"Output: {RYDC_DIR}")
    print()

    # Step 1: Download XAUUSD
    print("[1/3] Loading XAUUSD data...")
    xau = download_xauusd(start_date, end_date)
    if not xau:
        print("ERROR: No XAUUSD data available")
        sys.exit(1)

    # Step 2: Download DXY
    print("[2/3] Downloading DXY data...")
    dxy = download_dxy(start_date, end_date)
    if not dxy:
        print("ERROR: No DXY data available")
        sys.exit(1)

    # Step 3: Download DFII10
    print("[3/3] Downloading DFII10 data...")
    dfii = None

    # Try cache first
    dfii = load_dfii10_from_cache(start_date, end_date)

    # Try FRED API
    if not dfii and fred_key:
        dfii = download_dfii10(fred_key, start_date, end_date)

    if not dfii:
        print("WARNING: No DFII10 data available")
        print("  Set FRED_API_KEY or run: python scripts/download_fred_all.py")
        print("  Continuing without DFII10 (will use zero changes)")

        # Create dummy DFII10 data
        dfii = [{"date": r["date"], "dfii10": 0.0} for r in xau]

    # Merge
    print("\nMerging data...")
    merged = merge_data(xau, dxy, dfii)

    if not merged:
        print("ERROR: No overlapping data after merge")
        sys.exit(1)

    # Save
    output_file = RYDC_DIR / "rydc_daily.csv"
    n = save_csv(merged, output_file)

    print(f"\nSaved {n} rows to {output_file}")
    print(f"Date range: {merged[0]['date']} -> {merged[-1]['date']}")

    # Summary stats
    xau_returns = []
    for i in range(1, len(merged)):
        ret = (merged[i]["xau_close"] / merged[i-1]["xau_close"]) - 1.0
        xau_returns.append(ret)

    if xau_returns:
        import statistics
        print(f"\nXAUUSD return stats:")
        print(f"  Mean: {statistics.mean(xau_returns)*100:.4f}%")
        print(f"  Std:  {statistics.stdev(xau_returns)*100:.4f}%")
        print(f"  Min:  {min(xau_returns)*100:.4f}%")
        print(f"  Max:  {max(xau_returns)*100:.4f}%")


if __name__ == "__main__":
    main()
