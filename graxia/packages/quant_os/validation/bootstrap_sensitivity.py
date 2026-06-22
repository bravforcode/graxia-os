"""Phase 5 — Bootstrap sensitivity analysis.

Estimate confidence intervals for strategy metrics using bootstrap resampling.
"""
import random
from dataclasses import dataclass


@dataclass
class BootstrapResult:
    metric_name: str
    observed_value: float
    confidence_interval_95: tuple[float, float]
    bootstrap_mean: float
    bootstrap_std: float
    n_resamples: int
    passes_threshold: bool  # lower bound > 0


def bootstrap_confidence_interval(
    values: list[float],
    n_resamples: int = 1000,
    confidence_level: float = 0.95,
    seed: int = 42,
    metric_fn=None,
) -> BootstrapResult:
    """Compute bootstrap confidence interval for any metric."""
    if metric_fn is None:
        metric_fn = lambda x: sum(x) / len(x) if x else 0

    if len(values) == 0:
        return BootstrapResult(
            metric_name="unknown",
            observed_value=0,
            confidence_interval_95=(0, 0),
            bootstrap_mean=0,
            bootstrap_std=0,
            n_resamples=0,
            passes_threshold=False,
        )

    observed = metric_fn(values)

    rng = random.Random(seed)
    bootstrap_stats = []

    for _ in range(n_resamples):
        resample = [rng.choice(values) for _ in range(len(values))]
        bootstrap_stats.append(metric_fn(resample))

    bootstrap_stats.sort()

    alpha = 1 - confidence_level
    lower_idx = int(alpha / 2 * n_resamples)
    upper_idx = int((1 - alpha / 2) * n_resamples) - 1

    lower = bootstrap_stats[lower_idx]
    upper = bootstrap_stats[upper_idx]

    mean = sum(bootstrap_stats) / len(bootstrap_stats)
    std = (sum((x - mean) ** 2 for x in bootstrap_stats) / len(bootstrap_stats)) ** 0.5

    return BootstrapResult(
        metric_name="metric",
        observed_value=observed,
        confidence_interval_95=(lower, upper),
        bootstrap_mean=mean,
        bootstrap_std=std,
        n_resamples=n_resamples,
        passes_threshold=lower > 0,
    )
