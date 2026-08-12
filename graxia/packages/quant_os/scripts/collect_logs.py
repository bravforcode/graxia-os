"""
Continuous Execution Log Collector — MT5 account + market data snapshotter.

Collects account snapshots, open positions, recent deals, ticks/spreads,
and order book depth on a schedule. Supports snapshot (one-shot) and
continuous (infinite loop) modes with daily file rotation.

Usage:
    python scripts/collect_logs.py --symbols EURUSD,GBPUSD,XAUUSD
                                   --output artifacts/live_logs
                                   --mode snapshot|continuous
                                   --interval 60
"""
import argparse
import csv
import os
import random
import signal
import sys
import time
from datetime import datetime, UTC

# Conditional MT5 import (not required for --mock mode)
try:
    import MetaTrader5 as mt5
    MT5_OK = True
except ImportError:
    mt5 = None
    MT5_OK = False

try:
    from broker.mt5_gateway import (
        initialize_mt5,
        get_account_info,
        get_current_tick,
        shutdown_mt5,
        Mt5UnavailableError,
    )
    GATEWAY_OK = True
except ImportError:
    initialize_mt5 = get_account_info = get_current_tick = shutdown_mt5 = None
    Mt5UnavailableError = Exception
    GATEWAY_OK = False

SYMBOLS_DEFAULT = ["XAUUSD", "EURUSD", "GBPUSD"]
MT5_PATH = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"
CSV_FIELDS = [
    "timestamp_utc", "balance", "equity", "margin", "margin_level",
    "profit", "spread_points", "bid", "ask", "open_positions", "source",
]


MOCK_ACCOUNT = {
    "balance": 50000.0, "equity": 50123.45, "margin": 0.0,
    "margin_level": 0.0, "profit": 123.45, "currency": "USD",
    "leverage": 500, "name": "Mock Demo",
}

MOCK_TICK = {"bid": 1.1045, "ask": 1.1048, "spread": 3, "time": None}


def ensure_connected(mock: bool = False):
    if mock:
        return True
    if not MT5_OK or not GATEWAY_OK:
        print("  [WARN] MT5 not available. Use --mock to run without MT5.")
        return False
    try:
        info = mt5.terminal_info()
        if info and info.connected:
            return True
    except Exception:
        pass
    for attempt in range(3):
        try:
            initialize_mt5(MT5_PATH, timeout=15000)
            for sym in SYMBOLS_DEFAULT:
                mt5.symbol_select(sym, True)
            return True
        except Mt5UnavailableError:
            time.sleep(2 ** attempt)
    return False


