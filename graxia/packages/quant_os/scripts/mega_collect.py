"""
MEGA DATA COLLECTOR — Bulk tick download + batch orders + dataset builder.

Phase 1: Download historical ticks via copy_ticks_range (100x faster than real-time)
Phase 2: Run N demo orders with auto-approve, record execution data
Phase 3: Build training dataset from tick + order data

Usage:
    python scripts/mega_collect.py [--ticks-months 3] [--order-count 50] [--order-interval 10]
"""
import argparse
import csv
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from glob import glob
from uuid import uuid4

import MetaTrader5 as mt5
import numpy as np

# ── Constants ──
SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD"]
TERMINAL_PATH = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"
OUTPUT_BASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts", "mega_data")
TICK_DIR = os.path.join(OUTPUT_BASE, "ticks")
ORDER_DIR = os.path.join(OUTPUT_BASE, "orders")
DATASET_DIR = os.path.join(OUTPUT_BASE, "dataset")


# ============================================================
# PHASE 1: BULK HISTORICAL TICK DOWNLOAD
# ============================================================

def download_ticks_bulk(symbols, months_back=3):
    """Download historical ticks using copy_ticks_range. Returns dict of symbol -> numpy array."""
    os.makedirs(TICK_DIR, exist_ok=True)
    results = {}

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=months_back * 30)

    print(f"\n{'='*60}")
    print(f"PHASE 1: BULK TICK DOWNLOAD")
    print(f"  Range: {start_date.date()} -> {end_date.date()} ({months_back} months)")
    print(f"  Symbols: {symbols}")
    print(f"{'='*60}")

    for sym in symbols:
        print(f"\n  Downloading {sym}...")
        all_ticks = []

        # Download in monthly chunks (MT5 has limits per call)
        current = start_date
        while current < end_date:
            chunk_end = min(current + timedelta(days=30), end_date)
            ticks = mt5.copy_ticks_range(sym, current, chunk_end, mt5.COPY_TICKS_ALL)
            if ticks is not None and len(ticks) > 0:
                all_ticks.append(ticks)
                print(f"    {current.date()} -> {chunk_end.date()}: {len(ticks)} ticks")
            else:
                print(f"    {current.date()} -> {chunk_end.date()}: 0 ticks")
            current = chunk_end

        if all_ticks:
            combined = np.concatenate(all_ticks)
            # Deduplicate by time
            _, unique_idx = np.unique(combined['time'], return_index=True)
            combined = combined[unique_idx]

            # Save as CSV (numpy doesn't have native parquet without pandas)
            filepath = os.path.join(TICK_DIR, f"{sym}_bulk.csv")
            with open(filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['time', 'bid', 'ask', 'last', 'flags', 'volume_real'])
                for row in combined:
                    vol = row['volume_real'] if 'volume_real' in combined.dtype.names else 0
                    writer.writerow([
                        int(row['time']), row['bid'], row['ask'], row['last'],
                        int(row['flags']), vol
                    ])

            results[sym] = combined
            print(f"  [OK] {sym}: {len(combined)} unique ticks -> {filepath}")
        else:
            print(f"  [SKIP] {sym}: No tick data available")

    return results


# ============================================================
# PHASE 2: BATCH DEMO ORDERS
# ============================================================

def get_filling_mode(symbol):
    info = mt5.symbol_info(symbol)
    if not info:
        return 1
    fm = info.filling_mode
    return 1 if fm & 2 else (0 if fm & 1 else 0)


def calc_sl_tp(symbol, side):
    tick = mt5.symbol_info_tick(symbol)
    info = mt5.symbol_info(symbol)
    if not tick or not info:
        return None, None, None

    point = info.point
    tick_size = info.trade_tick_size
    stops_level = info.trade_stops_level
    freeze_level = info.trade_freeze_level

    buffer = max(stops_level * point, freeze_level * point, 0.1)
    if tick_size > 0:
        buffer = round(buffer / tick_size) * tick_size

    if side == "BUY":
        entry = tick.ask
        sl = round((tick.bid - buffer) / tick_size) * tick_size if tick_size else tick.bid - buffer
        gross_loss = entry - sl
        tp = round((entry + gross_loss) / tick_size) * tick_size if tick_size else entry + gross_loss
    else:
        entry = tick.bid
        sl = round((tick.ask + buffer) / tick_size) * tick_size if tick_size else tick.ask + buffer
        gross_loss = sl - entry
        tp = round((entry - gross_loss) / tick_size) * tick_size if tick_size else entry - gross_loss

    return round(entry, 5), round(sl, 5), round(tp, 5)


