"""Phase BE-P4 integration tests — empirical cost calibration."""
from graxia.packages.quant_os.cost.cost_model_labeled import (
    LabeledCostModel, LabeledCost, EvidenceLevel
)
from graxia.packages.quant_os.cost.quote_calibration import QuoteCalibrator
from graxia.packages.quant_os.cost.cost_stress_analyzer import CostStressAnalyzer
from graxia.packages.quant_os.cost.pipeline_latency import PipelineLatencyTracker
from graxia.packages.quant_os.cost.forbidden_shortcuts import ForbiddenShortcutsGuard


def test_labeled_cost_full_lifecycle():
    cost = LabeledCost(
        spread_points=3.0, slippage_points=0.5,
        commission_per_lot=7.0, swap_long_points=-2.5,
        swap_short_points=0.5,
        evidence_level=EvidenceLevel.ASSUMED_STRESS.value,
        quality_note="pre-demo conservative",
    )
    assert cost.total_cost_points == 3.5
    d = cost.to_dict()
    assert d["evidence_level"] == "ASSUMED_STRESS"


def test_quote_calibration_flow():
    cal = QuoteCalibrator()
    for i in range(200):
        cal.observe_spread(0.3 + i * 0.001)
        cal.observe_quote_move(0.1 + i * 0.0005)
        cal.observe_latency(10 + i * 0.05)
    result = cal.calibrate()
    assert result.is_sufficient(100)
    assert result.spread_p50 > 0
    assert result.spread_p90 > result.spread_p50


def test_stress_analysis_flow():
    analyzer = CostStressAnalyzer.default_scenarios()
    results = analyzer.analyze(strategy_pnl_per_trade=5.0)
    assert len(results) == 4
    assert results[0].scenario_name == "base"
    # Stress scenarios should have higher cost
    assert results[-1].total_cost_after > results[0].total_cost_after


def test_pipeline_latency_flow():
    tracker = PipelineLatencyTracker()
    for _ in range(10):
        tracker.on_tick_received()
        tracker.on_signal_finalized()
        tracker.on_order_persisted()
    stats = tracker.get_stats()
    assert stats["count"] == 10
    assert stats["avg_total_ms"] >= 0


def test_forbidden_shortcuts_guard():
    guard = ForbiddenShortcutsGuard()
    ok, _ = guard.check("quote_observed_calibration")
    assert ok
    ok, _ = guard.check("random_normal_slippage")
    assert not ok
    assert len(guard.get_violations()) == 1


def test_model_stress_matrix():
    model = LabeledCostModel.default_pre_demo()
    matrix = model.stress_matrix()
    assert len(matrix) == 4
    assert all(s["evidence_level"] == "ASSUMED_STRESS" for s in matrix)
