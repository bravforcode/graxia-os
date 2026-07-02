"""Ingest ETH.V and BTC.V from Stooq crypto dump.

Usage:
    python scripts/ingest_crypto_stooq.py --dump-dir "C:/path/to/d_world_txt"
    python scripts/ingest_crypto_stooq.py --dump-dir "C:/path/to/d_world_txt" --symbols ETHUSD BTCUSD
"""

import argparse
import csv
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

CRYPTO_MAP = {
    "ETHUSD": "cryptocurrencies/eth.v.txt",
    "BTCUSD": "cryptocurrencies/btc.v.txt",
}


def parse_stooq(filepath):
    rows = []
    with open(filepath, encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            if len(row) < 8:
                continue
            try:
                dt = datetime.strptime(row[2], "%Y%m%d").replace(tzinfo=UTC)
                rows.append(
                    {
                        "time": dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "open": float(row[4]),
                        "high": float(row[5]),
                        "low": float(row[6]),
                        "close": float(row[7]),
                        "volume": float(row[8]) if len(row) > 8 and row[8] else 0.0,
                    }
                )
            except Exception:
                continue
    df = pd.DataFrame(rows)
    df.drop_duplicates(subset=["time"], keep="first", inplace=True)
    df.sort_values("time", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def main():
    parser = argparse.ArgumentParser(description="Ingest Stooq crypto dump")
    parser.add_argument("--dump-dir", required=True, help="Path to Stooq dump directory")
    parser.add_argument("--symbols", nargs="*", default=["ETHUSD", "BTCUSD"], help="Symbols to ingest")
    args = parser.parse_args()

    dump_dir = Path(args.dump_dir)
    world_dir = dump_dir / "data" / "daily" / "world"
    if not world_dir.exists():
        print(f"Error: {world_dir} not found")
        return 1

    for symbol in args.symbols:
        rel_path = CRYPTO_MAP.get(symbol)
        if not rel_path:
            print(f"{symbol}: unknown crypto symbol")
            continue

        filepath = world_dir / rel_path
        if not filepath.exists():
            print(f"{symbol}: not found at {filepath}")
            continue

        df = parse_stooq(filepath)
        print(f"{symbol}: {len(df)} rows, {df['time'].min()} to {df['time'].max()}")

        out_path = DATA_DIR / f"{symbol}_D1.csv"
        if out_path.exists():
            existing = pd.read_csv(out_path)
            combined = pd.concat([existing, df], ignore_index=True)
            combined.drop_duplicates(subset=["time"], keep="last", inplace=True)
            combined.sort_values("time", inplace=True)
            combined.reset_index(drop=True, inplace=True)
            combined.to_csv(out_path, index=False)
            print(f"  merged: {len(df)} new + {len(existing)} existing = {len(combined)} total")
        else:
            df.to_csv(out_path, index=False)
            print(f"  saved: {len(df)} rows")

    print("Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
