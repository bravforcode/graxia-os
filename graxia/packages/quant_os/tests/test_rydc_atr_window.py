"""RYDC ATR alignment: validation ATR window must include the current (entry) bar,
matching the live strategy's close[-atr_period:] semantics."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from run_rydc_validation import _atr_window  # noqa: E402


def _data(n=100):
    return [
        {"xau_high": 100.0 + j, "xau_low": 99.0 + j, "xau_close": 99.5 + j}
        for j in range(n)
    ]


def test_atr_window_includes_current_bar():
    highs, lows, closes = _atr_window(_data(), 80, 14)
    assert len(closes) == 14
    assert closes[-1] == 99.5 + 80   # bar 80 (entry bar) included
    assert highs[-1] == 100.0 + 80
    assert lows[-1] == 99.0 + 80


def test_atr_window_early_bars_use_min_window():
    highs, lows, closes = _atr_window(_data(), 5, 14)
    assert len(closes) == 6          # min(14, i+1) bars [0..5]
    assert closes[0] == 99.5         # bar 0
    assert closes[-1] == 99.5 + 5    # bar 5 (current bar) included
