"""Phase 5 — Cost stress sensitivity analysis."""
from dataclasses import dataclass


@dataclass
class CostStressResult:
    base_pnl: float
    stress_1_5x_pnl: float
    stress_2x_pnl: float
    stress_3x_pnl: float
    survives_stress_1: bool  # pnl > 0 after 1.5x costs
    survives_stress_2: bool  # pnl > 0 after 2x costs
    survives_stress_3: bool  # pnl > 0 after 3x costs
    cost_sensitivity: str  # LOW/MEDIUM/HIGH


def analyze_cost_sensitivity(
    base_pnl: float,
    total_costs: float,
) -> CostStressResult:
    """Analyze how strategy performs under cost stress."""
    if total_costs == 0:
        return CostStressResult(
            base_pnl=base_pnl,
            stress_1_5x_pnl=base_pnl,
            stress_2x_pnl=base_pnl,
            stress_3x_pnl=base_pnl,
            survives_stress_1=base_pnl > 0,
            survives_stress_2=base_pnl > 0,
            survives_stress_3=base_pnl > 0,
            cost_sensitivity="NONE",
        )

    s1 = base_pnl - total_costs * 0.5  # 1.5x = base + 0.5x extra
    s2 = base_pnl - total_costs * 1.0  # 2x = base + 1x extra
    s3 = base_pnl - total_costs * 2.0  # 3x = base + 2x extra

    if s3 > 0:
        sensitivity = "LOW"
    elif s2 > 0:
        sensitivity = "MEDIUM"
    else:
        sensitivity = "HIGH"

    return CostStressResult(
        base_pnl=base_pnl,
        stress_1_5x_pnl=s1,
        stress_2x_pnl=s2,
        stress_3x_pnl=s3,
        survives_stress_1=s1 > 0,
        survives_stress_2=s2 > 0,
        survives_stress_3=s3 > 0,
        cost_sensitivity=sensitivity,
    )
