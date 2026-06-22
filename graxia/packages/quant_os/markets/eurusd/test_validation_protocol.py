"""Tests for EURUSD validation protocol."""
from graxia.packages.quant_os.markets.eurusd.validation_protocol import EURUSDValidationProtocol


def test_protocol_creates():
    proto = EURUSDValidationProtocol()
    assert len(proto.get_checks()) == 8


def test_protocol_passes_all():
    proto = EURUSDValidationProtocol()
    evidence = {c.check_name: True for c in proto.get_checks()}
    ok, issues = proto.validate(evidence)
    assert ok


def test_protocol_fails_missing():
    proto = EURUSDValidationProtocol()
    evidence = {"separate_dataset": True, "separate_contract": True}
    ok, issues = proto.validate(evidence)
    assert not ok
    assert len(issues) > 0


def test_protocol_fails_xauusd_transfer():
    proto = EURUSDValidationProtocol()
    evidence = {c.check_name: True for c in proto.get_checks()}
    evidence["no_xauusd_transfer"] = False
    ok, issues = proto.validate(evidence)
    assert not ok
    assert any("no_xauusd_transfer" in i for i in issues)
