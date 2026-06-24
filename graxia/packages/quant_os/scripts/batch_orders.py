"""
BATCH ORDER EXECUTOR — Automated demo order collection.

Runs N orders with auto-approve for demo data collection.
Each order: preflight → approve → send → record → close → next.

Usage:
    python scripts/batch_orders.py [--count 50] [--interval 30] [--symbols XAUUSD,EURUSD,GBPUSD]
"""
import argparse
import csv
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

import MetaTrader5 as mt5

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts", "batch_orders")
TERMINAL_PATH = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"

# Contract sizes per symbol
CONTRACT_SIZE = {"XAUUSD": 100, "EURUSD": 100000, "GBPUSD": 100000}


def init_mt5():
    res = mt5.initialize(path=TERMINAL_PATH, timeout=30000)
    if not res:
        print(f"FAIL_CONNECT: {mt5.last_error()}")
        sys.exit(1)
    return res


def get_filling_mode(symbol):
    info = mt5.symbol_info(symbol)
    if not info:
        return 1
    fm = info.filling_mode
    if fm & 2:
        return 1
    elif fm & 1:
        return 0
    return 0


def calc_sl_tp(symbol, side):
    """Calculate SL/TP with protective buffer."""
    tick = mt5.symbol_info_tick(symbol)
    info = mt5.symbol_info(symbol)
    if not tick or not info:
        return None, None, None, None

    stops_level = info.trade_stops_level
    freeze_level = info.trade_freeze_level
    point = info.point
    tick_size = info.trade_tick_size

    buffer = max(stops_level * point, freeze_level * point, 0.1)
    buffer = round(buffer / tick_size) * tick_size if tick_size else buffer

    spread = tick.ask - tick.bid

    if side == "BUY":
        entry = tick.ask
        sl = round((tick.bid - buffer) / tick_size) * tick_size
        gross_loss = entry - sl
        tp = round((entry + gross_loss) / tick_size) * tick_size
    else:
        entry = tick.bid
        sl = round((tick.ask + buffer) / tick_size) * tick_size
        gross_loss = sl - entry
        tp = round((entry - gross_loss) / tick_size) * tick_size

    return entry, round(sl, 5), round(tp, 5), round(buffer, 5)


def send_order(symbol, side, volume, sl, tp, filling_mode, order_id):
    """Send one order. Returns result dict."""
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return {"retcode": -999, "error": "NO_TICK"}

    price = tick.ask if side == "BUY" else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 30,
        "magic": int(hashlib.sha256(f"batch-{order_id}".encode()).hexdigest()[:8], 16),
        "comment": f"BATCH_{order_id[:8]}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_mode,
    }

    result = mt5.order_send(request)
    if result is None:
        return {"retcode": -1, "error": "NONE_RESULT"}

    return {
        "retcode": result.retcode,
        "deal": result.deal,
        "order": result.order,
        "volume": result.volume,
        "price": result.price,
        "comment": result.comment,
    }


def close_position(ticket, symbol, side, volume, filling_mode, order_id):
    """Close a position by ticket."""
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
        "magic": int(hashlib.sha256(f"batch-{order_id}".encode()).hexdigest()[:8], 16),
        "comment": f"CLOSE_{order_id[:8]}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_mode,
    }

    result = mt5.order_send(request)
    if result is None:
        return {"retcode": -1, "error": "NONE_RESULT"}

    return {
        "retcode": result.retcode,
        "deal": result.deal,
        "order": result.order,
        "comment": result.comment,
    }


