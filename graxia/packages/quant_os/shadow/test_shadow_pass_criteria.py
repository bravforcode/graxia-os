"""Tests for shadow pass criteria."""
from graxia.packages.quant_os.shadow.shadow_pass_criteria import ShadowPassCriteria


def test_criteria_creates():
    c = ShadowPassCriteria()
    assert c is not None


def test_criteria_all_pass():
    c = ShadowPassCriteria()
    metrics = {
        "order_count": 0, "stale_feed_count": 0, "event_bypass_count": 0,
        "has_contract_snapshot": True, "ledger_sealed": True,
        "critical_exception_count": 0, "heartbeat_count": 10,
        "unresolved_incidents": 0,
    }
    checks = c.evaluate(metrics)
    assert c.all_passed()
    assert len(checks) == 8


def test_criteria_fails_on_order():
    c = ShadowPassCriteria()
    metrics = {
        "order_count": 1, "stale_feed_count": 0, "event_bypass_count": 0,
        "has_contract_snapshot": True, "ledger_sealed": True,
        "critical_exception_count": 0, "heartbeat_count": 10,
        "unresolved_incidents": 0,
    }
    c.evaluate(metrics)
    assert not c.all_passed()
    failed = c.get_failed()
    assert len(failed) == 1
    assert failed[0].check_name == "no_order_operation"


def test_criteria_multiple_failures():
    c = ShadowPassCriteria()
    metrics = {"order_count": 1, "stale_feed_count": 2}
    c.evaluate(metrics)
    assert not c.all_passed()
    assert c.summary()["failed"] >= 2
