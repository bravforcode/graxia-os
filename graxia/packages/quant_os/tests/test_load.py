import time, sys, os
sys.path.insert(0, os.getcwd())
from graxia.packages.quant_os.backtest.data_loader import load_csv_data

data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
fmt = "%Y-%m-%d %H:%M:%S"

xau_d1 = os.path.join(data_dir, "XAUUSD_D1.csv")
if not os.path.exists(xau_d1):
    raise ImportError(f"Data file not found: {xau_d1}")

t0 = time.time()
d1, ts1 = load_csv_data(xau_d1, date_column="time", date_format=fmt)
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
