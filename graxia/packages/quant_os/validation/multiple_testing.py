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


def deflated_sharpe_ratio(
    sharpe: float,
    n_trials: int,
    n_bars: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Compute the Deflated Sharpe Ratio (DSR).

    Accounts for multiple testing bias in Sharpe ratio estimates.
    A DSR < 0.5 suggests the observed Sharpe is likely due to
    selection bias rather than genuine alpha.

    Args:
        sharpe: Observed annualized Sharpe ratio.
        n_trials: Number of strategies tested (selection bias).
        n_bars: Number of observations used to compute Sharpe.
        skewness: Return skewness (default 0 = normal).
        kurtosis: Return kurtosis (default 3 = normal).

    Returns:
        Deflated Sharpe ratio (float). Interpretation:
        - DSR > 0.95: Strong evidence of genuine alpha
        - DSR 0.5-0.95: Moderate evidence
        - DSR < 0.5: Likely selection bias
    """
    from scipy.stats import norm

    if n_trials <= 0 or n_bars <= 0:
        return 0.0

    # Expected maximum Sharpe under null (order statistics of normal)
    e_max_sr = norm.ppf(1 - 1.0 / n_trials) if n_trials > 1 else 0.0

    # Sharpe ratio standard error (Opdyke 2007)
    sr_std = np.sqrt(
        (1 - skewness * sharpe + (kurtosis - 1) / 4 * sharpe**2)
        / (n_bars - 1)
    )

    if sr_std < 1e-10:
        return 0.0

    # DSR = probability that true SR > 0 given observed SR and selection
    dsr = norm.cdf((sharpe - e_max_sr) / sr_std)
    return float(dsr)
