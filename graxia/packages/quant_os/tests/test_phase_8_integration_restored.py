"""Phase 8 integration tests — demo campaign and incident drills.

RESTORED from deleted test_phase_8_integration.py (BE-P10 commit ae946c6).
Migrated to current API. Scorecard tests quarantined (see QUARANTINE_MANIFEST.md).
"""
from graxia.packages.quant_os.canary.drills.drill_definitions import DRILL_CATALOG, DrillType
from graxia.packages.quant_os.canary.drills.drill_executor import DrillExecutor


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


def test_all_catalog_drills_have_definitions():
    """Every drill in catalog must have a complete definition."""
    for drill_type, defn in DRILL_CATALOG.items():
        assert defn.name
        assert defn.description
        assert defn.steps
        assert defn.expected_outcome
