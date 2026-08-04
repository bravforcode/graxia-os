"""Bug #3 extension: research_approaches.py must derive dollar PnL from actual price level."""

import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from research_approaches import test_session_pattern as session_pattern  # noqa: E402


def _src():
    return (pathlib.Path(__file__).resolve().parents[1] / "scripts" / "research_approaches.py").read_text()


def test_no_hardcoded_2350_in_source():
    assert "2350" not in _src()


def _make_df(level):
    n = 300
    rng = np.random.RandomState(0)
    moves = rng.normal(0, 0.001, n)
    close = level * np.exp(np.cumsum(moves))  # same fractional moves at any level
    idx = pd.date_range("2024-01-01 08:00", periods=n, freq="h", tz="UTC")  # all bars in London session
    return pd.DataFrame({"close": close, "high": close * 1.001, "low": close * 0.999}, index=idx)


def test_net_scales_with_price_level():
    low = session_pattern(_make_df(1.10))["london"]
    high = session_pattern(_make_df(2350.0))["london"]
    assert low["trades"] == high["trades"] > 0
    ratio = high["net"] / low["net"]
    assert abs(ratio - 2350.0 / 1.10) < 1e-3  # net = trades.sum() * price_level