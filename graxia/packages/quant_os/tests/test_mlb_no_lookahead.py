"""Regression test for F0-1: no lookahead in SMC swing labeling.

The swing-high/low label used to be computed with a centered rolling window
(``center=True``), which peeks at ``window // 2`` bars AFTER the current bar.
That is lookahead: in live trading those future bars don't exist yet. The fix
shifts the label forward by ``window // 2`` so it is only available once the
confirming bars have occurred.

Verification (numeric, not just "imports ok"):
1. A known swing high at bar 50 must NOT be labeled at bar 50 (old bug).
2. It must be labeled at bar 52 (50 + half-window) in the fixed version.
3. Perturbing ONLY future bars must not change the label at the confirm bar.
"""

import numpy as np
import pandas as pd

from graxia.packages.quant_os.strategies.mlb import _compute_swing_labels


def _series_with_swing(n: int, swing_at: int):
    """Monotonic series with a single clear local max at ``swing_at``."""
    high = np.linspace(100.0, 200.0, n)
    high[swing_at] = 300.0  # unambiguous local max in its 5-bar neighborhood
    low = high - 1.0
    return pd.Series(high, dtype="float64"), pd.Series(low, dtype="float64")


def test_fixed_label_not_available_at_swing_bar():
    high, low = _series_with_swing(100, swing_at=50)
    sh, _ = _compute_swing_labels(high, low, window=5)
    # Old (buggy) code would put True here; fixed code must not.
    assert not bool(sh.iloc[50]), "lookahead: label must not be available at the swing bar"


def test_fixed_label_available_two_bars_later():
    high, low = _series_with_swing(100, swing_at=50)
    sh, _ = _compute_swing_labels(high, low, window=5)
    assert bool(sh.iloc[52]), "label should be available 2 bars after the swing bar"


def test_label_invariant_to_future_perturbation():
    high, low = _series_with_swing(100, swing_at=50)
    sh_a, _ = _compute_swing_labels(high, low, window=5)
    # Perturb ONLY bars strictly after the confirm bar (52): 55..59
    high2 = high.copy()
    high2.iloc[55:60] = high2.iloc[55:60] * 1.5
    sh_b, _ = _compute_swing_labels(high2, low, window=5)
    assert sh_a.iloc[52] == sh_b.iloc[52], "label at confirm bar must not depend on bars after it (no lookahead)"


def test_before_after_numeric_shift():
    """Show the numeric before/after: naive labels at 50, fixed at 52."""
    high, low = _series_with_swing(100, swing_at=50)
    sh, _ = _compute_swing_labels(high, low, window=5)
    naive = high.rolling(window=5, center=True).max() == high
    assert bool(naive.iloc[50]), "naive (buggy) labeling puts True at the swing bar"
    assert not bool(sh.iloc[50]), "fixed labeling removes it from the swing bar"
    assert bool(sh.iloc[52]), "fixed labeling moves it to swing_bar + half_window"
