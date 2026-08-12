"""Probe MT5 market depth (DOM) for given symbols."""
import argparse
import sys
import time

import MetaTrader5 as mt5

MT5_PATH = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"


def probe_depth(symbol: str, label: str) -> bool:
    mt5.symbol_select(symbol, True)
    time.sleep(0.5)

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"  [{label}] No tick data — skipping")
        return False

    # Subscribe to market book (depth of market)
    sub_ok = mt5.market_book_add(symbol)
    print(f"  [{label}] market_book_add -> {sub_ok}")

    # Wait for depth data to arrive
    depth = None
    for i in range(10):
        time.sleep(0.5)
        depth = mt5.market_book_get(symbol)
        if depth is not None and len(depth) > 0:
            print(f"  [{label}] Depth arrived after ~{(i+1)*0.5:.1f}s ({len(depth)} entries)")
            break

    if depth is None:
        print(f"  [{label}] Depth unavailable (empty DOM / no market book support)")
        mt5.market_book_release(symbol)
        return False

    if len(depth) == 0:
        print(f"  [{label}] market_book_get returned empty list")
        mt5.market_book_release(symbol)
        return False

    # Separate bids and asks
    bids = [d for d in depth if d.type == 1]  # BOOK_TYPE_SELL == 1 (bid side)
    asks = [d for d in depth if d.type == 2]  # BOOK_TYPE_BUY == 2 (ask side)

    if not bids and not asks:
        print(f"  [{label}] Depth entries present but no bid/ask types found")
        mt5.market_book_release(symbol)
        return False

    print(f"  [{label}] Bid levels: {len(bids)}, Ask levels: {len(asks)}")

    top_bids = sorted(bids, key=lambda x: x.price, reverse=True)[:10]
    top_asks = sorted(asks, key=lambda x: x.price)[:10]

    print(f"  [{label}] Top 10 Bids:")
    for i, b in enumerate(top_bids):
        print(f"    {i+1:2d}. price={b.price:.5f}  volume={b.volume:.2f}")

    print(f"  [{label}] Top 10 Asks:")
    for i, a in enumerate(top_asks):
        print(f"    {i+1:2d}. price={a.price:.5f}  volume={a.volume:.2f}")

    mt5.market_book_release(symbol)
    return True


def main():
    parser = argparse.ArgumentParser(description="Check MT5 order book depth")
    parser.add_argument(
        "--symbols",
        default="XAUUSD,EURUSD,GBPUSD",
        help="Comma-separated symbols to probe",
    )
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        print("No symbols provided.")
        sys.exit(1)

    res = mt5.initialize(path=MT5_PATH, timeout=30000)
    if not res:
        print("MT5 init FAILED:", mt5.last_error())
        sys.exit(1)

    print(f"Connected: {mt5.account_info().login}@{mt5.account_info().server}")
    print(f"Probing symbols: {symbols}\n")

    available = 0
    for sym in symbols:
        ok = probe_depth(sym, sym)
        if ok:
            available += 1
        print()

    print(f"Depth available for {available}/{len(symbols)} symbols")

    depth_any = available > 0
    suffix = "HAS depth data" if depth_any else "NO depth data (demo limitation)"
    print(f"\nVerdict: {suffix}")

    mt5.shutdown()


if __name__ == "__main__":
    main()
