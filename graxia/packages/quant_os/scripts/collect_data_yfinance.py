"""
Data Collection Script — yfinance H1 (6 months) + D1 (2 years)

For all 15 instruments in the Quant OS system.
MT5 terminal required for M1 data — not available without running MT5.

Usage:
    python scripts/collect_data_yfinance.py
"""
import os
import sys
import yfinance as yf
import pandas as pd
from datetime import datetime
from pathlib import Path

# ── Instrument Mapping ──────────────────────────────────────────────
# yfinance ticker symbols for each instrument
INSTRUMENTS = {
    "AUDUSD": {"yf": "AUDUSD=X", "type": "forex"},
    "BTCUSD": {"yf": "BTC-USD", "type": "crypto"},
    "ETHUSD": {"yf": "ETH-USD", "type": "crypto"},
    "EURUSD": {"yf": "EURUSD=X", "type": "forex"},
    "GBPUSD": {"yf": "GBPUSD=X", "type": "forex"},
    "NAS100": {"yf": "^IXIC", "type": "index"},
    "NZDUSD": {"yf": "NZDUSD=X", "type": "forex"},
    "US30": {"yf": "^DJI", "type": "index"},
    "USDCAD": {"yf": "USDCAD=X", "type": "forex"},
    "USDCHF": {"yf": "USDCHF=X", "type": "forex"},
    "USDJPY": {"yf": "JPY=X", "type": "forex"},
    "XAGUSD": {"yf": "SI=F", "type": "metal"},
    "XAUUSD": {"yf": "GC=F", "type": "metal"},
    "XPDUSD": {"yf": None, "type": "metal"},  # No yfinance ticker
    "XPTUSD": {"yf": None, "type": "metal"},  # No yfinance ticker
}

DATA_DIR = Path(__file__).parent.parent / "data"


def download_h1_data(symbol: str, ticker_sym: str) -> pd.DataFrame:
    """Download 6 months of H1 data."""
    ticker = yf.Ticker(ticker_sym)
    df = ticker.history(period="6mo", interval="1h")
    if df.empty:
        print(f"  WARNING: No H1 data for {symbol}")
        return pd.DataFrame()
    
    # Standardize columns
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["open", "high", "low", "close", "volume"]
    df.index.name = "timestamp"
    
    print(f"  H1: {len(df)} bars, {df.index[0]} to {df.index[-1]}")
    return df


def download_d1_data(symbol: str, ticker_sym: str) -> pd.DataFrame:
    """Download 2 years of D1 data."""
    ticker = yf.Ticker(ticker_sym)
    df = ticker.history(period="2y", interval="1d")
    if df.empty:
        print(f"  WARNING: No D1 data for {symbol}")
        return pd.DataFrame()
    
    # Standardize columns
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["open", "high", "low", "close", "volume"]
    df.index.name = "timestamp"
    
    print(f"  D1: {len(df)} bars, {df.index[0]} to {df.index[-1]}")
    return df


def save_csv(df: pd.DataFrame, filepath: Path):
    """Save DataFrame to CSV."""
    if df.empty:
        return
    
    # Convert timestamp to string for CSV
    df.index = df.index.strftime("%Y-%m-%d %H:%M:%S")
    df.to_csv(filepath)
    print(f"  Saved: {filepath.name} ({len(df)} rows)")


def main():
    print("=" * 60)
    print("Quant OS Data Collection (yfinance)")
    print("=" * 60)
    print(f"Data directory: {DATA_DIR}")
    print(f"Instruments: {len(INSTRUMENTS)}")
    print()
    
    results = {"success": 0, "failed": 0, "skipped": 0}
    
    for symbol, info in INSTRUMENTS.items():
        print(f"\n--- {symbol} ({info['type']}) ---")
        
        if info["yf"] is None:
            print(f"  SKIPPED: No yfinance ticker available")
            results["skipped"] += 1
            continue
        
        try:
            # Download H1
            h1_df = download_h1_data(symbol, info["yf"])
            if not h1_df.empty:
                save_csv(h1_df, DATA_DIR / f"{symbol}_H1.csv")
            
            # Download D1
            d1_df = download_d1_data(symbol, info["yf"])
            if not d1_df.empty:
                save_csv(d1_df, DATA_DIR / f"{symbol}_D1.csv")
            
            results["success"] += 1
            
        except Exception as e:
            print(f"  ERROR: {e}")
            results["failed"] += 1
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Success: {results['success']}")
    print(f"Failed: {results['failed']}")
    print(f"Skipped: {results['skipped']}")
    
    # Verify existing M1 data
    print("\n--- Existing M1 Data ---")
    for symbol in INSTRUMENTS:
        m1_file = DATA_DIR / f"{symbol}_M1.csv"
        if m1_file.exists():
            lines = sum(1 for _ in open(m1_file)) - 1  # Subtract header
            print(f"  {symbol}_M1.csv: {lines} bars")
        else:
            print(f"  {symbol}_M1.csv: NOT FOUND")
    
    print("\nNOTE: M1 data requires MT5 terminal running.")
    print("Current M1 files have ~5000 bars (~3-5 days).")
    print("For 6+ months of M1 data, start MT5 and run:")
    print("  python scripts/collect_data_mt5.py")


if __name__ == "__main__":
    main()
