"""
Continuous Spread Measurement — 7+ Day Session-Separated Baseline
=================================================================
Records real MT5 spreads every 5 minutes for the 8-asset universe.
Separates by session (Asian/London/NY). Outputs summary statistics.

Usage:
    python scripts/measure_spread_continuous.py --duration-days 7
    python scripts/measure_spread_continuous.py --duration-days 14 --symbols XAUUSD EURUSD

Output:
    data/spread_measurements/YYYY-MM-DD.json  (one file per day)
    data/spread_measurements/summary.json     (aggregated stats)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "spread_measurements"

DEFAULT_SYMBOLS = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "US30", "BTCUSD"]

# Session boundaries (UTC hours)
SESSIONS = {
    "asian": (0, 7),
    "london": (7, 12),
    "ny": (12, 21),
    "off_hours": (21, 24),  # After NY close
}


def get_session(hour_utc: int) -> str:
    """Classify UTC hour into trading session."""
    for name, (start, end) in SESSIONS.items():
        if start <= hour_utc < end:
            return name
    return "asian"


def measure_once(symbols: list[str]) -> list[dict]:
    """Take one measurement snapshot for all symbols."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("ERROR: MetaTrader5 not installed. Run: pip install MetaTrader5")
        sys.exit(1)

    if not mt5.initialize():
        print(f"ERROR: MT5 initialize failed: {mt5.last_error()}")
        return []

    now = datetime.now(timezone.utc)
    measurements = []

    for sym_name in symbols:
        try:
            tick = mt5.symbol_info_tick(sym_name)
            sym_info = mt5.symbol_info(sym_name)
            if tick is None or sym_info is None:
                continue

            bid = tick.bid
            ask = tick.ask
            if bid <= 0 or ask <= 0:
                continue

            spread_points = ask - bid
            mid = (ask + bid) / 2.0
            spread_bps = (spread_points / mid) * 10000 if mid > 0 else 0

            measurements.append({
                "symbol": sym_name,
                "timestamp_utc": now.isoformat(),
                "bid": bid,
                "ask": ask,
                "spread_points": round(spread_points, 6),
                "spread_bps": round(spread_bps, 4),
                "session": get_session(now.hour),
                "point": sym_info.point,
                "digits": sym_info.digits,
            })
        except Exception as e:
            print(f"  WARNING: {sym_name} measurement failed: {e}")
            continue

    mt5.shutdown()
    return measurements