def run_one_order(symbol, side, volume, order_id, filling_mode):
    """Execute one full order lifecycle: send → wait → close → record."""
    entry, sl, tp, buffer = calc_sl_tp(symbol, side)
    if entry is None:
        return {"order_id": order_id, "status": "SKIP", "reason": "NO_TICK"}

    # Send
    send_result = send_order(symbol, side, volume, sl, tp, filling_mode, order_id)
    send_time = datetime.now(timezone.utc).isoformat()

    if send_result["retcode"] != 10009:
        return {
            "order_id": order_id,
            "status": "REJECTED",
            "symbol": symbol,
            "side": side,
            "send_retcode": send_result["retcode"],
            "send_comment": send_result.get("comment", ""),
            "send_time": send_time,
        }

    deal = send_result["deal"]
    exec_price = send_result["price"]

    # Wait briefly for position to appear
    time.sleep(0.5)

    # Find position
    positions = mt5.positions_get(symbol=symbol)
    pos_ticket = None
    for p in positions:
        if f"BATCH_{order_id[:8]}" in (p.comment or ""):
            pos_ticket = p.ticket
            break

    # Close
    time.sleep(1)
    close_result = {}
    if pos_ticket:
        close_result = close_position(pos_ticket, symbol, side, volume, filling_mode, order_id)
    close_time = datetime.now(timezone.utc).isoformat()

    # Record
    record = {
        "order_id": order_id,
        "symbol": symbol,
        "side": side,
        "volume": volume,
        "entry_planned": entry,
        "entry_actual": exec_price,
        "sl": sl,
        "tp": tp,
        "buffer": buffer,
        "send_retcode": send_result["retcode"],
        "send_deal": deal,
        "send_time": send_time,
        "close_retcode": close_result.get("retcode"),
        "close_deal": close_result.get("deal"),
        "close_time": close_time,
        "slippage_points": round((exec_price - entry) / mt5.symbol_info(symbol).point, 1) if mt5.symbol_info(symbol) else None,
        "status": "EXECUTED",
    }

    return record


def main():
    parser = argparse.ArgumentParser(description="Batch order executor")
    parser.add_argument("--count", type=int, default=50, help="Number of orders to run")
    parser.add_argument("--interval", type=int, default=15, help="Seconds between orders")
    parser.add_argument("--symbols", type=str, default="XAUUSD,EURUSD,GBPUSD", help="Comma-separated symbols")
    parser.add_argument("--volume", type=float, default=0.01, help="Volume per order")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")]
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # CSV output
    csv_path = os.path.join(OUTPUT_DIR, f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv")
    fieldnames = [
        "order_id", "symbol", "side", "volume", "entry_planned", "entry_actual",
        "sl", "tp", "buffer", "send_retcode", "send_deal", "send_time",
        "close_retcode", "close_deal", "close_time", "slippage_points", "status"
    ]

    init_mt5()

    print(f"Batch order executor: count={args.count} interval={args.interval}s symbols={symbols}")
    print(f"Output: {csv_path}")

    results = []
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for i in range(args.count):
            sym = symbols[i % len(symbols)]
            side = "BUY" if i % 2 == 0 else "SELL"
            filling = get_filling_mode(sym)
            order_id = uuid4().hex

            print(f"\n[{i+1}/{args.count}] {sym} {side} vol={args.volume} id={order_id[:8]}")

            record = run_one_order(sym, side, args.volume, order_id, filling)
            writer.writerow(record)
            f.flush()
            results.append(record)

            status = record["status"]
            retcode = record.get("send_retcode", "N/A")
            print(f"  Status: {status} retcode={retcode}")

            if i < args.count - 1:
                time.sleep(args.interval)

    # Summary
    executed = sum(1 for r in results if r["status"] == "EXECUTED")
    rejected = sum(1 for r in results if r["status"] == "REJECTED")
    skipped = sum(1 for r in results if r["status"] == "SKIP")

    print(f"\n{'='*60}")
    print(f"BATCH COMPLETE")
    print(f"  Total: {args.count}")
    print(f"  Executed: {executed}")
    print(f"  Rejected: {rejected}")
    print(f"  Skipped: {skipped}")
    print(f"  CSV: {csv_path}")
    print(f"{'='*60}")

    # Save summary
    summary = {
        "batch_time_utc": datetime.now(timezone.utc).isoformat(),
        "total": args.count,
        "executed": executed,
        "rejected": rejected,
        "skipped": skipped,
        "symbols": symbols,
        "csv": csv_path,
    }
    with open(os.path.join(OUTPUT_DIR, "batch_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    mt5.shutdown()


if __name__ == "__main__":
    main()