def collect_account_snapshot_mock() -> dict:
    """Generate a realistic-looking mock account snapshot from warehouse data."""
    rng = random.Random(int(time.time()) // 60)  # changes every minute
    equity_drift = rng.gauss(0, 50)
    return {
        "balance": MOCK_ACCOUNT["balance"],
        "equity": MOCK_ACCOUNT["balance"] + equity_drift,
        "margin": rng.uniform(0, 200),
        "margin_level": 50000 / max(rng.uniform(1, 200), 1),
        "profit": equity_drift,
        "currency": "USD",
        "leverage": 500,
    }


def collect_open_positions_mock() -> tuple[int, list]:
    """Generate mock open positions."""
    rng = random.Random(int(time.time()) // 300)  # changes every 5 min
    count = rng.randint(0, 3)
    positions = []
    for i in range(count):
        sym = rng.choice(SYMBOLS_DEFAULT)
        ptype = "BUY" if rng.random() > 0.5 else "SELL"
        price = 2000.0 if "XAU" in sym else 1.10
        positions.append({
            "ticket": 1000000 + i,
            "symbol": sym,
            "type": ptype,
            "volume": 0.01,
            "price_open": price + rng.gauss(0, 0.001),
            "sl": 0.0, "tp": 0.0,
            "profit": rng.gauss(0, 10),
            "swap": rng.gauss(0, 0.5),
        })
    return count, positions


def collect_tick_mock(symbol: str) -> dict:
    """Generate a realistic mock tick."""
    rng = random.Random(int(time.time() * 1000) % 1000000)
    is_xau = "XAU" in symbol.upper()
    base = 2000.0 if is_xau else 1.1050
    spread = rng.uniform(1, 8) * (0.01 if is_xau else 0.0001)
    mid = base + rng.gauss(0, 0.001 if is_xau else 0.00005)
    return {
        "bid": round(mid - spread / 2, 5),
        "ask": round(mid + spread / 2, 5),
        "spread": int(spread / (0.01 if is_xau else 0.0001)),
    }


def collect_account_snapshot(mock: bool = False):
    if mock:
        return collect_account_snapshot_mock()
    try:
        return get_account_info()
    except Mt5UnavailableError:
        return None


def collect_open_positions(mock: bool = False):
    if mock:
        return collect_open_positions_mock()
    try:
        positions = mt5.positions_get()
        if positions is None:
            return 0, []
        return len(positions), [
            {
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == 0 else "SELL",
                "volume": p.volume,
                "price_open": p.price_open,
                "sl": p.sl,
                "tp": p.tp,
                "profit": p.profit,
                "swap": p.swap,
                "comment": p.comment,
            }
            for p in positions
        ]
    except Exception as e:
        print(f"  [WARN] Positions error: {e}")
        return 0, []


def collect_recent_deals(limit=100, mock: bool = False):
    if mock:
        return []
    try:
        now = datetime.now(UTC)
        from_dt = datetime(now.year, now.month, now.day, tzinfo=UTC)
        deals = mt5.history_deals_get(from_dt, now)
        if deals is None:
            return []
        sorted_deals = sorted(deals, key=lambda d: d.time, reverse=True)[:limit]
        return [
            {
                "ticket": d.ticket,
                "symbol": d.symbol,
                "type": "BUY" if d.type == 0 else "SELL",
                "volume": d.volume,
                "price": d.price,
                "profit": d.profit,
                "commission": d.commission,
                "swap": d.swap,
                "time": datetime.fromtimestamp(d.time, tz=UTC).isoformat(),
                "comment": d.comment,
            }
            for d in sorted_deals
        ]
    except Exception as e:
        print(f"  [WARN] Deals error: {e}")
        return []


def collect_tick(symbol, mock: bool = False):
    if mock:
        return collect_tick_mock(symbol)
    try:
        tick = get_current_tick(symbol)
        info = mt5.symbol_info(symbol)
        spread_points = 0.0
        if info and info.point:
            spread_points = round((tick["ask"] - tick["bid"]) / info.point, 1)
        return {
            "bid": tick["bid"],
            "ask": tick["ask"],
            "spread_points": spread_points,
        }
    except Mt5UnavailableError:
        return None


def collect_order_book(symbol):
    try:
        mt5.market_book_add(symbol)
        time.sleep(0.5)
        depth = None
        for _ in range(5):
            depth = mt5.market_book_get(symbol)
            if depth and len(depth) > 0:
                break
            time.sleep(0.3)
        mt5.market_book_release(symbol)
        if depth and len(depth) > 0:
            bids = [d for d in depth if d.type == 1][:10]
            asks = [d for d in depth if d.type == 2][:10]
            return {
                "bid_depth": [(round(d.price, 5), d.volume) for d in bids],
                "ask_depth": [(round(d.price, 5), d.volume) for d in asks],
            }
    except Exception:
        pass
    return {"bid_depth": [], "ask_depth": []}


def get_csv_path(output_dir, symbol):
    date_str = datetime.now(UTC).strftime("%Y%m%d")
    sym_dir = os.path.join(output_dir, symbol)
    os.makedirs(sym_dir, exist_ok=True)
    return os.path.join(sym_dir, f"logs_{date_str}.csv")


def write_log_row(writer, file_obj, account, positions_count, tick_data, source="mt5"):
    now_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = {
        "timestamp_utc": now_utc,
        "balance": account.get("balance", 0.0),
        "equity": account.get("equity", 0.0),
        "margin": account.get("margin", 0.0),
        "margin_level": account.get("margin_level", 0.0),
        "profit": account.get("profit", 0.0),
        "spread_points": tick_data.get("spread_points", 0.0),
        "bid": tick_data.get("bid", 0.0),
        "ask": tick_data.get("ask", 0.0),
        "open_positions": positions_count,
        "source": source,
    }
    writer.writerow(row)
    file_obj.flush()


def open_csv(output_dir, symbol):
    csv_path = get_csv_path(output_dir, symbol)
    is_new = not os.path.exists(csv_path)
    f = open(csv_path, "a", newline="")
    writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
    if is_new:
        writer.writeheader()
    return writer, f


def run_snapshot(symbols, output_dir, mock: bool = False):
    for sym in symbols:
        account = collect_account_snapshot(mock=mock)
        if not account:
            print(f"  [SKIP] {sym}: MT5 unavailable (use --mock to run without MT5)")
            continue
        pos_count, positions = collect_open_positions(mock=mock)
        deals = collect_recent_deals(100, mock=mock)
        tick = collect_tick(sym, mock=mock)
        book = collect_order_book(sym)

        print(f"  {sym}: bal={account.get('balance')} eq={account.get('equity')} "
              f"ml={account.get('margin_level')} pnl={account.get('profit')} "
              f"pos={pos_count} deals={len(deals)} spread={tick.get('spread_points', 'N/A')}pt "
              f"book_bids={len(book['bid_depth'])} book_asks={len(book['ask_depth'])}")

        writer, f = open_csv(output_dir, sym)
        write_log_row(writer, f, account, pos_count, tick or {})
        f.close()


def run_continuous(symbols, output_dir, interval, mock: bool = False):
    print(f"Continuous mode: interval={interval}s, symbols={symbols}")
    if mock:
        print("  [MOCK] Using synthetic data (no MT5 connection)")
    print("Press Ctrl+C to stop.")

    stop_flag = [False]

    def handler(signum, frame):
        if not stop_flag[0]:
            print("\nShutdown signal received, stopping...")
        stop_flag[0] = True

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    writers = {}
    files = {}
    for sym in symbols:
        writer, f = open_csv(output_dir, sym)
        writers[sym] = writer
        files[sym] = f

    try:
        while not stop_flag[0]:
            now_tag = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            print(f"\n[{now_tag}] Collecting...")
            account = collect_account_snapshot(mock=mock)
            if not account:
                print("  [SKIP] MT5 unavailable — reconnecting...")
                if ensure_connected(mock=mock):
                    continue
                time.sleep(interval)
                continue

            pos_count, _ = collect_open_positions(mock=mock)

            for sym in symbols:
                tick = collect_tick(sym, mock=mock)
                bid_str = f"bid={tick['bid']}" if tick else "no tick"
                ask_str = f"ask={tick['ask']}" if tick else ""
                spr_str = f"spread={tick['spread_points']}pt" if tick else ""
                print(f"  {sym}: {bid_str} {ask_str} {spr_str} pos={pos_count}")
                write_log_row(writers[sym], files[sym], account, pos_count, tick or {})

            for _ in range(interval):
                if stop_flag[0]:
                    break
                time.sleep(1)

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        for f in files.values():
            f.close()
        shutdown_mt5()
        print("Collector stopped.")


def main():
    parser = argparse.ArgumentParser(description="Continuous execution log collector")
    parser.add_argument("--symbols", type=str,
                        default=",".join(SYMBOLS_DEFAULT),
                        help="Comma-separated symbols")
    parser.add_argument("--output", type=str, default=None,
                        help="Output directory (default: artifacts/live_logs)")
    parser.add_argument("--mode", type=str, choices=["snapshot", "continuous"],
                        default="snapshot",
                        help="snapshot=collect once, continuous=loop")
    parser.add_argument("--interval", type=int, default=60,
                        help="Seconds between collections (continuous mode)")
    parser.add_argument("--mock", action="store_true",
                        help="Use mock data (no MT5 connection needed)")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")]
    output_dir = args.output or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "artifacts", "live_logs",
    )

    os.makedirs(output_dir, exist_ok=True)

    if args.mock:
        print("[MOCK] Running in mock mode — no MT5 connection required")
    else:
        try:
            initialize_mt5(MT5_PATH, timeout=30000)
        except Mt5UnavailableError as e:
            print(f"FAIL_CONNECT: {e}")
            print("  Tip: Use --mock to run without MT5")
            sys.exit(1)

        for sym in symbols:
            mt5.symbol_select(sym, True)

        account = get_account_info()
        print(f"Account: {account.get('login')} Balance: ${account.get('balance'):,.2f}")

    print(f"Output: {output_dir}")

    if args.mode == "continuous":
        run_continuous(symbols, output_dir, args.interval, mock=args.mock)
    else:
        run_snapshot(symbols, output_dir, mock=args.mock)
        if not args.mock:
            shutdown_mt5()


if __name__ == "__main__":
    main()
