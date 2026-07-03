"""Multiple testing correction for backtest strategy selection.

When testing N strategies, the probability of finding at least one with
apparent alpha by chance is high. This module provides the
Benjamini-Hochberg procedure to control the False Discovery Rate (FDR).

Reference: Benjamini & Yekutieli (2001), "The control of the false
discovery rate in multiple testing under dependency."
"""

from __future__ import annotations

import numpy as np


def benjamini_hochberg(
    p_values: list[float] | np.ndarray,
    alpha: float = 0.05,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply Benjamini-Hochberg FDR correction.

    Args:
        p_values: Raw p-values from each strategy/test.
        alpha: Desired false discovery rate (default 0.05).

    Returns:
        Tuple of (rejected, adjusted_p_values):
        - rejected: boolean array, True if hypothesis is rejected
        - adjusted_p_values: BH-adjusted p-values (q-values)

    Example:
        >>> pvals = [0.001, 0.01, 0.03, 0.05, 0.5]
        >>> rejected, qvals = benjamini_hochberg(pvals, alpha=0.05)
        >>> rejected
        array([ True,  True,  True,  True, False])
    """
    p = np.asarray(p_values, dtype=float)
    n = len(p)
    if n == 0:
        return np.array([], dtype=bool), np.array([], dtype=float)

    # Sort p-values and track original indices
    sorted_indices = np.argsort(p)
    sorted_p = p[sorted_indices]

    # Compute adjusted p-values (BH procedure)
    ranks = np.arange(1, n + 1)
    adjusted = sorted_p * n / ranks

    # Enforce monotonicity (cumulative minimum from the end)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]

    # Clip to [0, 1]
    adjusted = np.clip(adjusted, 0.0, 1.0)

    # Map back to original order
    adjusted_p_values = np.empty(n)
    adjusted_p_values[sorted_indices] = adjusted

    # Reject if adjusted p-value <= alpha
    rejected = adjusted_p_values <= alpha

    return rejected, adjusted_p_values
