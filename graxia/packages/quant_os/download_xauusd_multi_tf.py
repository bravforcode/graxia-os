"""
download_xauusd_multi_tf.py — Multi-timeframe XAUUSD downloader for gold_bot backtesting.

Downloads D1, H1, and M15 OHLCV for XAUUSD so all 13 gold_bot strategies —
including session-based ones (london_breakout, opening_range) that need
intraday bars — can finally be backtested on the correct instrument.

FAIL-LOUD POLICY: Every download path either succeeds with real data,
or raises immediately. Nothing silently falls back to synthetic data.

Yahoo Finance intraday history limits (2026):
  1m: 7 days, 5m/15m: 60 days, 1h: 730 days, 1d: full history

Usage:
    python download_xauusd_multi_tf.py
    python download_xauusd_multi_tf.py --allow-yahoo-fallback
    python download_xauusd_multi_tf.py --symbol-mt5 XAUUSD.a
"""

import argparse
import os
from typing import NoReturn
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
YAHOO_INTRADAY_LIMITS_DAYS = {"1m": 7, "5m": 60, "15m": 60, "1h": 730}
MT5_REQUEST_BARS = {"H1": 30000, "M15": 100000}
MT5_TIMEFRAME_ATTR = {"H1": "TIMEFRAME_H1", "M15": "TIMEFRAME_M15", "D1": "TIMEFRAME_D1"}


def _fail(title: str, detail: str, fix_lines: list) -> NoReturn:
    fix_block = "\n".join(f"  {i + 1}. {line}" for i, line in enumerate(fix_lines))
    raise RuntimeError(
        f"\n{'=' * 60}\n{title}\n{'=' * 60}\n{detail}\n\nFIX:\n{fix_block}\n{'=' * 60}"
    )


def download_yahoo(symbol_yahoo: str, interval: str, period: str) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError:
        _fail("MISSING DEPENDENCY: yfinance", "Not installed.", ["pip install yfinance"])

    ticker = yf.Ticker(symbol_yahoo)
    df = ticker.history(period=period, interval=interval)

    if df is None or df.empty:
        _fail("YAHOO DOWNLOAD FAILED",
              f"No data for {symbol_yahoo} interval={interval} period={period}.",
              ["Check internet", f"Verify {symbol_yahoo} is valid", "Use MT5 for intraday"])

    df = df.rename(columns=str.lower)
    df.index = pd.to_datetime(df.index, utc=True)
    df.index.name = "time"
    return df[["open", "high", "low", "close", "volume"]]


def download_mt5(symbol_mt5: str, timeframe_name: str, bars: int) -> pd.DataFrame:
    try:
        import MetaTrader5 as mt5
    except ImportError:
        _fail("MISSING DEPENDENCY: MetaTrader5", "Not installed.", ["pip install MetaTrader5"])

    if not mt5.initialize():
        _fail("MT5 INITIALIZE FAILED",
              f"mt5.initialize() failed: {mt5.last_error()}",
              ["Open MT5 terminal and login", "Or use --allow-yahoo-fallback"])

    try:
        tf_const = getattr(mt5, MT5_TIMEFRAME_ATTR[timeframe_name])
        rates = mt5.copy_rates_from_pos(symbol_mt5, tf_const, 0, bars)

        if rates is None or len(rates) == 0:
            all_symbols = mt5.symbols_get() or []
            similar = [s.name for s in all_symbols if "XAU" in s.name.upper()]
            _fail("MT5 RETURNED NO DATA",
                  f"No data for symbol='{symbol_mt5}' timeframe={timeframe_name}",
                  [f"Similar symbols: {similar}", "Check Market Watch", "Pass --symbol-mt5"])

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.set_index("time").rename(columns={"tick_volume": "volume"})
        return df[["open", "high", "low", "close", "volume"]]
    finally:
        mt5.shutdown()


def summarize(df: pd.DataFrame, label: str) -> dict:
    return {
        "label": label, "bars": len(df),
        "start": df.index.min(), "end": df.index.max(),
        "trading_days": df.index.normalize().nunique(),
    }


def print_summary_table(summaries: list) -> None:
    print(f"\n{'=' * 70}")
    print("  XAUUSD MULTI-TIMEFRAME DOWNLOAD SUMMARY")
    print(f"{'=' * 70}")
    for s in summaries:
        print(f"\n  {s['label']}")
        print(f"    Bars:          {s['bars']}")
        print(f"    Date range:    {s['start']}  to  {s['end']}")
        print(f"    Trading days:  {s['trading_days']}")
        if s["trading_days"] < 100:
            print(f"    WARNING: only {s['trading_days']} trading days. "
                  f"Session-based strategies need ~100+ days.")
    print(f"\n{'=' * 70}\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol-yahoo", default="GC=F")
    parser.add_argument("--symbol-mt5", default="XAUUSD")
    parser.add_argument("--allow-yahoo-fallback", action="store_true")
    args = parser.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    summaries = []

    print("Downloading D1 (Yahoo, full history)...")
    d1 = download_yahoo(args.symbol_yahoo, interval="1d", period="max")
    d1.to_csv(os.path.join(DATA_DIR, "XAUUSD_D1.csv"))
    summaries.append(summarize(d1, "D1 (Yahoo, full history)"))
    print(f"  -> {len(d1)} bars saved")

    for tf_name, yahoo_interval in [("H1", "1h"), ("M15", "15m")]:
        print(f"\nDownloading {tf_name} (trying MT5 first)...")
        try:
            df = download_mt5(args.symbol_mt5, tf_name, MT5_REQUEST_BARS[tf_name])
            print(f"  -> Source: MT5, {len(df)} bars")
            summaries.append(summarize(df, f"{tf_name} (MT5)"))
        except RuntimeError:
            if not args.allow_yahoo_fallback:
                raise
            limit_days = YAHOO_INTRADAY_LIMITS_DAYS.get(yahoo_interval, "?")
            print(f"  WARNING: MT5 unavailable — falling back to Yahoo (~{limit_days} days only)")
            df = download_yahoo(args.symbol_yahoo, interval=yahoo_interval, period="60d")
            summaries.append(summarize(df, f"{tf_name} (Yahoo fallback, LIMITED)"))

        df.to_csv(os.path.join(DATA_DIR, f"XAUUSD_{tf_name}.csv"))
        print(f"  -> saved to data/XAUUSD_{tf_name}.csv")

    print_summary_table(summaries)


if __name__ == "__main__":
    main()
