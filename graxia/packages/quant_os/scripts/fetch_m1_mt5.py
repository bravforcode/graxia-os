"""
Fetch 6+ months M1 data from MT5 for all instruments.
Uses batch fetching (max 50K per call).
"""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from pathlib import Path

PATH = r'C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe'
DATA_DIR = Path(__file__).parent.parent / "data"
BATCH_SIZE = 50000
TARGET_BARS = 260000  # ~6 months of M1

INSTRUMENTS = [
    "AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY",
    "XAUUSD", "XAGUSD", "NAS100", "US30",
]

def fetch_all_m1(symbol, target=TARGET_BARS):
    """Fetch M1 data in batches."""
    all_rates = []
    offset = 0
    
    while offset < target:
        batch = min(BATCH_SIZE, target - offset)
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, offset, batch)
        if rates is None or len(rates) == 0:
            break
        all_rates.append(rates)
        offset += len(rates)
        if len(rates) < batch:
            break  # No more data
    
    if not all_rates:
        return None
    
    return np.concatenate(all_rates)

def main():
    if not mt5.initialize(PATH):
        print("MT5 init failed:", mt5.last_error())
        return
    
    acc = mt5.account_info()
    print("Connected: " + str(acc.login) + " @ " + acc.server)
    
    for symbol in INSTRUMENTS:
        print("\n--- " + symbol + " ---")
        
        info = mt5.symbol_info(symbol)
        if info is None:
            print("  Not found")
            continue
        
        mt5.symbol_select(symbol, True)
        
        rates = fetch_all_m1(symbol)
        if rates is None:
            print("  No data: " + str(mt5.last_error()))
            continue
        
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df = df.rename(columns={'time': 'timestamp', 'tick_volume': 'volume'})
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        
        first_date = df['timestamp'].iloc[0].strftime('%Y-%m-%d')
        last_date = df['timestamp'].iloc[-1].strftime('%Y-%m-%d')
        days = (df['timestamp'].iloc[-1] - df['timestamp'].iloc[0]).days
        
        print("  Bars: " + str(len(df)))
        print("  Range: " + first_date + " to " + last_date + " (" + str(days) + " days)")
        
        out_path = DATA_DIR / (symbol + "_M1.csv")
        df.to_csv(out_path, index=False)
        print("  Saved: " + out_path.name)
    
    mt5.shutdown()
    print("\nDone!")

if __name__ == "__main__":
    main()
