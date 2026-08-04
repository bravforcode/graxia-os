"""Bug #3 extension: wf_patched.py must derive dollar PnL from actual price level."""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from wf_patched import compute_fold_pnl  # noqa: E402


def _src():
    return (pathlib.Path(__file__).resolve().parents[1] / "scripts" / "wf_patched.py").read_text()


def test_no_hardcoded_2350_in_source():
    assert "2350.0" not in _src()


def test_compute_fold_pnl_scales_with_price_level():
    rng = np.random.RandomState(0)
    n = 100
    returns = rng.normal(0, 0.001, n)
    preds = rng.randint(0, 3, n)          # 3-class TB labels: 0/1/2
    confs = rng.uniform(0.8, 1.0, n)
    kwargs = dict(spread_cost=1e-5, slippage_p90=1e-5, min_confidence=0.85)
    low = compute_fold_pnl(returns, preds, confs, price_level=1.10, **kwargs)
    high = compute_fold_pnl(returns, preds, confs, price_level=2350.0, **kwargs)
    assert low["n_trades"] == high["n_trades"] > 0
    assert abs(high["gross_pnl"] / low["gross_pnl"] - 2350.0 / 1.10) < 1e-3
    assert abs(high["total_cost"] / low["total_cost"] - 2350.0 / 1.10) < 1e-3
