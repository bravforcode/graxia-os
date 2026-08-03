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
    *,
    sharpe_annualization_factor: float,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    confidence_level: float = 0.95,
) -> DeflatedSharpeResult:
    """Calculate deflated Sharpe ratio.

    The Lo (2002) standard-error formula requires observed_sharpe and
    n_observations to be in matching units: observed_sharpe must be the
    Sharpe computed directly from a sample of n_observations returns, with
    no rescaling in between. Most callers report an *annualized* Sharpe
    (per_period_sharpe * sqrt(periods_per_year)) while n_observations counts
    the raw per-period sample (e.g. daily bars) that produced it — passing
    both as-is silently inflates the significance test. sharpe_annualization_factor
    is the sqrt(periods_per_year)-style factor that was multiplied in to
    produce observed_sharpe; pass 1.0 if observed_sharpe is already a raw
    per-observation Sharpe, or if this call site hasn't been audited yet
    (1.0 preserves prior, possibly-incorrect behavior instead of guessing).
    See MATH_CORRECTNESS_AUDIT.md for per-call-site audit status.

    Args:
        observed_sharpe: Sharpe ratio from backtest (see unit note above)
        n_trials: number of strategy trials (multiple testing)
        n_observations: number of return observations backing observed_sharpe
        sharpe_annualization_factor: factor observed_sharpe was scaled by
            relative to the per-observation Sharpe over n_observations; use
            1.0 for an un-annualized Sharpe or an unaudited call site
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

    raw_sharpe = observed_sharpe / sharpe_annualization_factor

    # Expected max Sharpe under null (no skill)
    euler_mascheroni = 0.5772156649
    expected_max_sharpe = (1 - euler_mascheroni) * _norm_ppf(1 - 1 / n_trials) + euler_mascheroni * _norm_ppf(
        1 - 1 / (n_trials * math.e)
    )

    # Standard error of Sharpe ratio (raw_sharpe/n_observations must be matching units)
    sr_std = math.sqrt((1 - skewness * raw_sharpe + (kurtosis - 1) / 4 * raw_sharpe**2) / (n_observations - 1))

    if sr_std <= 0:
        sr_std = 1e-10

    # Deflated Sharpe = probability that observed Sharpe is not due to chance
    # CORRECT formula: z = (SR₀ - σ(SR)·E[max Z]) / σ(SR)
    # E[max SR] under null = sr_std * expected_max_sharpe (standard normal quantile scaled by SR std)
    adjusted_expected = sr_std * expected_max_sharpe
    z = (raw_sharpe - adjusted_expected) / sr_std
    probability_alpha = 1 - _norm_cdf(z)

    # Deflated Sharpe ratio — probability (not raw difference)
    deflated = probability_alpha
    multiple_testing = adjusted_expected * sharpe_annualization_factor

    passes = raw_sharpe > adjusted_expected and probability_alpha < (1 - confidence_level)

    return DeflatedSharpeResult(
        observed_sharpe=observed_sharpe,
        deflated_sharpe=deflated,
        probability_alpha=probability_alpha,
        multiple_testing_adjustment=multiple_testing,
        passes_threshold=passes,
    )


def dsr_from_annualized(
    observed_sharpe: float,
    n_trials: int,
    n_observations: int,
    *,
    annualization_factor: float = 252.0,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    confidence_level: float = 0.95,
) -> DeflatedSharpeResult:
    """DSR for an ANNUALIZED Sharpe ratio.

    Bailey & Lopez de Prado (2014) Eq.(2) requires a per-observation Sharpe:
    the Lo (2002) sr_std formula breaks when an annualized SR is passed with
    raw-bar n_observations (z is inflated ~sqrt(periods_per_year)x, producing
    false PASS verdicts). This helper de-annualizes internally so callers
    cannot get the units wrong.

    Args:
        observed_sharpe: Annualized Sharpe ratio from backtest.
        n_trials: Number of strategy trials (multiple testing correction).
        n_observations: Raw per-period observation count (e.g. daily bars).
        annualization_factor: Bars/periods per year (252=D1, 6096=H1, ...).
        skewness: RAW return skewness (0 for normal).
        kurtosis: RAW return kurtosis (3 for normal — NOT excess).
        confidence_level: Confidence for the pass threshold.
    """
    if annualization_factor <= 1:
        import warnings

        warnings.warn(
            f"dsr_from_annualized: annualization_factor={annualization_factor} <= 1 "
            "looks like a unit error (expected bars/year like 252, 6096).",
            stacklevel=2,
        )
        annualization_factor = 252.0

    return deflated_sharpe_ratio(
        observed_sharpe=observed_sharpe,
        n_trials=n_trials,
        n_observations=n_observations,
        sharpe_annualization_factor=math.sqrt(annualization_factor),
        skewness=skewness,
        kurtosis=kurtosis,
        confidence_level=confidence_level,
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
    *,
    sharpe_annualization_factor: float,
    confidence_level: float = 0.95,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    current_observations: int | None = None,
) -> MinBTLResult:
    """Calculate minimum observations needed for Sharpe to be statistically significant.

    Uses the Bailey & Lopez de Prado approach: given N strategy trials and
    an observed Sharpe ratio, compute the minimum T such that the Sharpe
    is unlikely to arise from selection bias alone.

    Same unit requirement as deflated_sharpe_ratio(): the Lo (2002) sr_std
    formula this is built on needs observed_sharpe and the resulting
    min_observations count to be in the SAME units — i.e. the per-period
    Sharpe computed directly from n_observations returns. Since callers
    typically hold an annualized Sharpe, sharpe_annualization_factor
    de-annualizes it internally (raw_sharpe = observed_sharpe / factor)
    before it enters the sr_std math, so min_observations comes out
    comparable to a raw (e.g. daily-bar) current_observations count.
    Pass 1.0 only at unaudited call sites to exactly preserve prior
    (possibly-incorrect) behavior — see MATH_CORRECTNESS_AUDIT.md.

    Args:
        observed_sharpe: Annualized Sharpe ratio from backtest
        n_trials: Number of strategy configurations tested
        sharpe_annualization_factor: Divides observed_sharpe to recover the
            raw per-period Sharpe (e.g. sqrt(252) for daily bars -> annual).
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

    raw_sharpe = observed_sharpe / sharpe_annualization_factor

    if raw_sharpe <= 0:
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
    sr_std_check = math.sqrt(max(1e-20, (1 - skewness * raw_sharpe + (kurtosis - 1) / 4 * raw_sharpe**2) / 99))
    scaled_expected = sr_std_check * expected_max_sharpe

    if raw_sharpe <= scaled_expected:
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
    numerator = z_conf**2 * (1 - skewness * raw_sharpe + (kurtosis - 1) / 4 * raw_sharpe**2)

    # Denominator: (SR - σ(SR)·E[max SR])²  — iterative solve since σ(SR) depends on T
    # Start with sr_std from T=100, iterate to convergence
    t_est = 100.0
    for _ in range(10):
        sr_std_est = math.sqrt(
            max(1e-20, (1 - skewness * raw_sharpe + (kurtosis - 1) / 4 * raw_sharpe**2) / max(t_est - 1, 1))
        )
        scaled_exp = sr_std_est * expected_max_sharpe
        denominator = (raw_sharpe - scaled_exp) ** 2
        if denominator <= 0:
            t_est = 999_999_999
            break
        min_obs = 1 + numerator / denominator
        if abs(min_obs - t_est) < 1:
            break
        t_est = min_obs

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
