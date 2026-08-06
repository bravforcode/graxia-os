# tests/test_partition_registry.py
from research.partition_registry import PARTITION_RULES, check_partition


def test_forex4_trend_continuity_closed():
    r = check_partition("trend_continuity", "USDCAD", "H1")
    assert r["status"] == "CLOSED"
    assert r["owner"] == "H"


def test_forex4_rsi_mr_watch():
    r = check_partition("rsi_mean_reversion", "AUDUSD", "H1")
    assert r["status"] == "WATCH"
    assert r["owner"] == "H"


def test_eurusd_h4_watch():
    r = check_partition("tf_probe_family", "EURUSD", "H4")
    assert r["status"] == "WATCH"


def test_unrelated_mechanism_free():
    r = check_partition("gold_scalper", "XAUUSD", "M15")
    assert r["status"] == "FREE"
    assert r["owner"] is None


def test_partition_rules_machine_checkable():
    for rule in PARTITION_RULES:
        assert {"status", "owner", "match"} <= set(rule.keys())
        assert rule["status"] in {"CLOSED", "WATCH"}
