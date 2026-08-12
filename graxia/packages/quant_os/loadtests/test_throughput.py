"""
Load test — measure data pipeline throughput.

Usage:
    python loadtests/test_throughput.py
"""
import time
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from graxia.packages.quant_os.backtest.data_loader import load_csv_data

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
FMT = "%Y-%m-%d %H:%M:%S"
TARGET_LOADS = {"XAUUSD_D1.csv": 1.0, "XAUUSD_H1.csv": 2.0, "XAUUSD_M15.csv": 3.0}


def run():
    results = {}
    for fname, max_sec in TARGET_LOADS.items():
        path = os.path.join(DATA_DIR, fname)
        t0 = time.time()
        data, ts = load_csv_data(path, date_column="time", date_format=FMT)
        elapsed = time.time() - t0
        results[fname] = {"rows": len(data["close"]), "elapsed_s": round(elapsed, 2), "target_s": max_sec}
        status = "PASS" if elapsed < max_sec else "FAIL"
        print(f"  {status} {fname}: {len(data['close'])} rows in {elapsed:.2f}s (target <{max_sec}s)")
    return results


if __name__ == "__main__":
    run()
