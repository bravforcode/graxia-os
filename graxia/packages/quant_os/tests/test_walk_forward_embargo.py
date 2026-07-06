"""Regression test for BUG-005 (P0): scripts/walk_forward.py must insert a
purge/embargo gap between the training window and the test window so that
no autocorrelated/label-horizon information leaks from train into test.

Before the fix, `test_start` was implicitly `train_end` (zero gap), so the
last training labels (which look forward via target_return / triple-barrier
horizons) and the first test-window bars could reference overlapping data.

This test drives the real `walk_forward()` function end-to-end on a small
synthetic dataset and inspects the fold boundaries it reports, rather than
peeking at internals, so it protects against the gap silently regressing to
zero again in the future.
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from walk_forward import walk_forward  # noqa: E402


def _make_df(n: int, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="1min", tz="UTC")
    # close prices kept in (1000, 10000) to satisfy compute_fold_pnl's
    # unrelated price-sanity assertion (tuned for XAUUSD-style instruments).
    close = 2000 + np.cumsum(rng.normal(0, 0.1, n))
    df = pd.DataFrame(
        {
            "f1": rng.normal(0, 1, n),
            "f2": rng.normal(0, 1, n),
            "close": close,
            "target": rng.integers(0, 2, n),
            "target_return": rng.normal(0, 0.001, n),
        },
        index=idx,
    )
    return df


MODEL_PARAMS = {
    "n_estimators": 5,
    "max_depth": 2,
    "learning_rate": 0.1,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": 42,
    "eval_metric": "logloss",
    "use_label_encoder": False,
    "verbosity": 0,
}

FEATURE_COLS = ["f1", "f2"]


@pytest.mark.parametrize("purge_gap", [0, 5, 20])
def test_purge_gap_separates_train_and_test(purge_gap):
    """test_start must be >= train_end + purge_gap, and the train/test index
    ranges reported for every fold must not overlap at all."""
    n = 140
    df = _make_df(n)

    agg = walk_forward(
        df,
        FEATURE_COLS,
        MODEL_PARAMS,
        train_window=30,
        test_window=10,
        step=15,
        spread_cost=0.0,
        slippage_p90=0.0,
        min_confidence=0.0,
        min_expected_profit=-1.0,  # accept all trades so folds aren't empty
        purge_gap=purge_gap,
    )

    folds = agg["folds"]
    assert len(folds) > 0, "expected at least one fold for this window/purge_gap combo"
    assert agg["params"]["purge_gap"] == purge_gap

    for f in folds:
        train_end_pos = df.index.get_loc(pd.Timestamp(f["train_end"]))
        test_start_pos = df.index.get_loc(pd.Timestamp(f["test_start"]))
        test_end_pos = df.index.get_loc(pd.Timestamp(f["test_end"]))

        gap = test_start_pos - train_end_pos - 1  # bars strictly between train_end and test_start
        assert gap >= purge_gap, (
            f"fold {f['fold']}: gap={gap} bars between train_end and test_start, " f"expected >= purge_gap={purge_gap}"
        )

        # Train range [train_start, train_end] and test range [test_start, test_end]
        # must not overlap at all.
        train_start_pos = df.index.get_loc(pd.Timestamp(f["train_start"]))
        assert train_end_pos < test_start_pos
        assert test_start_pos > train_end_pos
        train_positions = set(range(train_start_pos, train_end_pos + 1))
        test_positions = set(range(test_start_pos, test_end_pos + 1))
        assert train_positions.isdisjoint(test_positions), f"fold {f['fold']}: train and test index ranges overlap"


def test_default_purge_gap_is_fourteen_bars():
    """Default purge_gap (no explicit override) must be 14 bars, matching the
    label horizons used elsewhere in this codebase (forward_bars=5 in
    create_target, max_bars~=12 for triple-barrier labels)."""
    n = 140
    df = _make_df(n, seed=1)

    agg = walk_forward(
        df,
        FEATURE_COLS,
        MODEL_PARAMS,
        train_window=30,
        test_window=10,
        step=15,
        spread_cost=0.0,
        slippage_p90=0.0,
        min_confidence=0.0,
        min_expected_profit=-1.0,
    )

    assert agg["params"]["purge_gap"] == 14
    f = agg["folds"][0]
    train_end_pos = df.index.get_loc(pd.Timestamp(f["train_end"]))
    test_start_pos = df.index.get_loc(pd.Timestamp(f["test_start"]))
    assert test_start_pos - train_end_pos - 1 == 14


def test_zero_folds_warns_instead_of_silently_returning_nothing(capsys):
    """If purge_gap + windows exceed available bars, walk_forward should print
    a clear warning rather than silently returning an empty result."""
    n = 40
    df = _make_df(n, seed=2)

    agg = walk_forward(
        df,
        FEATURE_COLS,
        MODEL_PARAMS,
        train_window=30,
        test_window=10,
        step=15,
        spread_cost=0.0,
        slippage_p90=0.0,
        purge_gap=14,
    )

    assert agg["folds"] == []
    captured = capsys.readouterr()
    assert "No folds generated" in captured.out
