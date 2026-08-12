"""
MT5 XAUUSD Historical Data Exporter
Connects to Pepperstone MT5 and exports H1 (10yr) + M15 (2yr) XAUUSD data to Parquet.
"""

import os
from datetime import date
from pathlib import Path

import MetaTrader5 as mt5
import pandas as pd

ACCOUNT = int(os.environ.get("MT5_LOGIN", "0"))  # P0 fix: no hardcoded account
BASE_DIR = Path(__file__).resolve().parent.parent / "data" / "market_data" / "mt5"


TERMINAL_PATH = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"

def connect_mt5() -> None:
    os.environ["PYTHONIOENCODING"] = "utf-8"
    if not mt5.initialize(path=TERMINAL_PATH, timeout=30000):
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    info = mt5.account_info()
    if info is None:
        # Try login if not already logged in
        if not mt5.login(ACCOUNT):
            raise RuntimeError(f"MT5 login failed for {ACCOUNT}: {mt5.last_error()}")
        info = mt5.account_info()
    print(f"Connected: {info.server} | Account: {info.login} | Balance: {info.balance}")


def download_rates(symbol: str, timeframe: int, start: date, end: date) -> pd.DataFrame:
    """Download rates in yearly chunks to avoid MT5 limits."""
    import datetime as dt
    all_chunks = []
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + dt.timedelta(days=365), end)
        rates = mt5.copy_rates_range(symbol, timeframe, chunk_start, chunk_end)
        if rates is not None and len(rates) > 0:
            all_chunks.append(pd.DataFrame(rates))
            print(f"  {chunk_start} -> {chunk_end}: {len(rates)} bars")
        else:
            print(f"  {chunk_start} -> {chunk_end}: NO DATA ({mt5.last_error()})")
        chunk_start = chunk_end + dt.timedelta(days=1)
    
    if not all_chunks:
        raise RuntimeError(f"No data for {symbol} {timeframe}: {mt5.last_error()}")
    
    df = pd.concat(all_chunks, ignore_index=True).drop_duplicates(subset=["time"])
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.rename(columns={"time": "datetime"}, inplace=True)
    df.sort_values("datetime", inplace=True)
    return df


def print_summary(label: str, df: pd.DataFrame) -> None:
    print(f"\n=== {label} ===")
    print(f"Rows:          {len(df):,}")
    print(f"Date range:    {df['datetime'].min()} -> {df['datetime'].max()}")
    missing = df.isnull().sum().sum()
    print(f"Missing cells: {missing:,}")
    dupes = df["datetime"].duplicated().sum()
    print(f"Duplicate ts:  {dupes:,}")


def main():
    connect_mt5()
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # H1 — 10 years
        print("\nDownloading H1 data (10yr)...")
        h1 = download_rates("XAUUSD", mt5.TIMEFRAME_H1, date(2016, 1, 1), date(2026, 6, 26))
        h1_path = BASE_DIR / "xauusd_h1_10yr.parquet"
        h1.to_parquet(h1_path, index=False)
        print_summary("XAUUSD H1 (10yr)", h1)
        print(f"Saved: {h1_path}")

        # M15 — 2 years
        print("\nDownloading M15 data (2yr)...")
        m15 = download_rates("XAUUSD", mt5.TIMEFRAME_M15, date(2024, 6, 1), date(2026, 6, 26))
        m15_path = BASE_DIR / "xauusd_m15_2yr.parquet"
        m15.to_parquet(m15_path, index=False)
        print_summary("XAUUSD M15 (2yr)", m15)
        print(f"Saved: {m15_path}")

    finally:
        mt5.shutdown()
        print("\nMT5 shutdown.")


if __name__ == "__main__":
    main()
