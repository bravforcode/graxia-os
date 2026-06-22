"""Tests for demo canary config."""
from graxia.packages.quant_os.canary.demo_canary_config import DemoCanaryConfig


def test_config_creates():
    config = DemoCanaryConfig()
    ok, issues = config.validate()
    assert ok


def test_config_rejects_live():
    config = DemoCanaryConfig(account_mode="LIVE")
    ok, issues = config.validate()
    assert not ok
    assert any("DEMO" in i for i in issues)


def test_config_rejects_multiple_symbols():
    config = DemoCanaryConfig(symbols=["XAUUSD", "EURUSD"])
    ok, issues = config.validate()
    assert not ok


def test_config_rejects_blind_retry():
    config = DemoCanaryConfig(blind_retry_allowed=True)
    ok, issues = config.validate()
    assert not ok


def test_config_to_dict():
    config = DemoCanaryConfig()
    d = config.to_dict()
    assert d["account_mode"] == "DEMO"
    assert d["kill_switch_enabled"] is True
