"""Phase 5 — Walk-forward validation engine."""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class WalkForwardFold:
    fold_index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    in_sample_metrics: dict
    out_of_sample_metrics: dict


def walk_forward_split(
    n_bars: int,
    n_folds: int = 5,
    train_ratio: float = 0.7,
    embargo_bars: int = 12,
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """Generate walk-forward train/test splits.

    Returns list of ((train_start, train_end), (test_start, test_end)).
    Embargo: gap between train_end and test_start to prevent leakage.
    """
    fold_size = n_bars // n_folds
    train_size = int(fold_size * train_ratio)

    splits = []
    for i in range(n_folds):
        fold_start = i * fold_size
        train_start = fold_start
        train_end = fold_start + train_size
        test_start = train_end + embargo_bars
        test_end = min(fold_start + fold_size, n_bars)

        if test_start < test_end:
            splits.append(((train_start, train_end), (test_start, test_end)))

    return splits


def evaluate_fold(
    train_data: tuple,
    test_data: tuple,
    strategy_fn: Callable,
    metrics_fn: Callable,
) -> WalkForwardFold:
    """Evaluate a single walk-forward fold."""
    train_metrics = metrics_fn(strategy_fn, train_data)
    test_metrics = metrics_fn(strategy_fn, test_data)

    return WalkForwardFold(
        fold_index=0,
        train_start=train_data[0],
        train_end=train_data[1],
        test_start=test_data[0],
        test_end=test_data[1],
        in_sample_metrics=train_metrics,
        out_of_sample_metrics=test_metrics,
    )
