"""Tests for expansion planner."""

from graxia.packages.quant_os.expansion.expansion_planner import ExpansionPlanner, ExpansionRequest


def test_planner_creates():
    planner = ExpansionPlanner()
    assert planner.get_current_tier() == "tier_1"


def test_planner_allows_progression():
    planner = ExpansionPlanner()
    request = ExpansionRequest(target_tier="tier_2", justification="one additional strategy")
    decision = planner.evaluate(request)
    assert decision.approved


def test_planner_rejects_forbidden():
    planner = ExpansionPlanner()
    request = ExpansionRequest(
        target_tier="tier_2",
        justification="raising risk on win streak",
    )
    decision = planner.evaluate(request)
    assert not decision.approved
    assert any("forbidden" in v for v in decision.violations)


def test_planner_rejects_tier_skip():
    planner = ExpansionPlanner()
    request = ExpansionRequest(
        target_tier="tier_5",
        justification="portfolio risk budget",
    )
    decision = planner.evaluate(request)
    assert not decision.approved
    assert any("tier_skip" in v for v in decision.violations)


def test_planner_advance():
    planner = ExpansionPlanner()
    assert planner.advance_tier() == "tier_2"
    assert planner.advance_tier() == "tier_3"
