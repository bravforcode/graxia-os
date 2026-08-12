import math
from dataclasses import dataclass, field


@dataclass
class CheckResult:
    name: str
    passed: bool
    details: str = ""


class DataLeakageTest:
    """Verify no feature timestamps exceed the train-end boundary."""

    def run(self, train_end_index: int, total_bars: int, feature_timestamps: list[int]) -> CheckResult:
        violations = [t for t in feature_timestamps if t >= train_end_index]
        if violations:
            return CheckResult(
                name="data_leakage",
                passed=False,
                details=f"LEAKED_TIMESTAMPS:{violations}",
            )
        return CheckResult(name="data_leakage", passed=True, details="NO_LEAKAGE")


class FeatureAvailabilityTest:
    """Verify all required features are available at runtime."""

    def run(self, feature_names: list[str], available_features: dict[str, bool]) -> CheckResult:
        missing = [f for f in feature_names if not available_features.get(f, False)]
        if missing:
            return CheckResult(
                name="feature_availability",
                passed=False,
                details=f"MISSING_FEATURES:{missing}",
            )
        return CheckResult(name="feature_availability", passed=True, details="ALL_AVAILABLE")


class WalkForwardValidation:
    """Validate that walk-forward folds produce acceptable out-of-sample results."""

    def run(self, folds: list[dict]) -> CheckResult:
        if not folds:
            return CheckResult(
                name="walk_forward",
                passed=False,
                details="NO_FOLDS",
            )
        sharpes = [f.get("oos_sharpe", 0) for f in folds]
        avg_sharpe = sum(sharpes) / len(sharpes)
        if avg_sharpe <= 0:
            return CheckResult(
                name="walk_forward",
                passed=False,
                details=f"NEGATIVE_AVG_OOS_SHARPE:{avg_sharpe:.4f}",
            )
        return CheckResult(
            name="walk_forward",
            passed=True,
            details=f"AVG_OOS_SHARPE:{avg_sharpe:.4f}",
        )


class DeflatedSharpeRatio:
    """Adjust Sharpe ratio for multiple-testing bias."""

    def run(self, sharpe: float, n_trials: int, n_bars: int) -> CheckResult:
        if n_trials <= 0 or n_bars <= 0:
            return CheckResult(
                name="deflated_sharpe",
                passed=False,
                details="INVALID_INPUTS",
            )
        euler_gamma = 0.5772156649015329
        log_n = math.log(max(n_trials, 2))
        expected_max_sharpe = math.sqrt(2 * log_n) * (1 - euler_gamma / (2 * log_n)) if n_trials > 1 else 0
        variance_adjusted = sharpe - expected_max_sharpe
        if variance_adjusted <= 0:
            return CheckResult(
                name="deflated_sharpe",
                passed=False,
                details=f"DSR_NOT_SIGNIFICANT:sharpe={sharpe:.4f},expected_max={expected_max_sharpe:.4f}",
            )
        return CheckResult(
            name="deflated_sharpe",
            passed=True,
            details=f"DSR_PASS:sharpe={sharpe:.4f},deflated={variance_adjusted:.4f}",
        )


class PBOCheck:
    """Probability of Backtest Overfitting — check degradation between IS and OOS."""

    def run(self, is_sharpe: float, oos_sharpe: float, degradation_threshold: float = 0.5) -> CheckResult:
        if is_sharpe == 0:
            degradation = 1.0 if oos_sharpe == 0 else 0.0
        else:
            degradation = 1.0 - (oos_sharpe / is_sharpe)
        if degradation > degradation_threshold:
            return CheckResult(
                name="pbo_check",
                passed=False,
                details=f"HIGH_DEGRADATION:{degradation:.4f} > {degradation_threshold}",
            )
        return CheckResult(
            name="pbo_check",
            passed=True,
            details=f"DEGRADATION_OK:{degradation:.4f}",
        )


class ParameterStability:
    """Check that parameters remain stable across folds/windows."""

    def run(self, param_sets: list[dict], performance: list[float], min_folds: int = 3) -> CheckResult:
        if len(param_sets) < min_folds or len(performance) < min_folds:
            return CheckResult(
                name="parameter_stability",
                passed=False,
                details=f"INSUFFICIENT_FOLDS:{len(param_sets)}<{min_folds}",
            )
        numeric_params = {}
        for ps in param_sets:
            for k, v in ps.items():
                if isinstance(v, (int, float)):
                    numeric_params.setdefault(k, []).append(v)
        stable_params = []
        unstable_params = []
        for k, values in numeric_params.items():
            mean_val = sum(values) / len(values)
            if mean_val == 0:
                cv = 0.0
            else:
                variance = sum((v - mean_val) ** 2 for v in values) / len(values)
                cv = math.sqrt(variance) / abs(mean_val)
            if cv < 0.5:
                stable_params.append(k)
            else:
                unstable_params.append(k)
        if unstable_params:
            return CheckResult(
                name="parameter_stability",
                passed=False,
                details=f"UNSTABLE_PARAMS:{unstable_params}",
            )
        return CheckResult(
            name="parameter_stability",
            passed=True,
            details=f"STABLE_PARAMS:{stable_params}",
        )


class ValidationStack:
    """Run all Phase 5 governance checks in sequence."""

    def run_all(
        self,
        train_end_index: int,
        total_bars: int,
        feature_timestamps: list[int],
        feature_names: list[str],
        available_features: dict[str, bool],
        folds: list[dict],
        sharpe: float,
        n_trials: int,
        n_bars: int,
        is_sharpe: float,
        oos_sharpe: float,
        param_sets: list[dict],
        performance: list[float],
    ) -> "ValidationResult":
        checks = []
        checks.append(DataLeakageTest().run(train_end_index, total_bars, feature_timestamps))
        checks.append(FeatureAvailabilityTest().run(feature_names, available_features))
        checks.append(WalkForwardValidation().run(folds))
        checks.append(DeflatedSharpeRatio().run(sharpe, n_trials, n_bars))
        checks.append(PBOCheck().run(is_sharpe, oos_sharpe))
        checks.append(ParameterStability().run(param_sets, performance))
        return ValidationResult(checks=checks)


@dataclass
class ValidationResult:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def summary(self) -> dict:
        return {
            "total": len(self.checks),
            "passed": sum(1 for c in self.checks if c.passed),
            "failed": sum(1 for c in self.checks if not c.passed),
            "all_passed": self.all_passed,
            "checks": [{"name": c.name, "passed": c.passed, "details": c.details} for c in self.checks],
        }
