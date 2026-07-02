"""Phase 8 — Drill framework tests."""
from graxia.packages.quant_os.canary.drills.drill_definitions import (
    DrillType,
    DrillDefinition,
    DRILL_CATALOG,
)
from graxia.packages.quant_os.canary.drills.drill_executor import DrillExecutor


def test_drill_catalog_exists():
    assert len(DRILL_CATALOG) >= 4
    for dt in [DrillType.KILL_SWITCH, DrillType.MT5_DISCONNECT, DrillType.STALE_TICK, DrillType.SPREAD_SHOCK]:
        assert dt in DRILL_CATALOG
        assert isinstance(DRILL_CATALOG[dt], DrillDefinition)
        assert DRILL_CATALOG[dt].drill_type == dt


def test_drill_executor_instantiate():
    executor = DrillExecutor()
    summary = executor.get_summary()
    assert summary["total"] == 0
    assert summary["verdict"] == "PASS"


def test_drill_executor_register_and_execute():
    executor = DrillExecutor()
    calls = []

    def fake_drill():
        calls.append("executed")

    executor.register_drill(DrillType.KILL_SWITCH, fake_drill)
    result = executor.execute(DrillType.KILL_SWITCH)

    assert result.passed is True
    assert result.drill_type == DrillType.KILL_SWITCH
    assert result.duration_seconds >= 0
    assert calls == ["executed"]


def test_drill_executor_execute_all():
    executor = DrillExecutor()
    count = []

    def fake_drill():
        count.append(1)

    for dt in DRILL_CATALOG:
        executor.register_drill(dt, fake_drill)

    results = executor.execute_all()
    assert len(results) == len(DRILL_CATALOG)
    assert all(r.passed for r in results)
    assert len(count) == len(DRILL_CATALOG)


def test_drill_summary():
    executor = DrillExecutor()
    executor.register_drill(DrillType.KILL_SWITCH, lambda: None)
    executor.execute(DrillType.KILL_SWITCH)

    summary = executor.get_summary()
    assert summary["total"] == 1
    assert summary["passed"] == 1
    assert summary["failed"] == 0
    assert summary["verdict"] == "PASS"
