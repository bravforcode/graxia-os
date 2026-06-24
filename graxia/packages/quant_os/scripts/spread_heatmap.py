"""
SPREAD HEATMAP — 24-hour spread collection across symbols.

Records bid/ask/spread every N seconds for multiple symbols to identify
the tightest entry windows. Saves raw CSV + hourly summary report.

Usage:
    python scripts/spread_heatmap.py [--interval 300] [--duration 86400] [--symbols XAUUSD,EURUSD,GBPUSD]
"""
import argparse
import csv
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import MetaTrader5 as mt5

SYMBOLS_DEFAULT = ["XAUUSD", "EURUSD", "GBPUSD"]
MT5_PATH = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts", "spread_heatmap")


def init_mt5(symbols: list):
    res = mt5.initialize(path=MT5_PATH, timeout=30000)
    if not res:
        print(f"FAIL_CONNECT: {mt5.last_error()}")
        sys.exit(1)
    for sym in symbols:
        mt5.symbol_select(sym, True)
    return res


def collect_spread(symbol: str) -> dict:
    tick = mt5.symbol_info_tick(symbol)
    info = mt5.symbol_info(symbol)
    if not tick or not info:
        return None
    spread_price = round(tick.ask - tick.bid, 5)
    spread_points = round(spread_price / info.point, 1) if info.point else 0
    return {
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "symbol": symbol,
        "bid": tick.bid,
        "ask": tick.ask,
        "spread_price": spread_price,
        "spread_points": spread_points,
    }


def print_hourly_summary(hour_data: dict, hour_start: datetime):
    print(f"\n--- Hourly Summary: {hour_start.strftime('%Y-%m-%d %H:00 UTC')} ---")
    for sym in sorted(hour_data):
        entries = hour_data[sym]
        avg_spread = sum(e["spread_points"] for e in entries) / len(entries)
        min_sp = min(e["spread_points"] for e in entries)
        max_sp = max(e["spread_points"] for e in entries)
        print(f"  {sym}: avg={avg_spread:.1f}  min={min_sp:.1f}  max={max_sp:.1f}  samples={len(entries)}")
    print()


def generate_report(all_data: dict, symbols: list):
    report_path = os.path.join(OUTPUT_DIR, "report_hourly_best.txt")
    lines = []
    lines.append("=" * 60)
    lines.append("SPREAD HEATMAP REPORT — Best Entry Hours by Symbol")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"{'Symbol':<10} {'Best Hour (UTC)':<18} {'Avg Spread':<12} {'Worst Hour (UTC)':<18} {'Avg Spread':<12}")
    lines.append("-" * 70)

    for sym in symbols:
        if sym not in all_data:
            continue
        hour_avgs = defaultdict(list)
        for entry in all_data[sym]:
            dt_obj = datetime.fromisoformat(entry["timestamp_utc"].replace("Z", "+00:00"))
            hour_key = dt_obj.strftime("%Y-%m-%d %H:00")
            hour_avgs[hour_key].append(entry["spread_points"])

        best_hour = min(hour_avgs, key=lambda h: sum(hour_avgs[h]) / len(hour_avgs[h]))
        worst_hour = max(hour_avgs, key=lambda h: sum(hour_avgs[h]) / len(hour_avgs[h]))
        best_avg = sum(hour_avgs[best_hour]) / len(hour_avgs[best_hour])
        worst_avg = sum(hour_avgs[worst_hour]) / len(hour_avgs[worst_hour])
        lines.append(f"{sym:<10} {best_hour:<18} {best_avg:<12.1f} {worst_hour:<18} {worst_avg:<12.1f}")

    lines.append("")
    lines.append("Hour-by-hour breakdown:")
    lines.append("-" * 70)
    all_hours = sorted({k for sym in symbols if sym in all_data for k in {
        datetime.fromisoformat(e["timestamp_utc"].replace("Z", "+00:00")).strftime("%Y-%m-%d %H:00")
        for e in all_data[sym]
    }})

    header = f"{'Hour (UTC)':<20}"
    for sym in symbols:
        header += f" {sym:>18}"
    lines.append(header)
    lines.append("-" * (20 + 19 * len(symbols)))

    for hour in all_hours:
        row = f"{hour:<20}"
        for sym in symbols:
            if sym in all_data:
                avgs = [e["spread_points"] for e in all_data[sym]
                        if datetime.fromisoformat(e["timestamp_utc"].replace("Z", "+00:00")).strftime("%Y-%m-%d %H:00") == hour]
                if avgs:
                    row += f" {sum(avgs)/len(avgs):>18.1f}"
                else:
                    row += f" {'N/A':>18}"
        lines.append(row)

    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"\nReport saved: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Spread heatmap collector — 24h")
    parser.add_argument("--interval", type=int, default=300, help="Seconds between samples (default: 300)")
    parser.add_argument("--duration", type=int, default=86400, help="Total seconds to collect (default: 86400)")
    parser.add_argument("--symbols", type=str, default=",".join(SYMBOLS_DEFAULT), help="Comma-separated symbols")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")]
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    csv_path = os.path.join(OUTPUT_DIR, f"spread_{date_str}.csv")
    is_new = not os.path.exists(csv_path)
    csv_file = open(csv_path, "a", newline="")
    fieldnames = ["timestamp_utc", "symbol", "bid", "ask", "spread_price", "spread_points"]
    writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
    if is_new:
        writer.writeheader()

    init_mt5(symbols)
    print(f"Collecting spreads: symbols={symbols} interval={args.interval}s duration={args.duration}s")
    print(f"Output: {csv_path}")

    all_data = defaultdict(list)
    start = time.time()
    count = 0
    last_hour = None

    try:
        while time.time() - start < args.duration:
            now_utc = datetime.now(timezone.utc)
            current_hour = now_utc.strftime("%Y-%m-%d %H:00")

            for sym in symbols:
                entry = collect_spread(sym)
                if entry:
                    writer.writerow(entry)
                    csv_file.flush()
                    all_data[sym].append(entry)
                    count += 1

            if current_hour != last_hour:
                if last_hour is not None:
                    hour_start = datetime.strptime(last_hour, "%Y-%m-%d %H:00").replace(tzinfo=timezone.utc)
                    hour_data = defaultdict(list)
                    for sym in symbols:
                        if sym in all_data:
                            for e in all_data[sym]:
                                et = datetime.fromisoformat(e["timestamp_utc"].replace("Z", "+00:00"))
                                if et.strftime("%Y-%m-%d %H:00") == last_hour:
                                    hour_data[sym].append(e)
                    if hour_data:
                        print_hourly_summary(hour_data, hour_start)
                last_hour = current_hour

            elapsed = int(time.time() - start)
            remaining = args.duration - elapsed
            if count % 50 == 0:
                print(f"  [{elapsed}s/{args.duration}s] samples={count} remaining={remaining}s")
            remaining_sleep = max(0, args.interval - (time.time() - start) % args.interval)
            time.sleep(remaining_sleep)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        csv_file.close()
        mt5.shutdown()
        print(f"Done. Total samples: {count}. File: {csv_path}")
        generate_report(all_data, symbols)


if __name__ == "__main__":
    main()
