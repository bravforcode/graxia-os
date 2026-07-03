"""
Bootstrap Historical OHLCV Data from MT5 → DuckDB

Pulls 10,000 1H bars from Pepperstone-Demo server for XAUUSD and EURUSD.
This unlocks Triple-Barrier labeling, SHAP purging, and model training.

Usage: python scripts/bootstrap_history.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import MetaTrader5 as mt5
import duckdb
from core.config import get_settings


def bootstrap_history():
    settings = get_settings()

    # 1. Connect to MT5
    ok = mt5.initialize(
        login=settings.MT5_LOGIN,
        password=settings.MT5_PASSWORD,
        server=settings.MT5_SERVER,
    )
    if not ok:
        print(f"MT5 init failed: {mt5.last_error()}")
        return False

    info = mt5.account_info()
    print(f"Connected: {info.server} | Balance: {info.balance}")

    db_path = settings.DUCKDB_PATH or "data/market_data.duckdb"
    con = duckdb.connect(db_path)

    # Create ohlcv table if not exists
    con.execute("""
        CREATE TABLE IF NOT EXISTS ohlcv (
            time TIMESTAMP,
            symbol VARCHAR,
            timeframe VARCHAR,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume DOUBLE,
            tick_count INTEGER DEFAULT 0
        )
    """)

    symbols = ["XAUUSD", "EURUSD"]
    total_bars = 0

    for symbol in symbols:
        print(f"\nFetching {symbol} 1H history...")

        # Pull 10,000 bars from position 0 (most recent)
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 10000)
        if rates is None or len(rates) == 0:
            print(f"  No data for {symbol}: {mt5.last_error()}")
            continue

        # Convert to DataFrame
        import pandas as pd
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df["symbol"] = symbol
        df["timeframe"] = "1h"
        df["tick_count"] = 0

        # Rename columns to match schema
        df = df.rename(columns={"real_volume": "volume"})

        # Select only matching columns
        cols = ["time", "symbol", "timeframe", "open", "high", "low", "close", "volume", "tick_count"]
        df = df[[c for c in cols if c in df.columns]]

        # Insert into DuckDB
        con.execute("DELETE FROM ohlcv WHERE symbol = ? AND timeframe = '1h'", [symbol])
        con.execute("INSERT INTO ohlcv SELECT * FROM df")

        count = con.execute(
            "SELECT COUNT(*) FROM ohlcv WHERE symbol = ? AND timeframe = '1h'", [symbol]
        ).fetchone()[0]
        total_bars += count
        print(f"  {symbol}: {count} 1H bars loaded")
        print(f"  Range: {df['time'].iloc[0]} to {df['time'].iloc[-1]}")

    con.close()
    mt5.shutdown()

    print(f"\n{'='*50}")
    print(f"BOOTSTRAP COMPLETE: {total_bars} total 1H bars")
    print(f"Database: {db_path}")
    print(f"{'='*50}")

    # Verify
    con = duckdb.connect(db_path, read_only=True)
    for symbol in symbols:
        count = con.execute(
            "SELECT COUNT(*) FROM ohlcv WHERE symbol = ? AND timeframe = '1h'", [symbol]
        ).fetchone()[0]
        if count > 0:
            first = con.execute(
                "SELECT MIN(time) FROM ohlcv WHERE symbol = ? AND timeframe = '1h'", [symbol]
            ).fetchone()[0]
            last = con.execute(
                "SELECT MAX(time) FROM ohlcv WHERE symbol = ? AND timeframe = '1h'", [symbol]
            ).fetchone()[0]
            print(f"{symbol}: {count} bars | {first} → {last}")
    con.close()

    return True


if __name__ == "__main__":
    success = bootstrap_history()
    sys.exit(0 if success else 1)
