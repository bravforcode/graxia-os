import pytest
from graxia.packages.quant_os.markets.eurusd.contract_snapshot import EURUSDContractSnapshot, XAUUSDContractSnapshot
from graxia.packages.quant_os.markets.eurusd.session_calendar import get_active_session, is_liquidity_session, SessionType
from graxia.packages.quant_os.markets.eurusd.event_calendar import get_event_blackout, get_high_impact_events, EventImpact
from graxia.packages.quant_os.markets.eurusd.hypothesis import (
    EURUSDHypothesis, HypothesisRegistry, HypothesisStatus, ValidationProtocol
)

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
        assert get_active_session(10) == SessionType.LONDON
    
    def test_ny_session(self):
        assert get_active_session(18) == SessionType.NEW_YORK
    
    def test_overlap_session(self):
        assert get_active_session(14) == SessionType.LONDON_NY_OVERLAP
    
    def test_asian_session(self):
        assert get_active_session(3) == SessionType.ASIAN
    
    def test_off_hours(self):
        assert get_active_session(22) == SessionType.OFF_HOURS
    
    def test_liquidity_london(self):
        assert is_liquidity_session(10) is True
    
    def test_liquidity_off_hours(self):
        assert is_liquidity_session(22) is False

class TestEventCalendar:
    def test_nfp_blackout(self):
        before, after = get_event_blackout("NFP")
        assert before == 30
        assert after == 15
    
    def test_unknown_event_default(self):
        before, after = get_event_blackout("UnknownEvent")
        assert before == 15
    
    def test_high_impact_count(self):
        events = get_high_impact_events()
        assert len(events) >= 5

class TestHypothesis:
    def test_create(self):
        h = EURUSDHypothesis(
            hypothesis_id="EURUSD-HYP-001",
            economic_rationale="USD strength during rate hike cycle",
            entry_logic="Breakout above Asian range",
            exit_logic="Trailing stop 2x ATR",
            stop_logic="Below session low",
            take_profit_or_time_stop="3x risk or 4h time stop",
        )
        assert h.is_active() is False
    
    def test_activate(self):
        h = EURUSDHypothesis(
            hypothesis_id="EURUSD-HYP-001",
            economic_rationale="test",
            entry_logic="test",
            exit_logic="test",
            stop_logic="test",
        )
        h.activate()
        assert h.status == HypothesisStatus.ACTIVE
    
    def test_fingerprint(self):
        h = EURUSDHypothesis(
            hypothesis_id="EURUSD-HYP-001",
            economic_rationale="test",
            entry_logic="test",
            exit_logic="test",
            stop_logic="test",
        )
        assert len(h.fingerprint()) == 64

class TestHypothesisRegistry:
    def test_register(self):
        reg = HypothesisRegistry()
        h = EURUSDHypothesis(
            hypothesis_id="EURUSD-HYP-001",
            economic_rationale="test",
            entry_logic="test",
            exit_logic="test",
            stop_logic="test",
        )
        ok, msg = reg.register(h)
        assert ok is True
    
    def test_only_one_active(self):
        reg = HypothesisRegistry()
        h1 = EURUSDHypothesis(
            hypothesis_id="H1", economic_rationale="r", entry_logic="e",
            exit_logic="x", stop_logic="s", status=HypothesisStatus.ACTIVE,
        )
        h2 = EURUSDHypothesis(
            hypothesis_id="H2", economic_rationale="r", entry_logic="e",
            exit_logic="x", stop_logic="s", status=HypothesisStatus.ACTIVE,
        )
        reg.register(h1)
        ok, msg = reg.register(h2)
        assert ok is False
        assert "ACTIVE_EXISTS" in msg
    
    def test_get_active(self):
        reg = HypothesisRegistry()
        h = EURUSDHypothesis(
            hypothesis_id="H1", economic_rationale="r", entry_logic="e",
            exit_logic="x", stop_logic="s", status=HypothesisStatus.ACTIVE,
        )
        reg.register(h)
        assert reg.get_active() is not None

class TestValidationProtocol:
    def test_pass(self):
        proto = ValidationProtocol()
        ok, issues = proto.evaluate({"total_trades": 50, "oos_trades": 20, "max_drawdown_pct": 10, "sharpe_ratio": 1.0, "profit_factor": 1.5})
        assert ok is True
    
    def test_fail_min_trades(self):
        proto = ValidationProtocol()
        ok, issues = proto.evaluate({"total_trades": 5, "oos_trades": 20, "max_drawdown_pct": 10, "sharpe_ratio": 1.0, "profit_factor": 1.5})
        assert ok is False
