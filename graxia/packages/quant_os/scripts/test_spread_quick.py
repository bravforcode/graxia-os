"""Quick spread measurement - runs for 5 minutes to verify system works."""
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import MetaTrader5 as mt5

MT5_PATH = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"
OUTPUT_FILE = Path(__file__).parent.parent / "data" / "spread_log.jsonl"
SYMBOLS = ["XAUUSD"]

def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    if not mt5.initialize(path=MT5_PATH, timeout=30000):
        print(f"FATAL: MT5 init failed: {mt5.last_error()}")
        return
    
    print(f"MT5 connected. Testing {SYMBOLS}...")
    
    for sym in SYMBOLS:
        mt5.symbol_select(sym, True)
    
    # Take 5 samples (60s apart = 5 minutes)
    for i in range(5):
        for sym in SYMBOLS:
            tick = mt5.symbol_info_tick(sym)
            info = mt5.symbol_info(sym)
            if tick is None or info is None:
                print(f"  [{i+1}/5] {sym}: tick=None")
                continue
            mid = (tick.bid + tick.ask) / 2
            spread_bps = (tick.ask - tick.bid) / mid * 10000 if mid > 0 else 0
            sample = {
                "timestamp": datetime.now(UTC).isoformat(),
                "symbol": sym,
                "bid": round(tick.bid, info.digits),
                "ask": round(tick.ask, info.digits),
                "spread_bps": round(spread_bps, 2),
            }
            with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(sample) + "\n")
            print(f"  [{i+1}/5] {sym}: bid={tick.bid} ask={tick.ask} spread={spread_bps:.2f}bps")
        
        if i < 4:
            print(f"  Sleeping 60s...")
            time.sleep(60)
    
    mt5.shutdown()
    print(f"DONE. Output: {OUTPUT_FILE}")
    print(f"Samples written: {i+1}")

if __name__ == "__main__":
    main()
