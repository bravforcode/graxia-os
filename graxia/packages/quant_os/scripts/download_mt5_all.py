"""MT5 Historical Data Downloader — Bulk export M15/H1/H4/D1 for all symbols.

Uses MT5 copy_rates_range (free, from broker server).
M15 depth: ~2 years, H1+: 10+ years.

Usage:
    python scripts/download_mt5_all.py
    python scripts/download_mt5_all.py --timeframes M15 H1
    python scripts/download_mt5_all.py --symbols XAUUSD EURUSD
"""
from __future__ import annotations

import os
import sys
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path

import MetaTrader5 as mt5
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "market"

# Pepperstone demo terminal
TERMINAL_PATH = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"

# Symbols to download — organized by asset class
FOREX_MAJORS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
]
FOREX_CROSSES = [
    "EURGBP", "EURJPY", "EURCHF", "EURAUD", "EURCAD",
    "GBPJPY", "GBPAUD", "GBPCAD", "GBPNZD", "GBPCHF",
    "AUDJPY", "AUDCAD", "AUDCHF", "AUDNZD",
    "CADJPY", "CADCHF", "NZDJPY", "NZDCAD", "NZDCHF", "CHFJPY",
]
FOREX_EXOTICS = [
    "USDCNH", "USDTRY", "USDMXN", "USDZAR", "USDPLN", "USDHUF",
    "USDCZK", "USDINR", "USDKRW", "USDSGD", "USDNOK", "USDSEK", "USDDKK",
]
METALS = [
    "XAUUSD", "XAGUSD", "XPTUSD", "XAUEUR", "XAGEUR",
]
CRYPTO = [
    "BTCUSD", "ETHUSD", "BTCEUR", "ETHEUR",
]
INDICES = [
    "US500", "US30", "NAS100", "US2000",
    "DE40", "UK100", "JP225", "STOXX50E",
]

ALL_SYMBOLS = FOREX_MAJORS + FOREX_CROSSES + FOREX_EXOTICS + METALS + CRYPTO + INDICES

# Timeframe configs: (name, mt5_const, max_years_back)
TIMEFRAMES = {
    "M15": (mt5.TIMEFRAME_M15, 2),
    "H1":  (mt5.TIMEFRAME_H1, 10),
    "H4":  (mt5.TIMEFRAME_H4, 10),
    "D1":  (mt5.TIMEFRAME_D1, 10),
}


def connect() -> None:
    if not mt5.initialize(path=TERMINAL_PATH, timeout=30000):
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    info = mt5.account_info()
    print(f"Connected: {info.server} | Account: {info.login} | Balance: {info.balance}")


def download_rates_chunked(
    symbol: str,
    timeframe: int,
    start: datetime,
    end: datetime,
) -> pd.DataFrame | None:
    """Download rates in yearly chunks to avoid MT5 limits."""
    all_chunks = []
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=365), end)
        rates = mt5.copy_rates_range(symbol, timeframe, chunk_start, chunk_end)
        if rates is not None and len(rates) > 0:
            all_chunks.append(pd.DataFrame(rates))
        chunk_start = chunk_end + timedelta(days=1)
        time.sleep(0.1)  # Rate limit

    if not all_chunks:
        return None

    df = pd.concat(all_chunks, ignore_index=True).drop_duplicates(subset=["time"])
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.rename(columns={
        "time": "datetime", "open": "open", "high": "high",
        "low": "low", "close": "close", "tick_volume": "volume",
    }, inplace=True)
    df = df[["datetime", "open", "high", "low", "close", "volume"]]
    df.sort_values("datetime", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def download_all(symbols: list[str], timeframes: list[str]) -> dict:
    """Download all symbols × timeframes."""
    end_date = datetime.now()
    results = {"success": 0, "failed": 0, "bars": 0, "failed_list": []}

    for tf_name in timeframes:
        tf_const, max_years = TIMEFRAMES[tf_name]
        start_date = end_date - timedelta(days=max_years * 365)
        output_dir = DATA_DIR / "mt5" / tf_name
        output_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n--- {tf_name} ({start_date.date()} -> {end_date.date()}) ---")

        for i, symbol in enumerate(symbols):
            mt5.symbol_select(symbol, True)
            df = download_rates_chunked(symbol, tf_const, start_date, end_date)

            if df is not None and len(df) > 0:
                csv_path = output_dir / f"{symbol}.csv"
                df.to_csv(csv_path, index=False)
                results["success"] += 1
                results["bars"] += len(df)
                pct = (i + 1) / len(symbols) * 100
                print(f"  [{pct:5.1f}%] {symbol:10s} {len(df):7,} bars -> {csv_path.name}")
            else:
                results["failed"] += 1
                results["failed_list"].append(f"{symbol}/{tf_name}")
                pct = (i + 1) / len(symbols) * 100
                print(f"  [{pct:5.1f}%] {symbol:10s} FAILED")

    return results


def main():
    parser = argparse.ArgumentParser(description="MT5 Bulk Historical Data Downloader")
    parser.add_argument("--symbols", nargs="*", default=None, help="Specific symbols (default: all)")
    parser.add_argument("--timeframes", nargs="*", default=["M15", "H1", "H4", "D1"],
                        choices=["M15", "H1", "H4", "D1"])
    parser.add_argument("--category", default="all",
                        choices=["all", "forex", "metals", "crypto", "indices"])
    args = parser.parse_args()

    if args.symbols:
        symbols = args.symbols
    elif args.category == "all":
        symbols = ALL_SYMBOLS
    elif args.category == "forex":
        symbols = FOREX_MAJORS + FOREX_CROSSES + FOREX_EXOTICS
    elif args.category == "metals":
        symbols = METALS
    elif args.category == "crypto":
        symbols = CRYPTO
    elif args.category == "indices":
        symbols = INDICES
    else:
        symbols = ALL_SYMBOLS

    connect()

    try:
        print(f"Downloading {len(symbols)} symbols × {len(args.timeframes)} timeframes")
        results = download_all(symbols, args.timeframes)
    finally:
        mt5.shutdown()
        print("\nMT5 shutdown.")

    print("\n" + "=" * 60)
    print("DOWNLOAD COMPLETE")
    print(f"  Success: {results['success']}")
    print(f"  Failed:  {results['failed']}")
    print(f"  Total bars: {results['bars']:,}")
    if results["failed_list"]:
        print(f"  Failed: {', '.join(results['failed_list'][:30])}")

    # Show directory tree
    print(f"\n  Data saved to: {DATA_DIR / 'mt5'}")
    for tf_dir in sorted((DATA_DIR / 'mt5').iterdir()):
        if tf_dir.is_dir():
            csv_count = len(list(tf_dir.glob('*.csv')))
            print(f"    {tf_dir.name}/  ({csv_count} files)")


if __name__ == "__main__":
    main()
