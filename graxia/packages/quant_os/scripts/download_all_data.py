"""Bulk Data Downloader — Pull ALL market data via yfinance + Polygon.

Downloads:
- 50+ Forex pairs (daily + hourly)
- 100+ Equities (daily + hourly)
- 50+ Crypto (daily + hourly)
- Saves to CSV files for backtesting

Usage:
    python scripts/download_all_data.py
    python scripts/download_all_data.py --type forex
    python scripts/download_all_data.py --type equity --interval daily
"""
from __future__ import annotations

import os
import sys
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "market"


# ---------------------------------------------------------------------------
# Symbol Lists
# ---------------------------------------------------------------------------

FOREX_PAIRS = [
    # Majors
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X", "AUDUSD=X",
    "USDCAD=X", "NZDUSD=X",
    # Crosses
    "EURGBP=X", "EURJPY=X", "EURCHF=X", "EURAUD=X", "EURCAD=X",
    "GBPJPY=X", "GBPAUD=X", "GBPCAD=X", "GBPNZD=X", "GBPCHF=X",
    "AUDJPY=X", "AUDCAD=X", "AUDCHF=X", "AUDNZD=X",
    "CADJPY=X", "CADCHF=X",
    "NZDJPY=X", "NZDCAD=X", "NZDCHF=X",
    "CHFJPY=X",
    # Exotics
    "USDTRY=X", "USDMXN=X", "USDZAR=X", "USDPLN=X", "USDHUF=X",
    "USDCZK=X", "USDCNH=X", "USDINR=X", "USDBRL=X", "USDKRW=X",
    "USDTWD=X", "USDSGD=X", "USDHKD=X", "USDNOK=X", "USDSEK=X",
    "USDDKK=X", "USDTHB=X", "USDPHP=X", "USDMYR=X", "USDIDR=X",
    # Metals
    "XAUUSD=X", "XAGUSD=X", "XPTUSD=X", "XPDUSD=X",
]

EQUITY_SYMBOLS = [
    # Major ETFs
    "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "VEA", "VWO",
    "VGT", "XLK", "XLF", "XLE", "XLP", "XLU", "XLI", "XLV",
    "XLY", "XLC", "XLRE", "XLB", "XLV", "ARKK", "ARKG",
    # FAANG+M
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA",
    # Tech
    "AMD", "INTC", "CRM", "ADBE", "AVGO", "QCOM", "TXN", "NXPI",
    "AMAT", "LRCX", "KLAC", "MRVL", "SNOW", "PLTR", "CRM",
    # Semiconductor
    "TSM", "ASML", "ARM", "SMCI", "MU", "WDC", "STX",
    # Finance
    "JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW",
    "AXP", "USB", "PNC", "TFC", "COF",
    # Healthcare
    "JNJ", "UNH", "PFE", "ABBV", "MRK", "LLY", "TMO", "ABT",
    "DHR", "BMY", "AMGN", "GILD", "MDT", "ISRG", "SYK",
    # Consumer
    "WMT", "PG", "KO", "PEP", "COST", "MCD", "NKE", "SBUX",
    "TGT", "HD", "LOW", "TJX", "ROST",
    # Energy
    "XOM", "CVX", "COP", "EOG", "SLB", "OXY", "MPC", "PSX",
    # Crypto-related
    "COIN", "MSTR", "MARA", "RIOT", "CLSK", "HUT",
    # AI/Cloud
    "PLTR", "AI", "C3AI", "UPST", "SOFI", "HOOD",
    # Travel/Leisure
    "ABNB", "UBER", "LYFT", "DASH", "GRAB",
    # EV
    "RIVN", "LCID", "NIO", "XPEV", "LI",
    # Gaming/Meta
    "RBLX", "DKNG", "CHWY",
]

CRYPTO_SYMBOLS = [
    # Major
    "BTC-USD", "ETH-USD", "BNB-USD", "XRP-USD", "SOL-USD",
    "ADA-USD", "DOGE-USD", "DOT-USD", "AVAX-USD", "LINK-USD",
    # Large Cap
    "MATIC-USD", "UNI-USD", "ATOM-USD", "FIL-USD", "LTC-USD",
    "XLM-USD", "BCH-USD", "EOS-USD", "NEO-USD", "TRX-USD",
    "ETC-USD", "XMR-USD", "DASH-USD", "ZEC-USD", "ALGO-USD",
    # Mid Cap
    "AAVE-USD", "COMP-USD", "SNX-USD", "YFI-USD", "CRV-USD",
    "SUSHI-USD", "1INCH-USD", "MKR-USD", "LDO-USD", "RPL-USD",
    # Layer 1
    "NEAR-USD", "APT-USD", "SUI-USD", "SEI-USD", "TON-USD",
    "HBAR-USD", "VET-USD", "ICP-USD", "FTM-USD", "KAVA-USD",
    # Memes
    "SHIB-USD", "PEPE-USD", "WIF-USD", "BONK-USD", "FLOKI-USD",
]


# ---------------------------------------------------------------------------
# Download Functions
# ---------------------------------------------------------------------------

