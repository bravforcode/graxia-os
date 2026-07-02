"""Phase 5 — Probability of Backtest Overfitting (Bailey & Lopez de Prado, 2015).

Uses combinatorial symmetric cross-validation (CSCV) to estimate PBO.

CSCV Procedure:
1. Split OOS returns into S partitions.
2. For each C(S, S/2) combination, use half as IS selection set and half as OOS.
3. Find the best IS strategy (highest Sharpe), check its OOS rank.
4. PBO = fraction of combinations where the IS-best strategy ranks in the
   bottom half OOS (i.e., overfitting).
"""

import math
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


def calculate_pbo(
    oos_returns_per_fold: list[list[float]],
    n_partitions: int = 16,
    n_combinations: int | None = None,
) -> PBOResult:
    """Estimate Probability of Backtest Overfitting using CSCV.

    Args:
        oos_returns_per_fold: list of OOS return arrays per walk-forward fold.
            Each element is one fold's OOS returns.
        n_partitions: number of partitions for CSCV.  Partitions are built by
            concatenating all fold returns then splitting into S equal chunks.
        n_combinations: max combinations to sample (default: all C(S, S/2)).
            Caps at 512 for performance.
    """
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

        # Compute per-strategy Sharpe: each partition is a "strategy"
        # IS: rank partitions by their Sharpe on IS set, pick best
        # OOS: check if best-IS also wins on OOS

        is_sharpes = {}
        oos_sharpes = {}
        for idx in is_indices:
            is_sharpes[idx] = _sharpe(partitions[idx])
        for idx in oos_indices:
            oos_sharpes[idx] = _sharpe(partitions[idx])

        if not is_sharpes or not oos_sharpes:
            continue

        # Find the IS-best partition
        best_is_idx = max(is_sharpes, key=is_sharpes.get)  # type: ignore[arg-type]

        # Check: does the IS-best rank in the bottom half of OOS?
        oos_sorted = sorted(oos_sharpes.values(), reverse=True)
        best_is_oos_sharpe = _sharpe(partitions[best_is_idx])

        # Relative rank: fraction of OOS strategies that beat IS-best
        n_better = sum(1 for s in oos_sharpes.values() if s > best_is_oos_sharpe)
        rank_fraction = n_better / len(oos_sharpes) if oos_sharpes else 1.0

        # Overfit if IS-best is in bottom 50% of OOS rankings
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
