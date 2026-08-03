"""Shared Population Stability Index (PSI) primitive.

Extracted from ``ml/drift_monitor.py::DriftMonitor._calculate_psi`` (Phase 1,
2026-08-03) so the ML feature-drift check and the cost-drift demote check share
one statistical implementation. The math must stay identical to the original:
same bin edges, same 1e-10 probability floor, same erf-based normal CDF.
"""

from __future__ import annotations

import math


def psi(
    *,
    baseline_mean: float,
    baseline_std: float,
    current_mean: float,
    current_std: float,
    n_bins: int = 10,
) -> float:
    """Compute PSI between two normal distributions approximated by bins.

    Uses baseline mean/std to define bins, then computes the divergence
    between the baseline and current distributions.
    """
    # Define bin edges from baseline distribution
    lo = baseline_mean - 3 * baseline_std
    hi = baseline_mean + 3 * baseline_std
    edges = [lo + (hi - lo) * i / n_bins for i in range(n_bins + 1)]

    def _normal_cdf(x: float, mu: float, sigma: float) -> float:
        """Approximate normal CDF using error function."""
        return 0.5 * (1 + math.erf((x - mu) / (sigma * math.sqrt(2))))

    def _bin_probs(mu: float, sigma: float) -> list[float]:
        probs = []
        for i in range(n_bins):
            p = _normal_cdf(edges[i + 1], mu, sigma) - _normal_cdf(edges[i], mu, sigma)
            probs.append(max(p, 1e-10))
        return probs

    baseline_probs = _bin_probs(baseline_mean, baseline_std)
    current_probs = _bin_probs(current_mean, current_std)

    psi_value = 0.0
    for bp, cp in zip(baseline_probs, current_probs, strict=False):
        psi_value += (cp - bp) * math.log(cp / bp)
    return psi_value
