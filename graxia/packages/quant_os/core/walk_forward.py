"""Unified walk-forward validation interface.

Single import point for all walk-forward functionality.
Re-exports from validation.walk_forward (canonical) and
core.cross_validation (CPCV variant).

Usage:
    from core.walk_forward import (
        walk_forward_split,       # multi-fold splits
        purged_cv,                # purged CV generator
        simple_train_test_split,  # single 80/20 split
        sliding_window_splits,    # sliding window with purge/embargo
        run_walk_forward,         # full XGBoost walk-forward
        compute_fold_pnl,         # single fold P&L
        evaluate_fold,            # generic fold evaluator
        WalkForwardFold,
        WalkForwardResult,
    )
"""

from validation.walk_forward import (
    WalkForwardFold,
    WalkForwardResult,
    compute_fold_pnl,
    evaluate_fold,
    infer_bars_per_year,
    purged_cv,
    run_walk_forward,
    simple_train_test_split,
    sliding_window_splits,
    walk_forward_split,
)

# CPCV variant — kept in core/cross_validation.py (separate concern)
try:
    from core.cross_validation import (
        CPCVFoldResult,
        CPCVResult,
        combine_purged_k_fold_cv,
        cpcv_groups,
        walk_forward_cpcv,
    )
except ImportError:
    pass

__all__ = [
    "WalkForwardFold",
    "WalkForwardResult",
    "walk_forward_split",
    "purged_cv",
    "simple_train_test_split",
    "sliding_window_splits",
    "run_walk_forward",
    "compute_fold_pnl",
    "evaluate_fold",
    "infer_bars_per_year",
    # CPCV (if available)
    "CPCVResult",
    "CPCVFoldResult",
    "walk_forward_cpcv",
    "combine_purged_k_fold_cv",
    "cpcv_groups",
]
