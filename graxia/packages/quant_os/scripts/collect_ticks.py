"""
TICK DATA COLLECTOR — Continuous market data recording.

Records bid/ask/last/spread for multiple symbols at configurable interval.
Output: CSV files for training pipeline.

Usage:
    python scripts/collect_ticks.py [--interval 1.0] [--duration 3600] [--symbols XAUUSD,EURUSD,GBPUSD]
"""
import argparse
import csv
import os
import sys
import time
from datetime import datetime, UTC

import MetaTrader5 as mt5

SYMBOLS_DEFAULT = ["XAUUSD", "EURUSD", "GBPUSD"]
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts", "tick_data")


def init_mt5():
    res = mt5.initialize(timeout=30000)
    if not res:
        print(f"FAIL_CONNECT: {mt5.last_error()}")
        sys.exit(1)
    for sym in SYMBOLS_DEFAULT:
        mt5.symbol_select(sym, True)
    return res


def collect_tick(symbol: str) -> dict:
    tick = mt5.symbol_info_tick(symbol)
    info = mt5.symbol_info(symbol)
    if not tick or not info:
        return None
    spread = round((tick.ask - tick.bid) / info.point, 1) if info.point else 0
    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "time_msc": tick.time_msc,
        "symbol": symbol,
        "bid": tick.bid,
        "ask": tick.ask,
        "last": tick.last,
        "spread_points": spread,
        "spread_price": round(tick.ask - tick.bid, 5),
        "volume": tick.volume,
        "flags": tick.flags,
    }


def main():
    parser = argparse.ArgumentParser(description="Tick data collector")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between samples")
    parser.add_argument("--duration", type=int, default=3600, help="Total seconds to collect")
    parser.add_argument("--symbols", type=str, default=",".join(SYMBOLS_DEFAULT), help="Comma-separated symbols")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")]
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # One CSV per symbol
    writers = {}
    files = {}
    for sym in symbols:
        filepath = os.path.join(OUTPUT_DIR, f"{sym}_ticks_{datetime.now(UTC).strftime('%Y%m%d')}.csv")
        is_new = not os.path.exists(filepath)
        f = open(filepath, "a", newline="")
        writer = csv.DictWriter(f, fieldnames=[
            "timestamp_utc", "time_msc", "symbol", "bid", "ask", "last",
            "spread_points", "spread_price", "volume", "flags"
        ])
        if is_new:
            writer.writeheader()
        writers[sym] = writer
        files[sym] = f

    init_mt5()

    print(f"Collecting ticks: symbols={symbols} interval={args.interval}s duration={args.duration}s")
    print(f"Output: {OUTPUT_DIR}")

    start = time.time()
    count = 0
    try:
        while time.time() - start < args.duration:
            for sym in symbols:
                tick = collect_tick(sym)
                if tick:
                    writers[sym].writerow(tick)
                    files[sym].flush()
                    count += 1
            elapsed = int(time.time() - start)
            remaining = args.duration - elapsed
            if count % 50 == 0:
                print(f"  [{elapsed}s/{args.duration}s] ticks={count} remaining={remaining}s")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        for f in files.values():
            f.close()
        mt5.shutdown()
        print(f"Done. Total ticks: {count}. Files: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
