"""Phase 4 EURUSD module tests.

RESTORED from deleted test_phase_4_eurusd.py (BE-P7 commit 3ae373f).
Original deleted because API changed; migrated to current API.
"""
from graxia.packages.quant_os.markets.eurusd.contract_snapshot import EURUSDContractSnapshot, XAUUSDContractSnapshot
from graxia.packages.quant_os.markets.eurusd.session_calendar import EURUSDSessionCalendar
from graxia.packages.quant_os.markets.eurusd.event_calendar import EURUSDEventCalendar
from graxia.packages.quant_os.markets.eurusd.hypothesis import EURUSDHypothesis, HypothesisTracker


class TestEURUSDContract:
    def test_fingerprint_deterministic(self):
        c = EURUSDContractSnapshot()
        assert c.fingerprint() == c.fingerprint()

    def test_validate_valid(self):
        c = EURUSDContractSnapshot()
        valid, issues = c.validate()
        assert valid is True

    def test_validate_zero_tick(self):
        from decimal import Decimal
        c = EURUSDContractSnapshot(tick_size=Decimal("0"))
        valid, issues = c.validate()
        assert valid is False

    def test_xauusd_different(self):
        xau = XAUUSDContractSnapshot()
        eur = EURUSDContractSnapshot()
        assert xau.contract_size != eur.contract_size


class TestSessionCalendar:
    def test_london_session(self):
        cal = EURUSDSessionCalendar()
        sessions = cal.get_active_sessions(10)
        assert any(s.name == "london" for s in sessions)

    def test_ny_session(self):
        cal = EURUSDSessionCalendar()
        sessions = cal.get_active_sessions(18)
        assert any(s.name == "new_york" for s in sessions)

    def test_overlap_session(self):
        cal = EURUSDSessionCalendar()
        sessions = cal.get_active_sessions(14)
        assert any(s.name == "overlap_london_ny" for s in sessions)

    def test_asian_session(self):
        cal = EURUSDSessionCalendar()
        sessions = cal.get_active_sessions(3)
        assert any(s.name == "asian" for s in sessions)

    def test_off_hours(self):
        cal = EURUSDSessionCalendar()
        sessions = cal.get_active_sessions(22)
        assert len(sessions) == 0

    def test_liquidity_london(self):
        cal = EURUSDSessionCalendar()
        sessions = cal.get_active_sessions(10)
        assert any(s.typical_volume == "high" for s in sessions)

    def test_liquidity_off_hours(self):
        cal = EURUSDSessionCalendar()
        assert cal.is_session_open(22) is False


class TestEventCalendar:
    def test_event_calendar_exists(self):
        cal = EURUSDEventCalendar()
        assert cal is not None

    def test_high_impact_events(self):
        cal = EURUSDEventCalendar()
        events = cal.get_high_impact()
        assert len(events) >= 5

    def test_events_by_currency(self):
        cal = EURUSDEventCalendar()
        usd_events = cal.get_by_currency("USD")
        assert len(usd_events) >= 3


class TestHypothesis:
    def test_create(self):
        h = EURUSDHypothesis(
            hypothesis_id="EURUSD-HYP-001",
            rationale="USD strength during rate hike cycle",
        )
        ok, issues = h.validate()
        assert ok is True

    def test_validate_requires_id(self):
        h = EURUSDHypothesis(rationale="test")
        ok, issues = h.validate()
        assert ok is False
        assert any("hypothesis_id" in i for i in issues)

    def test_validate_requires_rationale(self):
        h = EURUSDHypothesis(hypothesis_id="HYP-001")
        ok, issues = h.validate()
        assert ok is False
        assert any("rationale" in i for i in issues)

    def test_compute_hash(self):
        h = EURUSDHypothesis(hypothesis_id="HYP-001", rationale="test")
        assert len(h.compute_hash()) == 64

    def test_to_from_dict(self):
        h = EURUSDHypothesis(hypothesis_id="HYP-001", rationale="test")
        d = h.to_dict()
        h2 = EURUSDHypothesis.from_dict(d)
        assert h2.hypothesis_id == "HYP-001"


class TestHypothesisTracker:
    def test_activate(self):
        t = HypothesisTracker()
        t.activate("HYP-001")
        assert t.get_active() == "HYP-001"

    def test_archive(self):
        t = HypothesisTracker()
        t.activate("HYP-001")
        t.archive("HYP-001", "no edge")
        assert t.get_active() == ""
        assert "HYP-001" in t.archived_hypotheses

    def test_activate_replaces(self):
        t = HypothesisTracker()
        t.activate("HYP-001")
        t.activate("HYP-002")
        assert t.get_active() == "HYP-002"
        assert "HYP-001" in t.archived_hypotheses
