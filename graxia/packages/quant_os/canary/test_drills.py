"""Tests for drill definitions."""
from graxia.packages.quant_os.canary.drills import DrillType, DrillResult, DrillExecutor


def test_drill_types():
    assert len(DrillType) == 13


def test_drill_executor_pass():
    executor = DrillExecutor()
    result = DrillResult(
        drill_type="kill_switch", detection_time_ms=50,
        new_order_blocked=True, existing_position_behavior="no_change",
        alert_delivered=True, recovery_verified=True,
        evidence_retained=True, postmortem_status="resolved",
    )
    executor.execute_drill(DrillType.KILL_SWITCH, result)
    assert result.passed
    assert executor.summary()["passed"] == 1


def test_drill_executor_fail_detection_time():
    executor = DrillExecutor()
    result = DrillResult(
        drill_type="kill_switch", detection_time_ms=500,  # > 100ms
        new_order_blocked=True, existing_position_behavior="no_change",
        alert_delivered=True, recovery_verified=True,
        evidence_retained=True, postmortem_status="resolved",
    )
    executor.execute_drill(DrillType.KILL_SWITCH, result)
    assert not result.passed


def test_drill_executor_fail_no_block():
    executor = DrillExecutor()
    result = DrillResult(
        drill_type="kill_switch", detection_time_ms=50,
        new_order_blocked=False,  # should block
        existing_position_behavior="no_change",
        alert_delivered=True, recovery_verified=True,
        evidence_retained=True, postmortem_status="resolved",
    )
    executor.execute_drill(DrillType.KILL_SWITCH, result)
    assert not result.passed
