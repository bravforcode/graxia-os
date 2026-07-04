"""
REAL SPREAD MEASUREMENT — Continuous spread logging from Pepperstone MT5.

Samples bid/ask for all 8 TSM assets every 60 seconds, computes spread in bps,
and appends to data/spread_log.jsonl. Designed to run for 1+ week.

Usage:
    python scripts/measure_spread.py [--interval 60] [--symbols XAUUSD,EURUSD,...]

Output:
    data/spread_log.jsonl  — one JSON line per sample per symbol
"""

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import MetaTrader5 as mt5

# All 8 TSM assets (SILVER=XAGUSD, OIL=SpotCrude on Pepperstone)
SYMBOLS_DEFAULT = [
    "XAUUSD",
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "BTCUSD",
    "ETHUSD",
    "XAGUSD",
    "SpotCrude",
]

# Display name mapping for reports
DISPLAY_NAMES = {
    "XAGUSD": "SILVER",
    "SpotCrude": "OIL",
}

BASE = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE / "data"
OUTPUT_FILE = OUTPUT_DIR / "spread_log.jsonl"

MT5_PATH = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"
INIT_TIMEOUT_MS = 30000
RETRY_DELAY_SEC = 10
MAX_RETRIES = 5


def init_mt5() -> bool:
    """Initialize MT5 connection with retry."""
    for attempt in range(1, MAX_RETRIES + 1):
        if mt5.initialize(path=MT5_PATH, timeout=INIT_TIMEOUT_MS):
            return True
        err = mt5.last_error()
        print(f"[INIT] Attempt {attempt}/{MAX_RETRIES} failed: {err}")
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY_SEC)
    return False


def ensure_symbols(symbols: list[str]) -> list[str]:
    """Select symbols in MT5 and return those available."""
    available = []
    for sym in symbols:
        if not mt5.symbol_select(sym, True):
            print(f"[WARN] Cannot select {sym}: {mt5.last_error()}")
            continue
        info = mt5.symbol_info(sym)
        if info is None:
            print(f"[WARN] No info for {sym}")
            continue
        available.append(sym)
    return available


def sample_spread(symbol: str) -> dict | None:
    """Get current bid/ask and compute spread metrics."""
    tick = mt5.symbol_info_tick(symbol)
    info = mt5.symbol_info(symbol)
    if tick is None or info is None:
        return None

    bid = float(tick.bid)
    ask = float(tick.ask)
    mid = (bid + ask) / 2.0
    spread_price = ask - bid
    spread_points = round(spread_price / info.point) if info.point > 0 else 0
    spread_bps = (spread_price / mid * 10000) if mid > 0 else 0.0

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "symbol": symbol,
        "display_name": DISPLAY_NAMES.get(symbol, symbol),
        "bid": round(bid, info.digits),
        "ask": round(ask, info.digits),
        "mid": round(mid, info.digits),
        "spread_bps": round(spread_bps, 2),
        "spread_points": spread_points,
        "spread_price": round(spread_price, info.digits),
        "tick_time": int(tick.time),
        "tick_time_msc": int(tick.time_msc),
    }


def write_sample(sample: dict) -> None:
    """Append one sample as a JSON line."""
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(sample) + "\n")


def run_loop(symbols: list[str], interval: float) -> None:
    """Main sampling loop. Ctrl+C to stop."""
    print(f"[START] Measuring spreads for {symbols}")
    print(f"[START] Interval={interval}s  Output={OUTPUT_FILE}")
    print("[START] Press Ctrl+C to stop\n")

    total_samples = 0
    errors = 0
    start_time = time.time()

    try:
        while True:
            batch_time = datetime.now(UTC).isoformat()
            for sym in symbols:
                sample = sample_spread(sym)
                if sample is None:
                    errors += 1
                    print(f"[ERR] {sym}: tick/info returned None at {batch_time}")
                    continue
                write_sample(sample)
                total_samples += 1

            elapsed = int(time.time() - start_time)
            if total_samples % 50 == 0:
                print(f"  [{elapsed}s] samples={total_samples} errors={errors}")

            time.sleep(interval)

    except KeyboardInterrupt:
        elapsed = int(time.time() - start_time)
        print(f"\n[STOP] Interrupted after {elapsed}s")
        print(f"[STOP] Total samples: {total_samples}, errors: {errors}")
        print(f"[STOP] Output: {OUTPUT_FILE}")


def main():
    parser = argparse.ArgumentParser(description="Real spread measurement from Pepperstone MT5")
    parser.add_argument("--interval", type=float, default=60, help="Seconds between samples (default: 60)")
    parser.add_argument("--symbols", type=str, default=",".join(SYMBOLS_DEFAULT), help="Comma-separated symbols")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("[INIT] Connecting to MT5...")
    if not init_mt5():
        print("[FATAL] Cannot connect to MT5 after retries. Exiting.")
        sys.exit(1)

    print("[INIT] MT5 connected. Selecting symbols...")
    available = ensure_symbols(symbols)
    if not available:
        print("[FATAL] No symbols available. Exiting.")
        mt5.shutdown()
        sys.exit(1)

    print(f"[INIT] Available symbols: {available}")

    try:
        run_loop(available, args.interval)
    finally:
        mt5.shutdown()
        print("[INIT] MT5 shutdown.")


if __name__ == "__main__":
    main()
