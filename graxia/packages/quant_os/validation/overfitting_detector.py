"""Unified overfitting detection pipeline — go/no-go gate for strategy promotion.

Orchestrates all anti-overfitting tools into a single evaluation:
  1. Deflated Sharpe Ratio (DSR) — corrects for selection bias
  2. Probability of Backtest Overfitting (PBO) — CSCV cross-validation
  3. Bootstrap confidence intervals — robustness of returns
  4. Cost stress sensitivity — survives cost increases?
  5. Parameter stability — stable near optimal?
  6. Minimum Backtest Length (MinBTL) — enough data?
  7. Search budget tracking — how many trials were tried?

Usage:
    detector = OverfittingDetector()
    report = detector.evaluate(
        strategy_id="xau_mean_revert_v1",
        returns=bar_returns,
        n_trials=150,
        n_observations=5000,
        oos_returns_per_fold=wf_folds,
        cost_pnl=10000,
        total_costs=2000,
        param_values=[18, 19, 20, 21, 22],
        param_pnls=[950, 980, 1000, 970, 940],
        data_length=5000,
    )
    if not report.passed:
        print(f"Blockers: {report.blockers}")
        print(f"Recommendation: {report.recommendation}")
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .bootstrap_sensitivity import BootstrapResult, bootstrap_confidence_interval
from .cost_stress import CostStressResult, analyze_cost_sensitivity
from .deflated_sharpe import (
    DeflatedSharpeResult,
    MinBTLResult,
    deflated_sharpe_ratio,
    min_backtest_length,
)
from .parameter_stability import ParameterStabilityResult, analyze_parameter_stability
from .probability_overfitting import PBOResult, calculate_pbo_from_matrix


@dataclass
class OverfittingConfig:
    """Thresholds for the overfitting detection pipeline."""

    # DSR
    min_deflated_sharpe: float = 0.5
    min_observed_sharpe: float = 1.0
    # PBO
    max_pbo: float = 0.5
    # Bootstrap
    min_bootstrap_ci_lower: float = 0.0
    # Walk-forward (IS/OOS)
    min_oos_consistency: float = 0.5
    max_is_os_gap: float = 0.3
    # Cost stress
    max_cost_sensitivity: str = "MEDIUM"  # "LOW" or "MEDIUM" acceptable
    # Parameter stability
    min_param_stability: float = 0.7
    # MinBTL
    require_sufficient_data: bool = True
    # Search budget
    max_trials: int = 1000


@dataclass
class OverfittingReport:
    """Full overfitting detection report."""

    strategy_id: str
    timestamp: str
    # Individual results
    dsr_result: DeflatedSharpeResult | None = None
    pbo_result: PBOResult | None = None
    bootstrap_result: BootstrapResult | None = None
    cost_stress_result: CostStressResult | None = None
    param_stability_results: list[ParameterStabilityResult] = field(default_factory=list)
    min_btl_result: MinBTLResult | None = None
    # Aggregate
    passed: bool = False
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    score: float = 0.0  # 0-1 composite score
    recommendation: str = "ARCHIVE_NO_EDGE"  # PROCEED | RETURN_TO_RESEARCH | ARCHIVE_NO_EDGE


class OverfittingDetector:
    """Unified overfitting detection pipeline.

    Runs all anti-overfitting checks and produces a go/no-go decision.

    Args:
        config: Optional OverfittingConfig with custom thresholds
    """

    def __init__(self, config: OverfittingConfig | None = None):
        self.config = config or OverfittingConfig()

    def evaluate(
        self,
        strategy_id: str,
        returns: list[float],
        n_trials: int,
        n_observations: int,
        oos_returns_per_fold: list[list[float]],
        cost_pnl: float,
        total_costs: float,
        param_values: list[float],
        param_pnls: list[float],
        data_length: int,
        sharpe: float | None = None,
        skewness: float = 0.0,
        kurtosis: float = 3.0,
        strategy_matrix: dict[str, list[list[float]]] | None = None,
    ) -> OverfittingReport:
        """Run the full overfitting detection pipeline.

        Args:
            strategy_id: Unique identifier for the strategy
            returns: Bar-level returns from the backtest
            n_trials: Total number of strategy configurations tried during research
            n_observations: Number of return observations used to compute Sharpe
            oos_returns_per_fold: DEPRECATED — use strategy_matrix instead
            cost_pnl: Base PnL (before stress)
            total_costs: Total transaction costs
            param_values: Parameter values tested (for stability analysis)
            param_pnls: PnL at each parameter value
            data_length: Total bars available in the dataset
            sharpe: Observed Sharpe (computed from returns if not provided)
            skewness: Return distribution skewness
            kurtosis: Return distribution excess kurtosis
            strategy_matrix: CSCV strategy matrix: config_id -> list of per-period
                return arrays. When provided, uses proper CSCV algorithm.

        Returns:
            OverfittingReport with all results, blockers, warnings, score, recommendation
        """
        report = OverfittingReport(
            strategy_id=strategy_id,
            timestamp=datetime.now(UTC).isoformat(),
        )

        # Compute Sharpe if not provided
        if sharpe is None:
            sharpe = self._compute_sharpe(returns)

        # --- Run each check ---
        report.dsr_result = self._check_dsr(sharpe, n_trials, n_observations, skewness, kurtosis)
        report.pbo_result = self._check_pbo(strategy_matrix, oos_returns_per_fold)
        report.bootstrap_result = self._check_bootstrap(returns)
        report.cost_stress_result = self._check_cost_stress(cost_pnl, total_costs)
        report.param_stability_results = self._check_param_stability(param_values, param_pnls)
        report.min_btl_result = self._check_min_btl(sharpe, n_trials, skewness, kurtosis, data_length)

        # --- Determine blockers ---
        self._check_blockers(report)

        # --- Compute composite score ---
        report.score = self._compute_score(report)

        # --- Determine recommendation ---
        report.recommendation = self._determine_recommendation(report)
        report.passed = report.recommendation == "PROCEED"

        return report

    def _compute_sharpe(self, returns: list[float], risk_free_rate: float = 0.0) -> float:
        """Compute annualized Sharpe from returns."""
        if len(returns) < 2:
            return 0.0
        mean = sum(returns) / len(returns)
        var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        std = math.sqrt(var) if var > 0 else 0.0
        if std == 0:
            return 0.0
        excess = mean - risk_free_rate
        return (excess / std) * math.sqrt(252)  # annualize

    def _check_dsr(self, sharpe, n_trials, n_observations, skewness, kurtosis) -> DeflatedSharpeResult:
        return deflated_sharpe_ratio(
            observed_sharpe=sharpe,
            n_trials=n_trials,
            n_observations=n_observations,
            skewness=skewness,
            kurtosis=kurtosis,
        )

    def _check_pbo(
        self,
        strategy_matrix: dict[str, list[list[float]]] | None = None,
        oos_returns_per_fold: list[list[float]] | None = None,
    ) -> PBOResult:
        """Check PBO using proper CSCV with strategy matrix if available."""
        if strategy_matrix and len(strategy_matrix) >= 2:
            return calculate_pbo_from_matrix(strategy_matrix)
        # Fallback: no strategy matrix available
        return PBOResult(pbo=1.0, n_partitions=0, n_combinations_tested=0, passes_threshold=False)

    def _check_bootstrap(self, returns) -> BootstrapResult:
        if not returns:
            return BootstrapResult(
                metric_name="return",
                observed_value=0,
                confidence_interval_95=(0, 0),
                bootstrap_mean=0,
                bootstrap_std=0,
                n_resamples=0,
                passes_threshold=False,
            )
        return bootstrap_confidence_interval(returns, n_resamples=1000)

    def _check_cost_stress(self, cost_pnl, total_costs) -> CostStressResult:
        return analyze_cost_sensitivity(base_pnl=cost_pnl, total_costs=total_costs)

    def _check_param_stability(self, param_values, param_pnls) -> list[ParameterStabilityResult]:
        if not param_values or not param_pnls or len(param_values) != len(param_pnls):
            return []
        # Analyze stability for the full parameter set
        base_idx = len(param_values) // 2
        result = analyze_parameter_stability(
            parameter_name="primary",
            base_value=param_values[base_idx],
            nearby_values=param_values,
            pnls=param_pnls,
        )
        return [result]

    def _check_min_btl(self, sharpe, n_trials, skewness, kurtosis, data_length) -> MinBTLResult:
        return min_backtest_length(
            observed_sharpe=sharpe,
            n_trials=n_trials,
            skewness=skewness,
            kurtosis=kurtosis,
            current_observations=data_length,
        )

    def _check_blockers(self, report: OverfittingReport) -> None:
        """Check for auto-fail conditions and warnings."""
        cfg = self.config

        # DSR blocker
        if report.dsr_result and not report.dsr_result.passes_threshold:
            # deflated_sharpe is now probability_alpha (P(false positive))
            # High probability = bad (likely false positive)
            if report.dsr_result.probability_alpha > 0.5:
                report.blockers.append(
                    f"DSR P(false positive)={report.dsr_result.probability_alpha:.3f} > 0.5 — "
                    f"strong evidence of selection bias after "
                    f"{report.dsr_result.multiple_testing_adjustment:.1f} trials"
                )
            elif report.dsr_result.probability_alpha > cfg.min_deflated_sharpe:
                report.warnings.append(
                    f"DSR P(false positive)={report.dsr_result.probability_alpha:.3f} > {cfg.min_deflated_sharpe} threshold"
                )

        # PBO blocker
        if report.pbo_result and report.pbo_result.pbo > cfg.max_pbo:
            if report.pbo_result.pbo > 0.7:
                report.blockers.append(f"PBO={report.pbo_result.pbo:.3f} > 0.7 — severe overfitting detected")
            else:
                report.warnings.append(f"PBO={report.pbo_result.pbo:.3f} > {cfg.max_pbo} threshold")

        # Bootstrap blocker
        if report.bootstrap_result:
            ci_lower = report.bootstrap_result.confidence_interval_95[0]
            if ci_lower < cfg.min_bootstrap_ci_lower:
                if ci_lower < 0:
                    report.blockers.append(f"Bootstrap CI lower={ci_lower:.4f} < 0 — returns not reliably positive")
                else:
                    report.warnings.append(f"Bootstrap CI lower={ci_lower:.4f} near zero")

        # Cost stress
        if report.cost_stress_result:
            sensitivity = report.cost_stress_result.cost_sensitivity
            if sensitivity == "HIGH":
                report.blockers.append(f"Cost sensitivity={sensitivity} — strategy destroyed by cost increases")
            elif sensitivity == "MEDIUM" and cfg.max_cost_sensitivity == "LOW":
                report.warnings.append(f"Cost sensitivity={sensitivity}")

        # Parameter stability
        for ps in report.param_stability_results:
            if ps.cliff_detected:
                report.blockers.append("Parameter cliff detected — performance drops sharply near optimal")
            elif ps.stability_score < cfg.min_param_stability:
                report.warnings.append(f"Parameter stability={ps.stability_score:.3f} < {cfg.min_param_stability}")

        # MinBTL
        if report.min_btl_result and cfg.require_sufficient_data and not report.min_btl_result.sufficient:
            report.warnings.append(
                f"MinBTL: need {report.min_btl_result.min_observations} bars — may lack statistical power"
            )

    def _compute_score(self, report: OverfittingReport) -> float:
        """Compute composite overfitting resistance score (0-1, higher = better)."""
        scores = []
        weights = []

        # DSR component (0.25)
        if report.dsr_result:
            # deflated_sharpe is now probability_alpha (CDF probability)
            # Low probability = good (unlikely to be false positive)
            # Score: 1 - probability_alpha (so P(false positive)=0 → score=1)
            dsr_score = max(0, min(1, 1.0 - report.dsr_result.probability_alpha))
            scores.append(dsr_score)
            weights.append(0.25)

        # PBO component (0.20) — inverted: low PBO = high score
        if report.pbo_result:
            pbo_score = max(0, 1 - report.pbo_result.pbo * 2)  # PBO=0 → 1, PBO=0.5 → 0
            scores.append(pbo_score)
            weights.append(0.20)

        # Bootstrap component (0.15)
        if report.bootstrap_result:
            ci_lower = report.bootstrap_result.confidence_interval_95[0]
            boot_score = max(0, min(1, ci_lower * 100 + 0.5))  # rough normalization
            scores.append(boot_score)
            weights.append(0.15)

        # Cost stress component (0.10)
        if report.cost_stress_result:
            cost_map = {"NONE": 1.0, "LOW": 0.8, "MEDIUM": 0.5, "HIGH": 0.1}
            scores.append(cost_map.get(report.cost_stress_result.cost_sensitivity, 0.5))
            weights.append(0.10)

        # Parameter stability component (0.10)
        if report.param_stability_results:
            avg_stability = sum(ps.stability_score for ps in report.param_stability_results) / len(
                report.param_stability_results
            )
            scores.append(avg_stability)
            weights.append(0.10)

        # Data sufficiency component (0.05)
        if report.min_btl_result:
            data_score = 1.0 if report.min_btl_result.sufficient else 0.3
            scores.append(data_score)
            weights.append(0.05)

        # Blocker penalty
        blocker_penalty = min(0.5, len(report.blockers) * 0.15)

        if not scores:
            return 0.0

        weighted = sum(s * w for s, w in zip(scores, weights, strict=False)) / sum(weights)
        return max(0, weighted - blocker_penalty)

    def _determine_recommendation(self, report: OverfittingReport) -> str:
        """Determine go/no-go recommendation."""
        if report.blockers:
            # Check severity
            severe_keywords = ["severe", "selection bias", "cliff", "destroyed"]
            has_severe = any(kw in b.lower() for b in report.blockers for kw in severe_keywords)
            if has_severe or report.score < 0.3:
                return "ARCHIVE_NO_EDGE"
            return "RETURN_TO_RESEARCH"

        if report.score >= 0.7 and not report.warnings:
            return "PROCEED"
        elif report.score >= 0.5:
            return "RETURN_TO_RESEARCH"  # promising but needs more validation
        else:
            return "ARCHIVE_NO_EDGE"
