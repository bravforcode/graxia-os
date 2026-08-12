"""Tests for micro-live policy."""
from graxia.packages.quant_os.micro_live.micro_live_policy import MicroLivePolicy


def test_policy_creates():
    p = MicroLivePolicy()
    ok, issues = p.validate()
    assert ok


def test_policy_rejects_multiple_symbols():
    p = MicroLivePolicy(symbol_count=2)
    ok, issues = p.validate()
    assert not ok


def test_policy_rejects_compounding():
    p = MicroLivePolicy(compounding="allowed")
    ok, issues = p.validate()
    assert not ok


def test_policy_to_dict():
    p = MicroLivePolicy()
    d = p.to_dict()
    assert d["symbol_count"] == 1
    assert d["kill_switch"] == "required"
