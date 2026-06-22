"""Phase BE-P7 integration tests — EURUSD clean research foundation."""
from graxia.packages.quant_os.markets.eurusd.hypothesis import EURUSDHypothesis, HypothesisTracker
from graxia.packages.quant_os.markets.eurusd.anti_contamination import AntiContaminationGuard
from graxia.packages.quant_os.markets.eurusd.session_calendar import EURUSDSessionCalendar
from graxia.packages.quant_os.markets.eurusd.event_calendar import EURUSDEventCalendar
from graxia.packages.quant_os.markets.eurusd.validation_protocol import EURUSDValidationProtocol


def test_hypothesis_full_lifecycle():
    h = EURUSDHypothesis(
        hypothesis_id="EURUSD-HYP-001",
        rationale="ECB rate differential drives mean reversion",
    )
    ok, issues = h.validate()
    assert ok
    h2 = EURUSDHypothesis.from_dict(h.to_dict())
    assert h2.hypothesis_id == "EURUSD-HYP-001"
    assert h.compute_hash() == h2.compute_hash()


def test_tracker_lifecycle():
    tracker = HypothesisTracker()
    tracker.activate("EURUSD-HYP-001")
    assert tracker.get_active() == "EURUSD-HYP-001"
    tracker.activate("EURUSD-HYP-002")
    assert tracker.get_active() == "EURUSD-HYP-002"
    assert "EURUSD-HYP-001" in tracker.archived_hypotheses


def test_anti_contamination_blocks():
    guard = AntiContaminationGuard()
    check = guard.check_transfer("XAUUSD", "EURUSD", "threshold_1")
    assert check.is_contaminated
    assert not guard.is_clean()


def test_anti_contamination_allows_hypothesis():
    guard = AntiContaminationGuard()
    check = guard.check_transfer("XAUUSD", "EURUSD", "hypothesis_new")
    assert not check.is_contaminated


def test_session_calendar():
    cal = EURUSDSessionCalendar()
    assert cal.is_session_open(10)  # London
    assert not cal.is_session_open(22)  # Closed


def test_event_calendar():
    cal = EURUSDEventCalendar()
    high = cal.get_high_impact()
    assert len(high) >= 6


def test_validation_protocol():
    proto = EURUSDValidationProtocol()
    evidence = {c.check_name: True for c in proto.get_checks()}
    ok, issues = proto.validate(evidence)
    assert ok


def test_validation_protocol_fails():
    proto = EURUSDValidationProtocol()
    evidence = {}
    ok, issues = proto.validate(evidence)
    assert not ok
    assert len(issues) == 8
