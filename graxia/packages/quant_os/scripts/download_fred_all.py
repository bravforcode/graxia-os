"""Download ALL FRED data for XAUUSD gold trading.

Fetches 10 years of daily data (2016-01-01 to 2026-06-26) for 40+ series
across interest rates, gold/volatility, oil, dollar, FX, economic, credit,
and liquidity categories. Saves individual CSVs + a combined summary.

Usage:
    python scripts/download_fred_all.py
"""

import os
import sys
import csv
import urllib.request
import urllib.error
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────
API_KEY = os.environ.get("FRED_API_KEY", "")
BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

START_DATE = "2016-01-01"
END_DATE = "2026-06-26"
FILE_TYPE = "json"  # json is more reliable than csv for FRED API

# All series organized by category
SERIES = {
    "interest_rates": [
        "DFII10", "DGS10", "DGS2", "DGS30", "DGS5", "DGS7",
        "DGS3MO", "DGS6MO", "T5YIE", "T5YIFR", "T10YIE", "T10Y2Y",
    ],
    "gold_volatility": ["GVZCLS", "VIXCLS"],
    "oil": ["DCOILWTICO", "DCOILBRENTEU"],
    "dollar": ["DTWEXBGS"],
    "fx": ["DEXUSEU", "DEXJPUS"],
    "economic": [
        "UNRATE", "CPIAUCSL", "CPILFESL", "FEDFUNDS",
        "INDPRO", "UMCSENT", "A191RL1Q225SBEA",
    ],
    "credit": [
        "BAMLH0A0HYM2", "BAMLH0A0HYM2EY", "BAMLH0A1HYBB",
        "TEDRATE", "BAA10Y",
    ],
    "liquidity": ["WALCL", "BOGMBASE", "RRPONTSYD", "WTREGEN"],
}

# Output directory
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "market_data" / "fred"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Rate limit: FRED API allows ~120 req/min, we'll be conservative
REQUEST_DELAY = 0.5  # seconds between requests

# Series that are NOT daily frequency — don't pass frequency=d for these
NON_DAILY_SERIES = {
    "UNRATE", "CPIAUCSL", "CPILFESL", "FEDFUNDS", "INDPRO", "UMCSENT",
    "A191RL1Q225SBEA", "WALCL", "BOGMBASE", "WTREGEN",
}


def fetch_series(series_id: str) -> list[dict]:
    """Fetch observations for a single FRED series via JSON API."""
    params = (
        f"?series_id={series_id}"
        f"&api_key={API_KEY}"
        f"&file_type={FILE_TYPE}"
        f"&observation_start={START_DATE}"
        f"&observation_end={END_DATE}"
    )
    # Only add frequency=d for daily series
    if series_id not in NON_DAILY_SERIES:
        params += "&frequency=d&aggregation_method=avg"

    url = BASE_URL + params
    req = urllib.request.Request(url, headers={"User-Agent": "FRED-Downloader/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("observations", [])
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} for {series_id}: {e.reason}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"  Error for {series_id}: {e}", file=sys.stderr)
        return []


def save_csv(series_id: str, observations: list[dict]) -> dict:
    """Save observations to a CSV file. Return summary stats."""
    filepath = OUT_DIR / f"{series_id}.csv"

    rows_written = 0
    missing_count = 0
    date_min = None
    date_max = None

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "value"])

        for obs in observations:
            date_str = obs.get("date", "")
            value_str = obs.get("value", ".")

            if not date_str:
                continue

            # FRED uses "." for missing values
            if value_str == ".":
                missing_count += 1
                continue  # skip missing rows entirely for clean CSV

            writer.writerow([date_str, value_str])
            rows_written += 1

            if date_min is None or date_str < date_min:
                date_min = date_str
            if date_max is None or date_str > date_max:
                date_max = date_str

    total_expected = len(observations)
    missing_pct = (missing_count / total_expected * 100) if total_expected > 0 else 0.0

    return {
        "series_id": series_id,
        "rows": rows_written,
        "date_min": date_min or "",
        "date_max": date_max or "",
        "missing_count": missing_count,
        "missing_pct": round(missing_pct, 1),
        "file": filepath.name,
    }


def main():
    all_series = []
    for cat, ids in SERIES.items():
        all_series.extend(ids)

    total = len(all_series)
    print(f"Downloading {total} FRED series ({START_DATE} to {END_DATE})...")
    print(f"Output: {OUT_DIR}\n")

    summaries = []
    errors = []

    for i, sid in enumerate(all_series, 1):
        print(f"[{i:2d}/{total}] {sid}...", end=" ", flush=True)
        observations = fetch_series(sid)

        if not observations:
            print("NO DATA")
            errors.append(sid)
            summaries.append({
                "series_id": sid, "rows": 0,
                "date_min": "", "date_max": "",
                "missing_count": 0, "missing_pct": 100.0,
                "file": f"{sid}.csv",
            })
        else:
            stats = save_csv(sid, observations)
            print(f"{stats['rows']} rows ({stats['date_min']} to {stats['date_max']})")
            summaries.append(stats)

        if i < total:
            time.sleep(REQUEST_DELAY)

    # ── Write summary CSV ──────────────────────────────────────────────────
    summary_path = OUT_DIR / "_summary.csv"
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "series_id", "rows", "date_min", "date_max",
            "missing_count", "missing_pct", "file",
        ])
        writer.writeheader()
        writer.writerows(summaries)

    # ── Print summary table ────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"{'Series':<20} {'Rows':>8} {'Date Range':<26} {'Missing%':>8}")
    print("-" * 80)
    for s in summaries:
        date_range = f"{s['date_min']} → {s['date_max']}" if s['date_min'] else "N/A"
        print(f"{s['series_id']:<20} {s['rows']:>8} {date_range:<26} {s['missing_pct']:>7.1f}%")

    print("-" * 80)
    total_rows = sum(s["rows"] for s in summaries)
    ok = sum(1 for s in summaries if s["rows"] > 0)
    print(f"Total: {ok}/{total} series downloaded, {total_rows:,} total rows")

    if errors:
        print(f"\nFailed: {', '.join(errors)}")

    print(f"\nSummary saved to: {summary_path}")
    print("Done.")


if __name__ == "__main__":
    main()