def save_day(day_data: list[dict], date_str: str) -> Path:
    """Save measurements for one day as JSON."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{date_str}.json"

    # Merge with existing if file exists
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        existing.extend(day_data)
        day_data = existing

    path.write_text(json.dumps(day_data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def compute_summary(all_measurements: list[dict]) -> dict:
    """Compute per-symbol, per-session summary statistics."""
    from collections import defaultdict
    import statistics

    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for m in all_measurements:
        key = (m["symbol"], m["session"])
        grouped[key].append(m["spread_bps"])

    summary = {}
    for (symbol, session), values in sorted(grouped.items()):
        if not values:
            continue
        values_sorted = sorted(values)
        n = len(values_sorted)
        key = f"{symbol}_{session}"
        summary[key] = {
            "symbol": symbol,
            "session": session,
            "n_samples": n,
            "min_bps": round(values_sorted[0], 4),
            "max_bps": round(values_sorted[-1], 4),
            "mean_bps": round(statistics.mean(values), 4),
            "median_bps": round(statistics.median(values), 4),
            "p95_bps": round(values_sorted[int(n * 0.95)] if n >= 20 else values_sorted[-1], 4),
            "std_bps": round(statistics.stdev(values), 4) if n >= 2 else 0,
        }

    # Also compute overall per-symbol summary
    symbol_overall: dict[str, list[float]] = defaultdict(list)
    for m in all_measurements:
        symbol_overall[m["symbol"]].append(m["spread_bps"])

    for symbol, values in sorted(symbol_overall.items()):
        if not values:
            continue
        values_sorted = sorted(values)
        n = len(values_sorted)
        key = f"{symbol}_ALL"
        summary[key] = {
            "symbol": symbol,
            "session": "ALL",
            "n_samples": n,
            "min_bps": round(values_sorted[0], 4),
            "max_bps": round(values_sorted[-1], 4),
            "mean_bps": round(statistics.mean(values), 4),
            "median_bps": round(statistics.median(values), 4),
            "p95_bps": round(values_sorted[int(n * 0.95)] if n >= 20 else values_sorted[-1], 4),
            "std_bps": round(statistics.stdev(values), 4) if n >= 2 else 0,
        }

    return summary


def run_measurement(duration_days: int, symbols: list[str], interval_sec: int = 300):
    """Main measurement loop."""
    print(f"=== Continuous Spread Measurement ===")
    print(f"Duration: {duration_days} days")
    print(f"Interval: {interval_sec}s (every {interval_sec // 60} min)")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Output: {DATA_DIR}")
    print()

    end_time = datetime.now(timezone.utc) + timedelta(days=duration_days)
    all_measurements = []
    day_buckets: dict[str, list[dict]] = {}

    sample_count = 0
    while datetime.now(timezone.utc) < end_time:
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")

        measurements = measure_once(symbols)
        if measurements:
            all_measurements.extend(measurements)

            # Bucket by day
            if date_str not in day_buckets:
                day_buckets[date_str] = []
            day_buckets[date_str].extend(measurements)

            sample_count += 1
            if sample_count % 12 == 0:  # Every hour (12 x 5min)
                print(f"  [{now.strftime('%Y-%m-%d %H:%M UTC')}] "
                      f"Samples: {sample_count}, "
                      f"Total measurements: {len(all_measurements)}")

            # Save daily file at end of day or every 100 measurements
            if len(day_buckets[date_str]) >= 100 or now.hour == 23:
                save_day(day_buckets[date_str], date_str)
                day_buckets[date_str] = []

        # Sleep until next interval
        time.sleep(interval_sec)

    # Final save for any remaining data
    for date_str, data in day_buckets.items():
        if data:
            save_day(data, date_str)

    # Generate summary
    if all_measurements:
        summary = compute_summary(all_measurements)
        summary_path = DATA_DIR / "summary.json"
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\n=== Measurement Complete ===")
        print(f"Total measurements: {len(all_measurements)}")
        print(f"Summary saved to: {summary_path}")

        # Print quick summary
        print(f"\n{'Symbol':<10} {'Session':<12} {'N':>5} {'Mean':>8} {'P95':>8} {'Max':>8}")
        print("-" * 60)
        for key, stats in sorted(summary.items()):
            if stats["session"] != "ALL":
                print(f"{stats['symbol']:<10} {stats['session']:<12} "
                      f"{stats['n_samples']:>5} {stats['mean_bps']:>8.2f} "
                      f"{stats['p95_bps']:>8.2f} {stats['max_bps']:>8.2f}")
    else:
        print("\nERROR: No measurements collected. Check MT5 connection.")


def main():
    parser = argparse.ArgumentParser(description="Continuous spread measurement for cost calibration")
    parser.add_argument("--duration-days", type=int, default=7, help="Measurement duration in days (default: 7)")
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS, help="Symbols to measure")
    parser.add_argument("--interval", type=int, default=300, help="Measurement interval in seconds (default: 300)")
    parser.add_argument("--once", action="store_true", help="Take single snapshot and exit (no loop)")
    args = parser.parse_args()

    if args.once:
        measurements = measure_once(args.symbols)
        if measurements:
            print(json.dumps(measurements, indent=2))
        else:
            print("No measurements collected.")
        return

    run_measurement(args.duration_days, args.symbols, args.interval)


if __name__ == "__main__":
    main()
