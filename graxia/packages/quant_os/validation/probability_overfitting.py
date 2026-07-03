"""Phase 5 — Probability of Backtest Overfitting (Bailey & Lopez de Prado, 2015).

Uses combinatorial symmetric cross-validation (CSCV) to estimate PBO.

CORRECT CSCV Procedure (strategy-matrix approach):
1. Build a strategy matrix: N configs × S time periods, cells = returns.
2. Split S time periods into two equal halves.
3. For each C(S, S/2) combination, use half as IS and half as OOS.
4. Find the best IS strategy (highest Sharpe), check its OOS rank.
5. PBO = fraction of combinations where the IS-best strategy ranks in the
   bottom half OOS (i.e., overfitting).

DEPRECATED legacy mode: when only oos_returns_per_fold is provided (no strategy
matrix), the old time-partition heuristic is used with a deprecation warning.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from itertools import combinations
from math import comb


@dataclass
class PBOResult:
    pbo: float  # probability of overfitting (0-1)
    n_partitions: int
    n_combinations_tested: int
    passes_threshold: bool  # pbo < 0.05


def _sharpe(returns: list[float]) -> float:
    """Compute annualized Sharpe from a return series (simple)."""
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    if std == 0:
        return 0.0
    return mean / std


def _concat_sharpe(returns_list: list[list[float]]) -> float:
    """Compute Sharpe from concatenated returns across multiple periods."""
    combined: list[float] = []
    for r in returns_list:
        combined.extend(r)
    return _sharpe(combined)


# ──────────────────────────────────────────────────────────────────────────────
# CORRECT CSCV: strategy-matrix approach
# ──────────────────────────────────────────────────────────────────────────────


def calculate_pbo_from_matrix(
    strategy_returns: dict[str, list[list[float]]],
    n_combinations: int | None = None,
) -> PBOResult:
    """Estimate PBO using the correct CSCV algorithm with a strategy matrix.

    Args:
        strategy_returns: dict mapping config_id -> list of per-period return
            arrays.  Each config_id represents one strategy configuration
            (e.g. from a parameter sweep).  Each element in the list is one
            time period's returns for that config.
            Example: {"ema10": [[r1,r2,...], [r3,r4,...]], "ema20": [...]}
        n_combinations: max C(S,S/2) combinations to test (default: all, cap512).

    Returns:
        PBOResult with the probability of backtest overfitting.
    """
    config_ids = list(strategy_returns.keys())
    n_configs = len(config_ids)

    if n_configs < 2:
        return PBOResult(pbo=1.0, n_partitions=0, n_combinations_tested=0, passes_threshold=False)

    # Determine number of time periods (must be same for all configs)
    n_periods = len(strategy_returns[config_ids[0]])
    if n_periods < 2:
        return PBOResult(pbo=1.0, n_partitions=0, n_combinations_tested=0, passes_threshold=False)

    # Validate all configs have same number of periods
    for cid in config_ids:
        if len(strategy_returns[cid]) != n_periods:
            return PBOResult(pbo=1.0, n_partitions=0, n_combinations_tested=0, passes_threshold=False)

    half = n_periods // 2
    if half == 0:
        return PBOResult(pbo=1.0, n_partitions=n_periods, n_combinations_tested=0, passes_threshold=False)

    # ── Enumerate C(S, S/2) combinations ─────────────────────────────────
    total_combos = comb(n_periods, half)
    max_combos = n_combinations or min(total_combos, 512)
    period_indices = list(range(n_periods))
    combo_iter = combinations(period_indices, half)

    overfit_count = 0
    tested = 0

    for is_indices in combo_iter:
        if tested >= max_combos:
            break
        oos_indices = [i for i in period_indices if i not in is_indices]

        # Compute per-config Sharpe on IS and OOS periods
        is_sharpes: dict[str, float] = {}
        oos_sharpes: dict[str, float] = {}

        for cid in config_ids:
            is_returns = [strategy_returns[cid][p] for p in is_indices]
            oos_returns = [strategy_returns[cid][p] for p in oos_indices]
            is_sharpes[cid] = _concat_sharpe(is_returns)
            oos_sharpes[cid] = _concat_sharpe(oos_returns)

        if not is_sharpes or not oos_sharpes:
            continue

        # Find the IS-best config
        best_is_id = max(is_sharpes, key=is_sharpes.get)  # type: ignore[arg-type]
        best_is_oos_sharpe = oos_sharpes[best_is_id]

        # Rank: fraction of OOS configs that beat IS-best
        n_better = sum(1 for s in oos_sharpes.values() if s > best_is_oos_sharpe)
        rank_fraction = n_better / len(oos_sharpes) if oos_sharpes else 1.0

        # Overfit if IS-best is in bottom 50% of OOS rankings
        if rank_fraction >= 0.5:
            overfit_count += 1

        tested += 1

    pbo = overfit_count / tested if tested > 0 else 1.0

    return PBOResult(
        pbo=round(pbo, 6),
        n_partitions=n_periods,
        n_combinations_tested=tested,
        passes_threshold=pbo < 0.05,
    )


# ──────────────────────────────────────────────────────────────────────────────
# DEPRECATED legacy mode: time-partition heuristic
# ──────────────────────────────────────────────────────────────────────────────


def calculate_pbo(
    oos_returns_per_fold: list[list[float]],
    n_partitions: int = 16,
    n_combinations: int | None = None,
) -> PBOResult:
    """Estimate PBO using the legacy time-partition heuristic.

    DEPRECATED: This method treats time partitions as "strategies", which tests
    temporal stability rather than overfitting. Use calculate_pbo_from_matrix()
    with a proper strategy matrix instead.

    Args:
        oos_returns_per_fold: list of OOS return arrays per walk-forward fold.
        n_partitions: number of time partitions for CSCV.
        n_combinations: max combinations to sample (default: all C(S, S/2), cap512).
    """
    warnings.warn(
        "calculate_pbo() with oos_returns_per_fold is deprecated. "
        "Use calculate_pbo_from_matrix() with a proper strategy matrix instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    n_folds = len(oos_returns_per_fold)

    if n_folds < 2:
        return PBOResult(pbo=1.0, n_partitions=0, n_combinations_tested=0, passes_threshold=False)

    # ── Step 1: flatten all OOS returns into a single series ──────────
    all_returns: list[float] = []
    for fold_returns in oos_returns_per_fold:
        all_returns.extend(fold_returns)

    if len(all_returns) < n_partitions:
        return PBOResult(pbo=1.0, n_partitions=n_partitions, n_combinations_tested=0, passes_threshold=False)

    # ── Step 2: split into S equal partitions ─────────────────────────
    chunk_size = len(all_returns) // n_partitions
    partitions = []
    for i in range(n_partitions):
        start = i * chunk_size
        end = start + chunk_size if i < n_partitions - 1 else len(all_returns)
        partitions.append(all_returns[start:end])

    half = n_partitions // 2
    if half == 0:
        return PBOResult(pbo=1.0, n_partitions=n_partitions, n_combinations_tested=0, passes_threshold=False)

    # ── Step 3: enumerate C(S, S/2) combinations ─────────────────────
    total_combos = comb(n_partitions, half)
    max_combos = n_combinations or min(total_combos, 512)
    indices = list(range(n_partitions))
    combo_iter = combinations(indices, half)

    overfit_count = 0
    tested = 0

    for is_indices in combo_iter:
        if tested >= max_combos:
            break
        oos_indices = [i for i in indices if i not in is_indices]

        is_sharpes = {}
        oos_sharpes = {}
        for idx in is_indices:
            is_sharpes[idx] = _sharpe(partitions[idx])
        for idx in oos_indices:
            oos_sharpes[idx] = _sharpe(partitions[idx])

        if not is_sharpes or not oos_sharpes:
            continue

        best_is_idx = max(is_sharpes, key=is_sharpes.get)  # type: ignore[arg-type]
        oos_sorted = sorted(oos_sharpes.values(), reverse=True)
        best_is_oos_sharpe = _sharpe(partitions[best_is_idx])

        n_better = sum(1 for s in oos_sharpes.values() if s > best_is_oos_sharpe)
        rank_fraction = n_better / len(oos_sharpes) if oos_sharpes else 1.0

        if rank_fraction >= 0.5:
            overfit_count += 1

        tested += 1

    pbo = overfit_count / tested if tested > 0 else 1.0

    return PBOResult(
        pbo=round(pbo, 6),
        n_partitions=n_partitions,
        n_combinations_tested=tested,
        passes_threshold=pbo < 0.05,
    )