def download_symbols(
    symbols: list[str],
    interval: str,
    start: str,
    end: str,
    category: str,
) -> dict:
    """Download data for a list of symbols."""
    output_dir = DATA_DIR / category / interval
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {"success": 0, "failed": 0, "bars": 0, "failed_symbols": []}

    for i, symbol in enumerate(symbols):
        ticker_name = symbol.replace("=X", "").replace("-USD", "")
        csv_path = output_dir / f"{ticker_name}.csv"

        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start, end=end, interval=interval)

            if df.empty:
                results["failed"] += 1
                results["failed_symbols"].append(symbol)
                continue

            # Clean and save
            df.index.name = "timestamp"
            df = df[["Open", "High", "Low", "Close", "Volume"]]
            df.columns = ["open", "high", "low", "close", "volume"]
            df.to_csv(csv_path)

            results["success"] += 1
            results["bars"] += len(df)

            progress = (i + 1) / len(symbols) * 100
            print(f"  [{progress:5.1f}%] {ticker_name:10s} {len(df):6d} bars -> {csv_path.name}")

        except Exception as e:
            results["failed"] += 1
            results["failed_symbols"].append(symbol)
            print(f"  [{(i+1)/len(symbols)*100:5.1f}%] {ticker_name:10s} FAILED: {e}")

        # Rate limiting — yfinance is gentle but let's be safe
        if (i + 1) % 10 == 0:
            time.sleep(1)

    return results


def download_all(start: str, end: str):
    """Download ALL market data."""
    print("=" * 60)
    print("BULK DATA DOWNLOAD — yfinance (free)")
    print(f"Period: {start} to {end}")
    print("=" * 60)

    total_results = {"success": 0, "failed": 0, "bars": 0, "failed_symbols": []}

    # --- FOREX ---
    print(f"\n--- FOREX ({len(FOREX_PAIRS)} pairs) ---")
    for interval in ["1d", "1h"]:
        print(f"\n  Interval: {interval}")
        r = download_symbols(FOREX_PAIRS, interval, start, end, f"forex/{interval}")
        for k in ["success", "failed", "bars"]:
            total_results[k] += r[k]
        total_results["failed_symbols"].extend(r["failed_symbols"])

    # --- EQUITY ---
    print(f"\n--- EQUITY ({len(EQUITY_SYMBOLS)} symbols) ---")
    for interval in ["1d", "1h"]:
        print(f"\n  Interval: {interval}")
        r = download_symbols(EQUITY_SYMBOLS, interval, start, end, f"equity/{interval}")
        for k in ["success", "failed", "bars"]:
            total_results[k] += r[k]
        total_results["failed_symbols"].extend(r["failed_symbols"])

    # --- CRYPTO ---
    print(f"\n--- CRYPTO ({len(CRYPTO_SYMBOLS)} symbols) ---")
    for interval in ["1d", "1h"]:
        print(f"\n  Interval: {interval}")
        r = download_symbols(CRYPTO_SYMBOLS, interval, start, end, f"crypto/{interval}")
        for k in ["success", "failed", "bars"]:
            total_results[k] += r[k]
        total_results["failed_symbols"].extend(r["failed_symbols"])

    # --- SUMMARY ---
    print("\n" + "=" * 60)
    print("DOWNLOAD COMPLETE")
    print("=" * 60)
    print(f"  Success:  {total_results['success']} symbol-interval combos")
    print(f"  Failed:   {total_results['failed']}")
    print(f"  Total bars: {total_results['bars']:,}")
    if total_results["failed_symbols"]:
        print(f"  Failed symbols: {', '.join(set(total_results['failed_symbols'])[:20])}")
    print(f"\n  Data saved to: {DATA_DIR}")

    # Print directory tree
    print("\n  Directory structure:")
    for d in sorted(DATA_DIR.rglob("*")):
        if d.is_dir():
            csv_count = len(list(d.glob("*.csv")))
            if csv_count > 0:
                print(f"    {d.relative_to(DATA_DIR)}/  ({csv_count} files)")


def download_category(category: str, interval: str, start: str, end: str):
    """Download a specific category."""
    symbol_map = {
        "forex": FOREX_PAIRS,
        "equity": EQUITY_SYMBOLS,
        "crypto": CRYPTO_SYMBOLS,
    }

    if category not in symbol_map:
        print(f"Unknown category: {category}. Use: forex, equity, crypto")
        return

    symbols = symbol_map[category]
    print(f"Downloading {category} ({len(symbols)} symbols) at {interval} interval...")
    r = download_symbols(symbols, interval, start, end, f"{category}/{interval}")
    print(f"\nDone: {r['success']} success, {r['failed']} failed, {r['bars']:,} bars")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Bulk Market Data Downloader")
    parser.add_argument("--type", type=str, choices=["all", "forex", "equity", "crypto"],
                        default="all", help="Data type to download")
    parser.add_argument("--interval", type=str, default="both",
                        help="Interval: 1d, 1h, or both (default: both)")
    parser.add_argument("--start", type=str, default="2020-01-01",
                        help="Start date (default: 2020-01-01)")
    parser.add_argument("--end", type=str, default=datetime.now().strftime("%Y-%m-%d"),
                        help="End date (default: today)")

    args = parser.parse_args()

    if args.type == "all":
        download_all(args.start, args.end)
    else:
        intervals = ["1d", "1h"] if args.interval == "both" else [args.interval]
        for iv in intervals:
            download_category(args.type, iv, args.start, args.end)


if __name__ == "__main__":
    main()
