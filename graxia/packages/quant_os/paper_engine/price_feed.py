"""
Price feed — async, multi-source, DuckDB-cached.
Source order: 1) local CSV 2) DuckDB 3) yfinance (live).
"""

from __future__ import annotations

import csv
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "data"
CACHE_DB = DATA_DIR / "market_data.duckdb"

# ── Yahoo Finance symbol map (quant_os symbol → yfinance ticker) ─────
YF_SYMBOL_MAP: dict[str, str] = {
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "USDCAD=X",
    "USDCHF": "USDCHF=X",
    "NZDUSD": "NZDUSD=X",
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "NAS100": "^IXIC",
    "US30": "^DJI",
    "SPX500": "^GSPC",
    "OIL": "CL=F",
    "DXY": "DX-Y.NYB",
    "VIX": "^VIX",
}

# ── Timeframe mapping ──────────────────────────────────────────────
YF_INTERVAL_MAP: dict[str, str] = {
    "M1": "1m",
    "M5": "5m",
    "M15": "15m",
    "M30": "30m",
    "H1": "60m",
    "H4": "1h",  # will resample
    "D1": "1d",
    "W1": "1wk",
    "MN1": "1mo",
}

TF_DAYS_LOOKBACK: dict[str, int] = {
    "M1": 7,
    "M5": 30,
    "M15": 60,
    "M30": 60,
    "H1": 365,
    "H4": 730,
    "D1": 1825,
    "W1": 3650,
    "MN1": 7300,
}

# ── CSV column mapping ─────────────────────────────────────────────
CSV_COLUMN_ALIASES: dict[str, str] = {
    "time": "time",
    "timestamp": "time",
    "date": "time",
    "datetime": "time",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "adj close": "close",
    "adjusted close": "close",
    "volume": "volume",
    "tick_volume": "volume",
    "vol": "volume",
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename CSV columns to canonical: time, open, high, low, close, volume."""
    rename = {}
    for col in df.columns:
        lower = col.strip().lower()
        if lower in CSV_COLUMN_ALIASES:
            rename[col] = CSV_COLUMN_ALIASES[lower]
    df = df.rename(columns=rename)
    # ensure required columns
    for req in ["time", "open", "high", "low", "close"]:
        if req not in df.columns:
            raise ValueError(f"Missing required column '{req}' in CSV. Have: {list(df.columns)}")
    if "volume" not in df.columns:
        df["volume"] = 0
    return df


def _parse_time(df: pd.DataFrame) -> pd.DataFrame:
    """Parse time column to datetime, sort, set as index."""
    if "time" in df.columns:
        # Try various formats
        if df["time"].dtype == "int64" or df["time"].dtype == "float64":
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        else:
            df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time").sort_index()
    return df


def _resample_h4(df: pd.DataFrame) -> pd.DataFrame:
    """Resample 1h → 4h if needed."""
    if len(df) < 4:
        return df
    ohlc = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    return df.resample("4h").agg(ohlc).dropna()


def find_csv(symbol: str, timeframe: str) -> Path | None:
    """Find local CSV file for symbol+timeframe."""
    patterns = [
        f"{symbol}_{timeframe}.csv",
        f"{symbol}_D1.csv" if timeframe == "D1" else None,
    ]
    for pattern in patterns:
        if pattern is None:
            continue
        for root, _dirs, files in os.walk(DATA_DIR):
            for f in files:
                if f.lower() == pattern.lower():
                    return Path(root) / f
    return None


def load_csv(symbol: str, timeframe: str) -> pd.DataFrame | None:
    """Load from local CSV, normalised."""
    path = find_csv(symbol, timeframe)
    if path is None:
        return None
    try:
        # Auto-detect delimiter
        with open(path, newline="") as f:
            sample = f.read(8192)
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        df = pd.read_csv(path, delimiter=dialect.delimiter)
        df = _normalize_columns(df)
        df = _parse_time(df)
        if timeframe == "H4":
            df = _resample_h4(df)
        return df
    except Exception:
        return None


def load_duckdb(symbol: str, timeframe: str) -> pd.DataFrame | None:
    """Try loading from DuckDB cache."""
    if not CACHE_DB.exists():
        return None
    try:
        import duckdb

        con = duckdb.connect(str(CACHE_DB))
        # Try common table names
        for table in [symbol, f"{symbol}_{timeframe}", "bars", "market_data"]:
            try:
                q = f"SELECT * FROM \"{table}\" WHERE symbol = '{symbol}' ORDER BY time"
                df = con.execute(q).fetchdf()
                if len(df) > 0:
                    return df
            except Exception:
                continue
        con.close()
    except Exception:
        pass
    return None


def fetch_yfinance(symbol: str, timeframe: str) -> pd.DataFrame | None:
    """Fetch from yfinance (live or historical)."""
    yf_symbol = YF_SYMBOL_MAP.get(symbol)
    if yf_symbol is None:
        return None

    interval = YF_INTERVAL_MAP.get(timeframe, "1d")
    lookback_days = TF_DAYS_LOOKBACK.get(timeframe, 365)
    period = f"{lookback_days}d"

    try:
        import yfinance as yf

        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty:
            return None

        df = df.reset_index()
        # yfinance uses 'Datetime' or 'Date' column
        if "Datetime" in df.columns:
            df = df.rename(columns={"Datetime": "time"})
        elif "Date" in df.columns:
            df = df.rename(columns={"Date": "time"})
        df = df.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })
        df = _parse_time(df)
        if timeframe == "H4":
            df = _resample_h4(df)

        # cache to DuckDB for下次
        _cache_to_duckdb(symbol, timeframe, df)
        return df
    except Exception:
        return None


def _cache_to_duckdb(symbol: str, timeframe: str, df: pd.DataFrame) -> None:
    """Cache fetched data to local DuckDB for faster re-runs."""
    try:
        import duckdb

        con = duckdb.connect(str(CACHE_DB))
        table = f"{symbol}_{timeframe}"
        con.execute(f"CREATE TABLE IF NOT EXISTS \"{table}\" AS SELECT * FROM df WHERE 1=0")
        # insert-or-ignore by index
        con.execute(f"INSERT OR REPLACE INTO \"{table}\" SELECT * FROM df")
        con.close()
    except Exception:
        pass


def load_ohlcv(symbol: str, timeframe: str) -> pd.DataFrame | None:
    """Load OHLCV data from best available source.

    Priority: CSV cache > DuckDB > yfinance fetch.
    """
    df = load_csv(symbol, timeframe)
    if df is not None and len(df) > 100:
        return df

    df = load_duckdb(symbol, timeframe)
    if df is not None and len(df) > 100:
        return df

    return fetch_yfinance(symbol, timeframe)


def get_latest_price(symbol: str) -> float | None:
    """Get latest price from yfinance."""
    try:
        import yfinance as yf

        yf_sym = YF_SYMBOL_MAP.get(symbol)
        if not yf_sym:
            return None
        ticker = yf.Ticker(yf_sym)
        df = ticker.history(period="1d", interval="1m", progress=False)
        if not df.empty:
            return float(df["Close"].iloc[-1])
        return None
    except Exception:
        return None


def get_available_symbols() -> list[str]:
    """List all symbols that have data available."""
    available = set(YF_SYMBOL_MAP.keys())

    # Check CSV files
    for root, _dirs, files in os.walk(DATA_DIR):
        for f in files:
            if f.endswith(".csv"):
                parts = f.split("_")
                if parts and parts[0] in YF_SYMBOL_MAP:
                    available.add(parts[0])

    return sorted(available)
