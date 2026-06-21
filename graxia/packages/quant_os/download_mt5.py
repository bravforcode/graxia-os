"""Download XAUUSD multi-TF data from MT5 terminal."""
import MetaTrader5 as mt5
import csv
import os
from datetime import datetime

PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
DATA_DIR = os.path.join("graxia", "packages", "quant_os", "data")

mt5.initialize(PATH)
mt5.symbol_select("XAUUSD", True)

TF_MAP = {
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
    "D1": mt5.TIMEFRAME_D1,
}

for tf_name, tf_const in TF_MAP.items():
    print(f"Downloading XAUUSD {tf_name}...")
    rates = mt5.copy_rates_from_pos("XAUUSD", tf_const, 0, 50000)
    if rates is None:
        print(f"  ERROR: {mt5.last_error()}")
        continue
    
    print(f"  Got {len(rates)} bars")
    
    # Convert to CSV
    out_path = os.path.join(DATA_DIR, f"XAUUSD_{tf_name}.csv")
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "open", "high", "low", "close", "volume"])
        for r in rates:
            ts = datetime.fromtimestamp(r["time"]).strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow([ts, r["open"], r["high"], r["low"], r["close"], r["tick_volume"]])
    
    # Show date range
    first = datetime.fromtimestamp(rates[0]["time"])
    last = datetime.fromtimestamp(rates[-1]["time"])
    print(f"  Range: {first} to {last}")
    print(f"  Saved: {out_path}")

mt5.shutdown()
print("Done.")
