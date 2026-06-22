"""Phase 5 — Verdict logic for statistical validation gate."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Phase5Thresholds:
    deflated_sharpe_min: float = 0.0
    pbo_max: float = 0.05
    cost_stress_survives_1_5x: bool = True
    parameter_stability_min: float = 0.5
    bootstrap_ci_lower_positive: bool = True
    walk_forward_positive_oos: bool = True


@dataclass
class Phase5Verdict:
    verdict: str  # PASS_TO_6 / CONDITIONAL_PASS / NO_GO
    passed_checks: list = field(default_factory=list)
    failed_checks: list = field(default_factory=list)


def evaluate_phase5(
    deflated_sharpe: float,
    pbo: float,
    cost_survives: bool,
    stability_score: float,
    bootstrap_lower: float,
    oos_positive: bool,
    thresholds: Optional[Phase5Thresholds] = None,
) -> Phase5Verdict:
    if thresholds is None:
        thresholds = Phase5Thresholds()

    passed = []
    failed = []

    if deflated_sharpe >= thresholds.deflated_sharpe_min:
        passed.append(f"deflated_sharpe={deflated_sharpe:.3f}")
    else:
        failed.append(f"deflated_sharpe={deflated_sharpe:.3f} < {thresholds.deflated_sharpe_min}")

    if pbo <= thresholds.pbo_max:
        passed.append(f"pbo={pbo:.3f}")
    else:
        failed.append(f"pbo={pbo:.3f} > {thresholds.pbo_max}")

    if cost_survives:
        passed.append("cost_stress=survives_1_5x")
    else:
        failed.append("cost_stress=fails_1_5x")

    if stability_score >= thresholds.parameter_stability_min:
        passed.append(f"stability={stability_score:.3f}")
    else:
        failed.append(f"stability={stability_score:.3f} < {thresholds.parameter_stability_min}")

    if bootstrap_lower > 0:
        passed.append(f"bootstrap_ci_lower={bootstrap_lower:.3f}")
    else:
        failed.append(f"bootstrap_ci_lower={bootstrap_lower:.3f} <= 0")

    if oos_positive:
        passed.append("walk_forward=oos_positive")
    else:
        failed.append("walk_forward=oos_negative")

    if len(failed) == 0:
        verdict = "PASS_TO_6"
    elif len(failed) <= 2:
        verdict = "CONDITIONAL_PASS"
    else:
        verdict = "NO_GO"

    return Phase5Verdict(verdict=verdict, passed_checks=passed, failed_checks=failed)
