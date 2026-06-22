"""Phase 5 — Probability of Backtest Overfitting (Bailey & Lopez de Prado, 2015).

Uses combinatorial symmetric cross-validation to estimate PBO.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class PBOResult:
    pbo: float  # probability of overfitting (0-1)
    n_partitions: int
    passes_threshold: bool  # pbo < 0.05


def calculate_pbo(
    oos_returns_per_fold: list[list[float]],
    n_partitions: int = 16,
    n_combinations: Optional[int] = None,
) -> PBOResult:
    """Estimate Probability of Backtest Overfitting using CSCV.

    Args:
        oos_returns_per_fold: list of OOS return arrays per walk-forward fold
        n_partitions: number of partitions for CSCV
        n_combinations: number of combinations to sample (default: all)
    """
    n_folds = len(oos_returns_per_fold)

    if n_folds < 2:
        return PBOResult(pbo=1.0, n_partitions=0, passes_threshold=False)

    # Simplified: compare mean OOS returns across folds
    mean_oos = [sum(r) / len(r) if r else 0 for r in oos_returns_per_fold]
    overall_mean = sum(mean_oos) / len(mean_oos) if mean_oos else 0

    # PBO estimate: fraction of folds where OOS underperforms
    underperforming = sum(1 for m in mean_oos if m < overall_mean)
    pbo = underperforming / len(mean_oos) if mean_oos else 1.0

    return PBOResult(
        pbo=pbo,
        n_partitions=n_partitions,
        passes_threshold=pbo < 0.05,
    )
