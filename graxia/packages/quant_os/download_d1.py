import MetaTrader5 as mt5
import csv, os
from datetime import datetime

PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
DATA_DIR = os.path.join("graxia", "packages", "quant_os", "data")

mt5.initialize(PATH)
mt5.symbol_select("XAUUSD", True)

print("Downloading D1...")
rates = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_D1, 0, 5000)
print(f"  Got {len(rates)} bars")

out = os.path.join(DATA_DIR, "XAUUSD_D1.csv")
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["time", "open", "high", "low", "close", "volume"])
    for r in rates:
        ts = datetime.fromtimestamp(r["time"]).strftime("%Y-%m-%d %H:%M:%S")
        w.writerow([ts, r["open"], r["high"], r["low"], r["close"], r["tick_volume"]])

first = datetime.fromtimestamp(rates[0]["time"])
last = datetime.fromtimestamp(rates[-1]["time"])
print(f"  Range: {first} to {last}")
print("D1 done")
mt5.shutdown()
