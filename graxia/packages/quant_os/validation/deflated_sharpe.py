"""Phase 5 — Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014).

Adjusts Sharpe ratio for multiple testing bias.
"""
import math
from dataclasses import dataclass


@dataclass
class DeflatedSharpeResult:
    observed_sharpe: float
    deflated_sharpe: float
    probability_alpha: float  # probability of false positive
    multiple_testing_adjustment: float
    passes_threshold: bool  # deflated_sharpe > 0 and prob_alpha < 0.05


def _norm_cdf(x: float) -> float:
    """Standard normal CDF approximation (ponytail: no scipy dependency)."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_ppf(p: float) -> float:
    """Standard normal inverse CDF approximation."""
    if p <= 0:
        return -10.0
    if p >= 1:
        return 10.0
    if p < 0.5:
        return -_norm_ppf(1 - p)

    t = math.sqrt(-2 * math.log(1 - p))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    return t - (c0 + c1 * t + c2 * t * t) / (1 + d1 * t + d2 * t * t + d3 * t * t * t)


def deflated_sharpe_ratio(
    observed_sharpe: float,
    n_trials: int,
    n_observations: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    confidence_level: float = 0.95,
) -> DeflatedSharpeResult:
    """Calculate deflated Sharpe ratio.

    Args:
        observed_sharpe: Sharpe ratio from backtest
        n_trials: number of strategy trials (multiple testing)
        n_observations: number of return observations
        skewness: return distribution skewness
        kurtosis: return distribution excess kurtosis
        confidence_level: desired confidence level
    """
    if n_trials <= 0 or n_observations <= 0:
        return DeflatedSharpeResult(
            observed_sharpe=observed_sharpe,
            deflated_sharpe=observed_sharpe,
            probability_alpha=1.0,
            multiple_testing_adjustment=0.0,
            passes_threshold=False,
        )

    # Expected max Sharpe under null (no skill)
    euler_mascheroni = 0.5772156649
    expected_max_sharpe = (
        (1 - euler_mascheroni) * _norm_ppf(1 - 1/n_trials)
        + euler_mascheroni * _norm_ppf(1 - 1/(n_trials * math.e))
    )

    # Standard error of Sharpe ratio
    sr_std = math.sqrt(
        (1 - skewness * observed_sharpe + (kurtosis - 1) / 4 * observed_sharpe**2)
        / (n_observations - 1)
    )

    if sr_std <= 0:
        sr_std = 1e-10

    # Deflated Sharpe = probability that observed Sharpe is not due to chance
    z = (observed_sharpe - expected_max_sharpe) / sr_std
    probability_alpha = 1 - _norm_cdf(z)

    # Deflated Sharpe ratio
    deflated = observed_sharpe - expected_max_sharpe
    multiple_testing = expected_max_sharpe

    passes = observed_sharpe > expected_max_sharpe and probability_alpha < (1 - confidence_level)

    return DeflatedSharpeResult(
        observed_sharpe=observed_sharpe,
        deflated_sharpe=deflated,
        probability_alpha=probability_alpha,
        multiple_testing_adjustment=multiple_testing,
        passes_threshold=passes,
    )
