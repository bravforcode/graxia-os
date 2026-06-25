"""Load test: measure data loading throughput."""
import time
import os
import pytest


@pytest.fixture(scope="module")
def csv_paths():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    return {
        "d1": os.path.join(data_dir, "XAUUSD_D1.csv"),
        "h1": os.path.join(data_dir, "XAUUSD_H1.csv"),
        "m15": os.path.join(data_dir, "XAUUSD_M15.csv"),
    }


def test_load_d1(csv_paths):
    from graxia.packages.quant_os.backtest.data_loader import load_csv_data

    assert os.path.exists(csv_paths["d1"]), f"Data file not found: {csv_paths['d1']}"
    fmt = "%Y-%m-%d %H:%M:%S"
    t0 = time.time()
    d1, ts1 = load_csv_data(csv_paths["d1"], date_column="time", date_format=fmt)
    elapsed = time.time() - t0
    assert len(d1["close"]) > 0, "D1 should have bars"
    assert elapsed < 60.0, f"D1 loading too slow: {elapsed:.1f}s"


def test_load_h1(csv_paths):
    from graxia.packages.quant_os.backtest.data_loader import load_csv_data

    assert os.path.exists(csv_paths["h1"]), f"Data file not found: {csv_paths['h1']}"
    fmt = "%Y-%m-%d %H:%M:%S"
    t0 = time.time()
    h1, tsh1 = load_csv_data(csv_paths["h1"], date_column="time", date_format=fmt)
    elapsed = time.time() - t0
    assert len(h1["close"]) > 0, "H1 should have bars"
    assert elapsed < 60.0, f"H1 loading too slow: {elapsed:.1f}s"


def test_load_m15(csv_paths):
    from graxia.packages.quant_os.backtest.data_loader import load_csv_data

    assert os.path.exists(csv_paths["m15"]), f"Data file not found: {csv_paths['m15']}"
    fmt = "%Y-%m-%d %H:%M:%S"
    t0 = time.time()
    m15, tsm15 = load_csv_data(csv_paths["m15"], date_column="time", date_format=fmt)
    elapsed = time.time() - t0
    assert len(m15["close"]) > 0, "M15 should have bars"
    assert elapsed < 60.0, f"M15 loading too slow: {elapsed:.1f}s"
