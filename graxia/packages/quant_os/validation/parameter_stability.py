"""Phase 5 — Parameter neighborhood stability analysis."""
from dataclasses import dataclass


@dataclass
class ParameterStabilityResult:
    parameter_name: str
    base_value: float
    nearby_values_tested: list
    nearby_pnls: list
    stable: bool  # nearby values don't cause cliff
    cliff_detected: bool  # sharp performance drop
    stability_score: float  # 0-1, 1 = perfectly stable


def analyze_parameter_stability(
    parameter_name: str,
    base_value: float,
    nearby_values: list[float],
    pnls: list[float],
    cliff_threshold: float = 0.5,
) -> ParameterStabilityResult:
    """Check if parameter changes cause performance cliffs."""
    if len(pnls) < 2:
        return ParameterStabilityResult(
            parameter_name=parameter_name,
            base_value=base_value,
            nearby_values_tested=nearby_values,
            nearby_pnls=pnls,
            stable=True,
            cliff_detected=False,
            stability_score=1.0,
        )

    base_pnl = pnls[len(pnls) // 2]  # assume middle is base
    if base_pnl == 0:
        base_pnl = 1e-10

    # Check for cliffs
    cliff = False
    min_ratio = 1.0
    for pnl in pnls:
        ratio = pnl / base_pnl if base_pnl != 0 else 0
        if ratio < min_ratio:
            min_ratio = ratio
        if ratio < cliff_threshold:
            cliff = True

    stability_score = max(0, min_ratio)

    return ParameterStabilityResult(
        parameter_name=parameter_name,
        base_value=base_value,
        nearby_values_tested=nearby_values,
        nearby_pnls=pnls,
        stable=not cliff,
        cliff_detected=cliff,
        stability_score=stability_score,
    )