def send_close_order(symbol, side, volume, ticket, filling_mode, magic, comment):
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return {"retcode": -999, "error": "NO_TICK"}

    close_type = mt5.ORDER_TYPE_SELL if side == "BUY" else mt5.ORDER_TYPE_BUY
    close_price = tick.bid if side == "BUY" else tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": close_type,
        "position": ticket,
        "price": close_price,
        "deviation": 30,
        "magic": magic,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_mode,
    }

    result = mt5.order_send(request)
    if result is None:
        return {"retcode": -1, "error": "NONE"}
    return {"retcode": result.retcode, "deal": result.deal, "comment": result.comment}


def run_batch_orders(symbols, count=50, interval=10, volume=0.01):
    """Run batch orders. Returns list of order records."""
    os.makedirs(ORDER_DIR, exist_ok=True)
    csv_path = os.path.join(ORDER_DIR, f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv")

    fieldnames = [
        "order_id", "symbol", "side", "volume", "entry", "sl", "tp",
        "send_retcode", "send_deal", "send_price", "send_time",
        "close_retcode", "close_deal", "close_time",
        "slippage_points", "latency_ms", "status"
    ]

    print(f"\n{'='*60}")
    print(f"PHASE 2: BATCH DEMO ORDERS")
    print(f"  Count: {count} | Interval: {interval}s | Volume: {volume}")
    print(f"  Symbols: {symbols}")
    print(f"{'='*60}")

    results = []
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for i in range(count):
            sym = symbols[i % len(symbols)]
            side = "BUY" if i % 2 == 0 else "SELL"
            filling = get_filling_mode(sym)
            order_id = uuid4().hex
            magic = int(hashlib.sha256(f"batch-{order_id}".encode()).hexdigest()[:8], 16)

            entry, sl, tp = calc_sl_tp(sym, side)
            if entry is None:
                print(f"  [{i+1}/{count}] {sym} {side} SKIP (no tick)")
                continue

            # Send order
            tick = mt5.symbol_info_tick(sym)
            order_type = mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": sym,
                "volume": volume,
                "type": order_type,
                "price": tick.ask if side == "BUY" else tick.bid,
                "sl": sl,
                "tp": tp,
                "deviation": 30,
                "magic": magic,
                "comment": f"BATCH_{order_id[:8]}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling,
            }

            send_start = time.time()
            result = mt5.order_send(request)
            send_time = datetime.now(timezone.utc).isoformat()
            latency_ms = round((time.time() - send_start) * 1000)

            if result is None or result.retcode != 10009:
                retcode = result.retcode if result else -1
                record = {
                    "order_id": order_id, "symbol": sym, "side": side, "volume": volume,
                    "entry": entry, "sl": sl, "tp": tp,
                    "send_retcode": retcode, "send_deal": 0, "send_price": 0,
                    "send_time": send_time, "close_retcode": 0, "close_deal": 0,
                    "close_time": "", "slippage_points": 0, "latency_ms": latency_ms,
                    "status": "REJECTED"
                }
                writer.writerow(record)
                f.flush()
                results.append(record)
                print(f"  [{i+1}/{count}] {sym} {side} REJECTED retcode={retcode}")
                time.sleep(interval)
                continue

            exec_price = result.price
            deal = result.deal

            # Wait for position
            time.sleep(0.5)

            # Find and close position
            positions = mt5.positions_get(symbol=sym)
            close_result = {"retcode": -1, "error": "NO_POSITION"}
            close_time = ""

            for p in positions:
                if f"BATCH_{order_id[:8]}" in (p.comment or ""):
                    time.sleep(1)
                    cr = send_close_order(sym, side, volume, p.ticket, filling, magic, f"CLOSE_{order_id[:8]}")
                    close_result = cr
                    close_time = datetime.now(timezone.utc).isoformat()
                    break

            slippage = round((exec_price - entry) / mt5.symbol_info(sym).point, 1) if mt5.symbol_info(sym) else 0

            record = {
                "order_id": order_id, "symbol": sym, "side": side, "volume": volume,
                "entry": entry, "sl": sl, "tp": tp,
                "send_retcode": 10009, "send_deal": deal, "send_price": exec_price,
                "send_time": send_time,
                "close_retcode": close_result.get("retcode", 0),
                "close_deal": close_result.get("deal", 0),
                "close_time": close_time,
                "slippage_points": slippage, "latency_ms": latency_ms,
                "status": "EXECUTED"
            }
            writer.writerow(record)
            f.flush()
            results.append(record)

            print(f"  [{i+1}/{count}] {sym} {side} OK deal={deal} price={exec_price} slip={slippage}pt latency={latency_ms}ms")

            if i < count - 1:
                time.sleep(interval)

    return results, csv_path


