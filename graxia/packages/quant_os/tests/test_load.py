import time, sys, os
from pathlib import Path
sys.path.insert(0, os.getcwd())
from graxia.packages.quant_os.backtest.data_loader import load_csv_data

data_dir = str(Path(__file__).parent.parent / "data")
fmt = "%Y-%m-%d %H:%M:%S"

t0 = time.time()
d1, ts1 = load_csv_data(os.path.join(data_dir, "XAUUSD_D1.csv"), date_column="time", date_format=fmt)
elapsed = time.time() - t0
print(f"D1: {len(d1['close'])} bars in {elapsed:.1f}s")

t0 = time.time()
h1, tsh1 = load_csv_data(os.path.join(data_dir, "XAUUSD_H1.csv"), date_column="time", date_format=fmt)
elapsed = time.time() - t0
print(f"H1: {len(h1['close'])} bars in {elapsed:.1f}s")

t0 = time.time()
m15, tsm15 = load_csv_data(os.path.join(data_dir, "XAUUSD_M15.csv"), date_column="time", date_format=fmt)
elapsed = time.time() - t0
print(f"M15: {len(m15['close'])} bars in {elapsed:.1f}s")

print("Loading OK")
