"""Phase 8 integration tests — demo campaign and incident drills."""
from graxia.packages.quant_os.canary.drills.drill_definitions import DRILL_CATALOG, DrillType
from graxia.packages.quant_os.canary.drills.drill_executor import DrillExecutor
from graxia.packages.quant_os.canary.demo_scorecard import DemoScorecard


def test_drill_catalog_has_required_types():
    """Drill catalog must have core drill types."""
    required = {DrillType.KILL_SWITCH, DrillType.MT5_DISCONNECT, DrillType.STALE_TICK, DrillType.SPREAD_SHOCK}
    assert required.issubset(set(DRILL_CATALOG.keys()))


def test_drill_executor_works():
    """DrillExecutor must execute drills."""
    executor = DrillExecutor()

    def dummy_drill():
        pass

    executor.register_drill(DrillType.KILL_SWITCH, dummy_drill)
    result = executor.execute(DrillType.KILL_SWITCH)
    assert result.passed


def test_demo_scorecard_works():
    """DemoScorecard must evaluate correctly when no issues."""
    scorecard = DemoScorecard(
        protective_stop_verification_rate_pct=100,
        position_deal_reconciliation_rate_pct=100,
    )
    result = scorecard.evaluate()
    assert result["passed"] is True


def test_demo_scorecard_fails_on_incidents():
    """DemoScorecard must fail on critical incidents."""
    scorecard = DemoScorecard(critical_incidents=1)
    result = scorecard.evaluate()
    assert result["passed"] is False


def test_all_catalog_drills_have_definitions():
    """Every drill in catalog must have a complete definition."""
    for drill_type, defn in DRILL_CATALOG.items():
        assert defn.name
        assert defn.description
        assert defn.steps
        assert defn.expected_outcome
