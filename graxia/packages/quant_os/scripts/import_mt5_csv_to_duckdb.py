"""Import MT5-downloaded CSV data into data/market_data.duckdb ohlcv table.

Reads CSVs written by scripts/download_mt5_all.py (data/market/mt5/{TF}/{SYMBOL}.csv)
and upserts them into the flat ``ohlcv`` table used by backtest/data_loader.py
(timeframe convention: '15m', '1h', '4h', '1d').

Usage:
    python scripts/import_mt5_csv_to_duckdb.py --symbols BTCUSD EURUSD --timeframes M15 H1
    python scripts/import_mt5_csv_to_duckdb.py --all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MT5_DIR = PROJECT_ROOT / "data" / "market" / "mt5"
DB_PATH = PROJECT_ROOT / "data" / "market_data.duckdb"

TF_MAP = {"M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d"}


def import_csv(symbol: str, tf_name: str, con: duckdb.DuckDBPyConnection) -> int:
    csv_path = MT5_DIR / tf_name / f"{symbol}.csv"
    if not csv_path.exists():
        print(f"  SKIP {symbol}/{tf_name} (no file: {csv_path.name})")
        return 0

    df = pd.read_csv(csv_path)
    if "datetime" not in df.columns:
        print(f"  SKIP {symbol}/{tf_name} (no 'datetime' column)")
        return 0

    df["time"] = pd.to_datetime(df["datetime"], utc=True)
    df["symbol"] = symbol
    df["timeframe"] = TF_MAP[tf_name]
    df["tick_count"] = 0
    cols = ["time", "symbol", "timeframe", "open", "high", "low", "close", "volume", "tick_count"]
    df = df[[c for c in cols if c in df.columns]]

    tf = TF_MAP[tf_name]
    con.execute("DELETE FROM ohlcv WHERE symbol = ? AND timeframe = ?", [symbol, tf])
    con.execute("INSERT INTO ohlcv SELECT * FROM df")
    return len(df)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import MT5 CSVs into market_data.duckdb")
    parser.add_argument("--symbols", nargs="+", default=None, help="Symbols to import (default: all found)")
    parser.add_argument("--timeframes", nargs="+", default=["M15", "H1"], choices=list(TF_MAP.keys()))
    parser.add_argument("--all", action="store_true", help="Import all symbols found in data/market/mt5")
    args = parser.parse_args()

    if args.all:
        symbols = sorted({p.name for tf in TF_MAP for p in (MT5_DIR / tf).glob("*.csv")} if MT5_DIR.exists() else [])
    else:
        symbols = args.symbols or ["BTCUSD", "EURUSD"]

    if not MT5_DIR.exists():
        print(f"ERROR: {MT5_DIR} does not exist. Run download_mt5_all.py first.")
        sys.exit(1)

    con = duckdb.connect(str(DB_PATH))
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

    total = 0
    for symbol in symbols:
        for tf_name in args.timeframes:
            n = import_csv(symbol, tf_name, con)
            if n:
                print(f"  {symbol}/{tf_name}: {n:,} bars -> duckdb")
                total += n

    con.close()
    print(f"\nIMPORT COMPLETE: {total:,} bars total into {DB_PATH.name}")


if __name__ == "__main__":
    main()
