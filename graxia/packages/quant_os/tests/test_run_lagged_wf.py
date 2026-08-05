"""Bug #3: run_lagged_wf.py must use actual price series, not a hardcoded constant."""

import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from run_lagged_wf import compute_features_lagged  # noqa: E402


def _src():
    return (pathlib.Path(__file__).resolve().parents[1] / "scripts" / "run_lagged_wf.py").read_text()


def test_no_hardcoded_price_constant_in_source():
    assert "2350.0" not in _src()


def test_compute_features_lagged_returns_aligned_price_series():
    n = 100
    close = 1.10 + np.cumsum(np.random.RandomState(0).normal(0, 0.0005, n))
    df = pd.DataFrame({"close": close})
    X, y, price = compute_features_lagged(df)
    assert len(X) == len(y) == len(price)
    # price must reflect the actual (EURUSD-scale ~1.1) series, not an XAUUSD-scale constant
    assert 0.5 < price.mean() < 2.0


if __name__ == "__main__":
    test_no_hardcoded_price_constant_in_source()
    test_compute_features_lagged_returns_aligned_price_series()
    print("OK")
