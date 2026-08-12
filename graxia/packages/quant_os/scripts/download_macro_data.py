"""CLI script to download all FRED macro data and COT reports."""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.data.fred_client import FredClient, SERIES_CATALOG
from core.data.cot_reports import fetch_cot_gold_range


def main():
    parser = argparse.ArgumentParser(description="Download FRED macro data and COT reports")
    parser.add_argument("--start", default="2020-01-01", help="Start date YYYY-MM-DD (default: 2020-01-01)")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--series", nargs="*", help="Specific FRED series IDs (default: all catalog)")
    parser.add_argument("--cot-start", type=int, default=2020, help="COT start year (default: 2020)")
    parser.add_argument("--cot-end", type=int, default=None, help="COT end year (default: current year)")
    parser.add_argument("--force", action="store_true", help="Force re-download, skip cache")
    parser.add_argument("--no-cot", action="store_true", help="Skip COT download")
    args = parser.parse_args()

    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        print("ERROR: FRED_API_KEY not set in environment.")
        print("  Set via: $env:FRED_API_KEY='your-key'  (PowerShell)")
        print("  Or add to .env file in project root.")
        sys.exit(1)

    from datetime import date
    end_date = args.end or date.today().strftime("%Y-%m-%d")
    cot_end = args.cot_end or date.today().year

    client = FredClient(api_key=api_key)

    series_ids = args.series if args.series else list(SERIES_CATALOG.keys())

    print("=" * 60)
    print(f"FRED Macro Download: {args.start} → {end_date}")
    print("=" * 60)
    print(f"\nFetching {len(series_ids)} series...")

    results = []
    for sid in series_ids:
        desc = SERIES_CATALOG.get(sid, sid)
        try:
            s = client.fetch_series(sid, args.start, end_date, force=args.force)
            if s.empty:
                print(f"  {sid:15s} → EMPTY (no data in range)")
                results.append((sid, desc, args.start, end_date, 0, "EMPTY"))
            else:
                cache_path = client._cache_path(sid, args.start, end_date)
                row_count = len(s)
                date_range = f"{s.index[0].strftime('%Y-%m-%d')} → {s.index[-1].strftime('%Y-%m-%d')}"
                print(f"  {sid:15s} → {row_count:5d} rows | {date_range} | {cache_path}")
                results.append((sid, desc, args.start, end_date, row_count, str(cache_path)))
        except Exception as e:
            print(f"  {sid:15s} → ERROR: {e}")
            results.append((sid, desc, args.start, end_date, 0, f"ERROR: {e}"))

    if not args.no_cot:
        print(f"\nFetching COT gold data ({args.cot_start}-{cot_end})...")
        try:
            cot_df = fetch_cot_gold_range(args.cot_start, cot_end, force=args.force)
            if cot_df.empty:
                print("  COT → EMPTY")
            else:
                cot_cache = Path("data/cot")
                print(f"  COT → {len(cot_df):5d} rows | {cot_df['date'].min().strftime('%Y-%m-%d')} → {cot_df['date'].max().strftime('%Y-%m-%d')} | cached in {cot_cache}")
        except Exception as e:
            print(f"  COT → ERROR: {e}")

    print("\n--- Summary ---")
    print(f"{'Series':15s} {'Description':50s} {'Rows':>6s} {'Cache Path'}")
    print("-" * 120)
    for sid, desc, start, end, rows, cache in results:
        print(f"{sid:15s} {desc[:48]:48s}  {rows:>5d}  {cache}")


if __name__ == "__main__":
    main()
