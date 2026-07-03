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
    expected_max_sharpe = (1 - euler_mascheroni) * _norm_ppf(1 - 1 / n_trials) + euler_mascheroni * _norm_ppf(
        1 - 1 / (n_trials * math.e)
    )

    # Standard error of Sharpe ratio
    sr_std = math.sqrt(
        (1 - skewness * observed_sharpe + (kurtosis - 1) / 4 * observed_sharpe**2) / (n_observations - 1)
    )

    if sr_std <= 0:
        sr_std = 1e-10

    # Deflated Sharpe = probability that observed Sharpe is not due to chance
    # CORRECT formula: z = (SR₀ - σ(SR)·E[max Z]) / σ(SR)
    # E[max SR] under null = sr_std * expected_max_sharpe (standard normal quantile scaled by SR std)
    adjusted_expected = sr_std * expected_max_sharpe
    z = (observed_sharpe - adjusted_expected) / sr_std
    probability_alpha = 1 - _norm_cdf(z)

    # Deflated Sharpe ratio — probability (not raw difference)
    deflated = probability_alpha
    multiple_testing = adjusted_expected

    passes = observed_sharpe > adjusted_expected and probability_alpha < (1 - confidence_level)

    return DeflatedSharpeResult(
        observed_sharpe=observed_sharpe,
        deflated_sharpe=deflated,
        probability_alpha=probability_alpha,
        multiple_testing_adjustment=multiple_testing,
        passes_threshold=passes,
    )


@dataclass
class MinBTLResult:
    """Result of minimum backtest length calculation."""

    min_observations: int  # Minimum bars/observations needed
    n_trials: int  # Number of strategy trials
    observed_sharpe: float  # The Sharpe being tested
    expected_max_sharpe: float  # E[max_SR] under null
    z_threshold: float  # z-score at confidence level
    sufficient: bool  # True if caller indicates data >= min_observations


def min_backtest_length(
    observed_sharpe: float,
    n_trials: int,
    confidence_level: float = 0.95,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    current_observations: int | None = None,
) -> MinBTLResult:
    """Calculate minimum observations needed for Sharpe to be statistically significant.

    Uses the Bailey & Lopez de Prado approach: given N strategy trials and
    an observed Sharpe ratio, compute the minimum T such that the Sharpe
    is unlikely to arise from selection bias alone.

    Args:
        observed_sharpe: Annualized Sharpe ratio from backtest
        n_trials: Number of strategy configurations tested
        confidence_level: Desired confidence (default 0.95)
        skewness: Return distribution skewness (default 0 = normal)
        kurtosis: Return distribution kurtosis (default 3 = normal)
        current_observations: If provided, checks whether current data is sufficient

    Returns:
        MinBTLResult with minimum observations needed
    """
    sentinel_inf = 999_999_999

    # Edge cases
    if n_trials <= 0:
        z_conf = _norm_ppf(confidence_level)
        return MinBTLResult(
            min_observations=1,
            n_trials=n_trials,
            observed_sharpe=observed_sharpe,
            expected_max_sharpe=0.0,
            z_threshold=z_conf,
            sufficient=(current_observations is not None and current_observations >= 1),
        )

    if observed_sharpe <= 0:
        z_conf = _norm_ppf(confidence_level)
        return MinBTLResult(
            min_observations=sentinel_inf,
            n_trials=n_trials,
            observed_sharpe=observed_sharpe,
            expected_max_sharpe=0.0,
            z_threshold=z_conf,
            sufficient=False,
        )

    # Expected maximum Sharpe under null (same formula as deflated_sharpe_ratio)
    euler_mascheroni = 0.5772156649
    expected_max_sharpe = (1 - euler_mascheroni) * _norm_ppf(1 - 1 / n_trials) + euler_mascheroni * _norm_ppf(
        1 - 1 / (n_trials * math.e)
    )

    # If observed Sharpe doesn't exceed expected max under null, no T suffices
    # Use a reasonable initial estimate of σ(SR) for the threshold check
    sr_std_check = math.sqrt(max(1e-20, (1 - skewness * observed_sharpe + (kurtosis - 1) / 4 * observed_sharpe**2) / 99))
    scaled_expected = sr_std_check * expected_max_sharpe

    if observed_sharpe <= scaled_expected:
        z_conf = _norm_ppf(confidence_level)
        return MinBTLResult(
            min_observations=sentinel_inf,
            n_trials=n_trials,
            observed_sharpe=observed_sharpe,
            expected_max_sharpe=expected_max_sharpe,
            z_threshold=z_conf,
            sufficient=False,
        )

    # z-score at confidence level
    z_conf = _norm_ppf(confidence_level)

    # Numerator of the MinBTL formula: z² * (1 - skew*SR + (kurt-1)/4 * SR²)
    numerator = z_conf**2 * (1 - skewness * observed_sharpe + (kurtosis - 1) / 4 * observed_sharpe**2)

    # Denominator: (SR - σ(SR)·E[max SR])²  — iterative solve since σ(SR) depends on T
    # Start with sr_std from T=100, iterate to convergence
    T_est = 100.0
    for _ in range(10):
        sr_std_est = math.sqrt(max(1e-20, (1 - skewness * observed_sharpe + (kurtosis - 1) / 4 * observed_sharpe**2) / max(T_est - 1, 1)))
        scaled_exp = sr_std_est * expected_max_sharpe
        denominator = (observed_sharpe - scaled_exp) ** 2
        if denominator <= 0:
            T_est = 999_999_999
            break
        min_obs = 1 + numerator / denominator
        if abs(min_obs - T_est) < 1:
            break
        T_est = min_obs

    min_obs_int = int(math.ceil(min_obs))

    sufficient = current_observations is not None and current_observations >= min_obs_int

    return MinBTLResult(
        min_observations=min_obs_int,
        n_trials=n_trials,
        observed_sharpe=observed_sharpe,
        expected_max_sharpe=expected_max_sharpe,
        z_threshold=z_conf,
        sufficient=sufficient,
    )
