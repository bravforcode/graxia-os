"""Phase BE-P13 integration tests — controlled expansion (FINAL PHASE)."""
from graxia.packages.quant_os.expansion.expansion_planner import (
    ExpansionPlanner, ExpansionRequest, ExpansionTier
)
from graxia.packages.quant_os.expansion.expansion_tracker import ExpansionTracker, ExpansionRecord
from graxia.packages.quant_os.expansion.forbidden_guard import ForbiddenExpansionGuard
from graxia.packages.quant_os.expansion.readiness_check import ExpansionReadiness


def test_planner_progression():
    planner = ExpansionPlanner()
    request = ExpansionRequest(target_tier="tier_2", justification="one additional strategy")
    decision = planner.evaluate(request)
    assert decision.approved


def test_planner_forbidden_blocked():
    planner = ExpansionPlanner()
    request = ExpansionRequest(
        target_tier="tier_2",
        justification="raising risk on win streak",
    )
    decision = planner.evaluate(request)
    assert not decision.approved


def test_tracker_records():
    tracker = ExpansionTracker()
    tracker.record(ExpansionRecord(
        tier="tier_1", strategy_id="XAU", justification="proven", approved=True,
    ))
    assert tracker.summary()["approved"] == 1


def test_forbidden_guard_blocks():
    guard = ForbiddenExpansionGuard()
    assert not guard.is_clean("mixing crypto and fx")


def test_readiness_all_pass():
    r = ExpansionReadiness()
    context = {
        "current_tier_proven": True, "safety_incidents": 0,
        "risk_breaches": 0, "broker_identity_locked": True, "cost_gap_pct": 20,
    }
    assert r.all_passed(context)


def test_full_expansion_flow():
    """Complete expansion flow: planner -> tracker -> guard -> readiness."""
    planner = ExpansionPlanner("tier_1")
    tracker = ExpansionTracker()
    guard = ForbiddenExpansionGuard()
    readiness = ExpansionReadiness()

    # Check readiness
    assert readiness.all_passed({
        "current_tier_proven": True, "safety_incidents": 0,
        "risk_breaches": 0, "broker_identity_locked": True, "cost_gap_pct": 20,
    })

    # Check forbidden
    assert guard.is_clean("add one more strategy")

    # Plan expansion
    request = ExpansionRequest(target_tier="tier_2", justification="add one more strategy")
    decision = planner.evaluate(request)
    assert decision.approved

    # Record
    tracker.record(ExpansionRecord(
        tier="tier_2", strategy_id="NEW_STRAT",
        justification="add one more strategy", approved=True,
    ))
    assert tracker.summary()["approved"] == 1
