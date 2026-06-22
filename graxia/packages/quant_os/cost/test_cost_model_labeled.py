"""Tests for labeled cost model."""
from graxia.packages.quant_os.cost.cost_model_labeled import (
    LabeledCostModel, LabeledCost, EvidenceLevel
)


def test_cost_creates():
    cost = LabeledCost(
        spread_points=3.0, slippage_points=0.5,
        commission_per_lot=7.0, swap_long_points=-2.5,
        swap_short_points=0.5,
        evidence_level=EvidenceLevel.ASSUMED_STRESS.value,
    )
    assert cost.total_cost_points == 3.5


def test_cost_to_dict():
    cost = LabeledCost(
        spread_points=3.0, slippage_points=0.5,
        commission_per_lot=7.0, swap_long_points=-2.5,
        swap_short_points=0.5,
        evidence_level="ASSUMED_STRESS",
    )
    d = cost.to_dict()
    assert d["spread_points"] == 3.0
    assert d["evidence_level"] == "ASSUMED_STRESS"


def test_model_default_pre_demo():
    model = LabeledCostModel.default_pre_demo()
    assert len(model.get_all_scenarios()) == 4
    assert model.get_scenario("base") is not None
    assert model.get_scenario("stress_3") is not None


def test_model_stress_matrix():
    model = LabeledCostModel.default_pre_demo()
    matrix = model.stress_matrix()
    assert len(matrix) == 4
    assert all(s["evidence_level"] == "ASSUMED_STRESS" for s in matrix)


def test_model_add_custom():
    model = LabeledCostModel()
    model.add_scenario("custom", LabeledCost(
        spread_points=2.0, slippage_points=0.3,
        commission_per_lot=5.0, swap_long_points=-1.0,
        swap_short_points=0.2,
        evidence_level=EvidenceLevel.QUOTE_OBSERVED.value,
        quality_note="from real tick data",
    ))
    assert model.get_scenario("custom").evidence_level == "QUOTE_OBSERVED"
