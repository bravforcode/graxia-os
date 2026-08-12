"""Verify EURUSD contract snapshot."""
from decimal import Decimal

from graxia.packages.quant_os.markets.eurusd.contract_snapshot import EURUSDContractSnapshot


def test_contract_size():
    c = EURUSDContractSnapshot()
    assert c.contract_size == 100000


def test_tick_size():
    c = EURUSDContractSnapshot()
    assert c.tick_size == Decimal("0.00001")


def test_fingerprint_deterministic():
    c1 = EURUSDContractSnapshot()
    c2 = EURUSDContractSnapshot()
    assert c1.fingerprint() == c2.fingerprint()


def test_validate_passes():
    c = EURUSDContractSnapshot()
    ok, issues = c.validate()
    assert ok is True


def test_validate_fails_zero_tick():
    c = EURUSDContractSnapshot(tick_size=Decimal("0"))
    ok, issues = c.validate()
    assert ok is False
