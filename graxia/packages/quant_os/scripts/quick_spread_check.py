#!/usr/bin/env python3
"""Quick spread check for XPDUSD and XPTUSD on Pepperstone MT5."""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import MetaTrader5 as mt5

MT5_PATH = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"
SYMBOLS = ["XPDUSD", "XPTUSD"]

def main():
    print("[INIT] Connecting to MT5...")
    if not mt5.initialize(path=MT5_PATH, timeout=30000):
        err = mt5.last_error()
        print(f"[FATAL] MT5 connection failed: {err}")
        sys.exit(1)
    print("[INIT] MT5 connected.\n")

    results = {}
    for sym in SYMBOLS:
        if not mt5.symbol_select(sym, True):
            print(f"[WARN] Cannot select {sym}: {mt5.last_error()}")
            continue

        info = mt5.symbol_info(sym)
        tick = mt5.symbol_info_tick(sym)
        if info is None or tick is None:
            print(f"[WARN] No info/tick for {sym}")
            continue

        bid = tick.bid
        ask = tick.ask
        mid = (bid + ask) / 2.0
        spread_price = ask - bid
        spread_bps = (spread_price / mid * 10000) if mid > 0 else 0.0

        results[sym] = {
            "bid": round(bid, info.digits),
            "ask": round(ask, info.digits),
            "mid": round(mid, info.digits),
            "spread_price": round(spread_price, info.digits),
            "spread_bps": round(spread_bps, 2),
            "point": info.point,
            "digits": info.digits,
            "contract_size": info.trade_contract_size,
            "volume_min": info.volume_min,
            "volume_step": info.volume_step,
        }

        print(f"=== {sym} ===")
        print(f"  Bid:          {bid:.{info.digits}f}")
        print(f"  Ask:          {ask:.{info.digits}f}")
        print(f"  Mid:          {mid:.{info.digits}f}")
        print(f"  Spread Price: {spread_price:.{info.digits}f}")
        print(f"  Spread BPS:   {spread_bps:.2f}")
        print(f"  Point:        {info.point}")
        print(f"  Digits:       {info.digits}")
        print(f"  Contract:     {info.trade_contract_size}")
        print(f"  Min Volume:   {info.volume_min}")
        print(f"  Volume Step:  {info.volume_step}")
        print()

    mt5.shutdown()
    print("[DONE] MT5 shutdown.")

    # Estimate round-trip costs
    print("\n=== ROUND-TRIP COST ESTIMATE (no commission on metals) ===")
    for sym, r in results.items():
        rt_bps = r["spread_bps"] * 2  # Round-trip = 2 × measured spread (no commission on metals)
        print(f"  {sym}: spread={r['spread_bps']:.2f} bps, est RT={rt_bps:.2f} bps")

if __name__ == "__main__":
    main()