# ============================================================
# PHASE 3: BUILD TRAINING DATASET
# ============================================================

def build_dataset(tick_data, order_records):
    """Build training dataset from order records + historical tick statistics."""
    os.makedirs(DATASET_DIR, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"PHASE 3: BUILD TRAINING DATASET")
    print(f"{'='*60}")

    # Compute historical tick stats per symbol
    tick_stats = {}
    for sym, ticks in tick_data.items():
        if len(ticks) == 0:
            continue
        bids = [float(t['bid']) for t in ticks]
        asks = [float(t['ask']) for t in ticks]
        spreads = [float(t['ask']) - float(t['bid']) for t in ticks]
        tick_stats[sym] = {
            "bid_mean": round(np.mean(bids), 5),
            "bid_std": round(np.std(bids), 5),
            "ask_mean": round(np.mean(asks), 5),
            "ask_std": round(np.std(asks), 5),
            "spread_mean": round(np.mean(spreads), 5),
            "spread_std": round(np.std(spreads), 5),
            "spread_max": round(max(spreads), 5),
            "tick_count": len(ticks),
        }

    features = []
    for record in order_records:
        if record["status"] != "EXECUTED":
            continue

        sym = record["symbol"]
        stats = tick_stats.get(sym, {})

        feature = {
            "order_id": record["order_id"],
            "symbol": sym,
            "side": record["side"],
            "volume": record["volume"],
            "entry": record["entry"],
            "sl": record["sl"],
            "tp": record["tp"],
            "send_price": record["send_price"],
            "slippage_points": record["slippage_points"],
            "latency_ms": record["latency_ms"],
            "close_retcode": record.get("close_retcode", 0),
            # Historical tick context
            "hist_bid_mean": stats.get("bid_mean"),
            "hist_bid_std": stats.get("bid_std"),
            "hist_ask_mean": stats.get("ask_mean"),
            "hist_ask_std": stats.get("ask_std"),
            "hist_spread_mean": stats.get("spread_mean"),
            "hist_spread_std": stats.get("spread_std"),
            "hist_spread_max": stats.get("spread_max"),
            "hist_tick_count": stats.get("tick_count"),
            "send_time": record["send_time"],
        }
        features.append(feature)

    if not features:
        print("  No features generated (no orders with surrounding ticks)")
        return None

    # Write CSV
    csv_path = os.path.join(DATASET_DIR, f"training_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv")
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=features[0].keys())
        writer.writeheader()
        writer.writerows(features)

    # Summary
    symbols = set(f["symbol"] for f in features)
    sides = {"BUY": sum(1 for f in features if f["side"] == "BUY"),
             "SELL": sum(1 for f in features if f["side"] == "SELL")}
    avg_slippage = round(np.mean([abs(float(f["slippage_points"])) for f in features]), 2)
    avg_latency = round(np.mean([float(f["latency_ms"]) for f in features]), 0)

    summary = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_features": len(features),
        "symbols": list(symbols),
        "side_distribution": sides,
        "avg_slippage_points": avg_slippage,
        "avg_latency_ms": avg_latency,
        "csv": csv_path,
    }

    with open(os.path.join(DATASET_DIR, "dataset_summary.json"), 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"  Features: {len(features)} rows")
    print(f"  Symbols: {symbols}")
    print(f"  Side dist: {sides}")
    print(f"  Avg slippage: {avg_slippage} points")
    print(f"  Avg latency: {avg_latency}ms")
    print(f"  CSV: {csv_path}")

    return csv_path


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Mega data collector")
    parser.add_argument("--ticks-months", type=int, default=3, help="Months of historical ticks")
    parser.add_argument("--order-count", type=int, default=50, help="Number of demo orders")
    parser.add_argument("--order-interval", type=int, default=10, help="Seconds between orders")
    parser.add_argument("--volume", type=float, default=0.01, help="Volume per order")
    parser.add_argument("--skip-ticks", action="store_true", help="Skip tick download")
    parser.add_argument("--skip-orders", action="store_true", help="Skip order execution")
    args = parser.parse_args()

    os.makedirs(OUTPUT_BASE, exist_ok=True)

    # Init MT5
    res = mt5.initialize(path=TERMINAL_PATH, timeout=30000)
    if not res:
        print(f"FAIL_CONNECT: {mt5.last_error()}")
        sys.exit(1)

    for sym in SYMBOLS:
        mt5.symbol_select(sym, True)

    print(f"{'='*60}")
    print(f"MEGA DATA COLLECTOR")
    print(f"  Time: {datetime.now(timezone.utc).isoformat()}")
    print(f"  Account: {mt5.account_info().login}")
    print(f"  Balance: ${mt5.account_info().balance:,.2f}")
    print(f"{'='*60}")

    tick_data = {}
    order_records = []
    order_csv = None

    # Phase 1: Bulk tick download
    if not args.skip_ticks:
        tick_data = download_ticks_bulk(SYMBOLS, args.ticks_months)
    else:
        print("\nSkipping tick download (--skip-ticks)")
        # Load existing tick files
        for sym in SYMBOLS:
            filepath = os.path.join(TICK_DIR, f"{sym}_bulk.csv")
            if os.path.exists(filepath):
                ticks = []
                with open(filepath, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        ticks.append(row)
                tick_data[sym] = ticks
                print(f"  Loaded {len(ticks)} existing ticks for {sym}")

    # Phase 2: Batch orders
    if not args.skip_orders:
        order_records, order_csv = run_batch_orders(
            SYMBOLS, args.order_count, args.order_interval, args.volume
        )
    else:
        print("\nSkipping orders (--skip-orders)")
        # Load existing order files
        for filepath in sorted(glob(os.path.join(ORDER_DIR, "batch_*.csv"))):
            with open(filepath, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    order_records.append(row)
            print(f"  Loaded {len(order_records)} existing orders from {filepath}")

    # Phase 3: Build dataset
    if tick_data and order_records:
        build_dataset(tick_data, order_records)
    else:
        print("\nCannot build dataset: missing tick data or order records")

    # Final summary
    acct = mt5.account_info()
    print(f"\n{'='*60}")
    print(f"MEGA COLLECT COMPLETE")
    print(f"  Balance: ${acct.balance:,.2f}")
    print(f"  Ticks: {sum(len(v) for v in tick_data.values())} total")
    print(f"  Orders: {len(order_records)} total")
    print(f"  Output: {OUTPUT_BASE}")
    print(f"{'='*60}")

    # Save run summary
    run_summary = {
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "balance": acct.balance,
        "total_ticks": sum(len(v) for v in tick_data.values()),
        "total_orders": len(order_records),
        "tick_dir": TICK_DIR,
        "order_dir": ORDER_DIR,
        "dataset_dir": DATASET_DIR,
    }
    with open(os.path.join(OUTPUT_BASE, "run_summary.json"), 'w') as f:
        json.dump(run_summary, f, indent=2)

    mt5.shutdown()


if __name__ == "__main__":
    main()
