"""Tests for Phase 5 — Cost stress + parameter stability."""

from graxia.packages.quant_os.validation.cost_stress import analyze_cost_sensitivity
from graxia.packages.quant_os.validation.parameter_stability import (
    analyze_parameter_stability,
)

# --- Cost stress tests ---


def test_cost_stress_no_costs():
    result = analyze_cost_sensitivity(base_pnl=100.0, total_costs=0.0)
    assert result.cost_sensitivity == "NONE"
    assert result.survives_stress_1
    assert result.survives_stress_2
    assert result.survives_stress_3
    assert result.stress_3x_pnl == 100.0


def test_cost_stress_low_sensitivity():
    # 3x costs still profitable: 100 - 30*2 = 40 > 0
    result = analyze_cost_sensitivity(base_pnl=100.0, total_costs=30.0)
    assert result.cost_sensitivity == "LOW"
    assert result.survives_stress_1
    assert result.survives_stress_2
    assert result.survives_stress_3


def test_cost_stress_high_sensitivity():
    # 1.5x costs already unprofitable: 10 - 20*0.5 = 0
    result = analyze_cost_sensitivity(base_pnl=10.0, total_costs=20.0)
    assert result.cost_sensitivity == "HIGH"
    assert not result.survives_stress_2
    assert not result.survives_stress_3


# --- Parameter stability tests ---


def test_parameter_stability_stable():
    # All nearby PnLs close to base
    result = analyze_parameter_stability(
        parameter_name="lookback",
        base_value=20,
        nearby_values=[18, 19, 20, 21, 22],
        pnls=[95.0, 98.0, 100.0, 97.0, 94.0],
    )
    assert result.stable
    assert not result.cliff_detected
    assert result.stability_score >= 0.9


def test_parameter_stability_cliff():
    # One value causes massive drop
    result = analyze_parameter_stability(
        parameter_name="lookback",
        base_value=20,
        nearby_values=[18, 19, 20, 21, 22],
        pnls=[100.0, 95.0, 100.0, 90.0, 10.0],
    )
    assert result.cliff_detected
    assert not result.stable


def test_parameter_stability_insufficient_data():
    result = analyze_parameter_stability(
        parameter_name="threshold",
        base_value=0.5,
        nearby_values=[0.5],
        pnls=[100.0],
    )
    assert result.stable
    assert result.stability_score == 1.0
