"""Tests for cost stress analyzer."""
from graxia.packages.quant_os.cost.cost_stress_analyzer import CostStressAnalyzer


def test_analyzer_creates():
    analyzer = CostStressAnalyzer()
    assert analyzer is not None


def test_analyzer_default_scenarios():
    analyzer = CostStressAnalyzer.default_scenarios()
    results = analyzer.analyze(strategy_pnl_per_trade=5.0)
    assert len(results) == 4
    assert results[0].scenario_name == "base"
    assert results[0].cost_increase_pct == 0.0


def test_analyzer_stress_increases_cost():
    analyzer = CostStressAnalyzer(base_cost=3.5)
    analyzer.add_scenario("stress", 2.0)
    results = analyzer.analyze()
    assert results[0].total_cost_after > results[0].total_cost_before


def test_analyzer_sensitivity_high():
    analyzer = CostStressAnalyzer(base_cost=3.5)
    analyzer.add_scenario("extreme", 3.0)
    results = analyzer.analyze(strategy_pnl_per_trade=1.0)
    assert results[0].sensitivity == "HIGH"


def test_analyzer_sensitivity_low():
    analyzer = CostStressAnalyzer(base_cost=3.5)
    analyzer.add_scenario("mild", 1.2)
    results = analyzer.analyze(strategy_pnl_per_trade=10.0)
    assert results[0].sensitivity == "LOW"
