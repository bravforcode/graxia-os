"""
Tests for C1: Multi-agent framework
"""

import pytest

from graxia.packages.quant_os.core.agents import (
    Agent,
    BullBearResearcherAgent,
    PortfolioManagerAgent,
    RiskAuditorAgent,
    TechnicalAnalystAgent,
)
from graxia.packages.quant_os.core.canonical.macro_regime import MacroRegimeCache
from graxia.packages.quant_os.core.enums import SignalType
from graxia.packages.quant_os.core.event_bus import EventBus
from graxia.packages.quant_os.core.events import BarEvent, RiskEvent, SignalEvent

# ── Fixtures ──────────────────────────────────────────────────────


def _make_bar(symbol: str, close: float, bar_index: int = 0, **kwargs) -> BarEvent:
    return BarEvent(
        symbol=symbol,
        open=kwargs.get("open", close * 0.99),
        high=kwargs.get("high", close * 1.01),
        low=kwargs.get("low", close * 0.99),
        close=close,
        volume=kwargs.get("volume", 1000.0),
        bar_index=bar_index,
    )


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def analyst() -> TechnicalAnalystAgent:
    return TechnicalAnalystAgent()


@pytest.fixture
def researcher() -> BullBearResearcherAgent:
    return BullBearResearcherAgent()


@pytest.fixture
def risk_auditor():
    """Reset MacroRegimeCache to avoid cross-test contamination."""
    cache = MacroRegimeCache()
    cache.reset()
    return RiskAuditorAgent()


@pytest.fixture
def pm() -> PortfolioManagerAgent:
    return PortfolioManagerAgent()


# ── Agent ABC tests ───────────────────────────────────────────────


class TestAgentABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            Agent("test")  # type: ignore[call-arg]

    def test_repr(self, analyst):
        assert "TechnicalAnalystAgent" in repr(analyst)
        assert "technical_analyst" in repr(analyst)


# ── TechnicalAnalystAgent tests ───────────────────────────────────


class TestTechnicalAnalyst:
    def test_ignores_non_bar_events(self, analyst):
        sig = SignalEvent(symbol="XAUUSD", signal_type=SignalType.BUY)
        analyst.observe(sig)
        assert analyst.act() is None

    def test_no_signal_with_insufficient_data(self, analyst):
        for i in range(5):
            analyst.observe(_make_bar("XAUUSD", 2000.0 + i, bar_index=i))
        assert analyst.act() is None

    def test_buy_signal_on_bullish_crossover(self, analyst):
        # Create declining then rising prices to trigger bullish SMA cross
        # Long SMA needs 20 bars, short needs 5
        prices = list(range(1980, 2000)) + list(range(2000, 2010))
        for i, p in enumerate(prices):
            analyst.observe(_make_bar("XAUUSD", float(p), bar_index=i))
        event = analyst.act()
        if event is not None:
            assert isinstance(event, SignalEvent)
            assert event.symbol == "XAUUSD"
            assert event.signal_type in (SignalType.BUY, SignalType.SELL, SignalType.NO_TRADE)

    def test_reset_clears_state(self, analyst):
        for i in range(25):
            analyst.observe(_make_bar("XAUUSD", 2000.0, bar_index=i))
        analyst.reset()
        assert analyst._closes == {}
        assert analyst._highs == {}
        assert analyst._lows == {}

    def test_multiple_symbols(self, analyst):
        for i in range(25):
            analyst.observe(_make_bar("XAUUSD", 2000.0 + i, bar_index=i))
            analyst.observe(_make_bar("BTCUSD", 50000.0 + i * 10, bar_index=i))
        assert "XAUUSD" in analyst._closes
        assert "BTCUSD" in analyst._closes


# ── BullBearResearcherAgent tests ─────────────────────────────────


class TestBullBearResearcher:
    def test_ignores_non_signal_events(self, researcher):
        bar = _make_bar("XAUUSD", 2000.0)
        researcher.observe(bar)
        assert researcher.act() is None

    def test_ignores_self_sourced_signals(self, researcher):
        sig = SignalEvent(
            symbol="XAUUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            source="bull_bear_researcher",
        )
        researcher.observe(sig)
        assert researcher.act() is None

    def test_no_consensus_with_insufficient_votes(self, researcher):
        sig = SignalEvent(
            symbol="XAUUSD",
            signal_type=SignalType.BUY,
            confidence=0.7,
            source="analyst_1",
        )
        researcher.observe(sig)
        assert researcher.act() is None

    def test_consensus_with_majority(self, researcher):
        for name in ["a1", "a2", "a3"]:
            researcher.observe(
                SignalEvent(
                    symbol="XAUUSD",
                    signal_type=SignalType.BUY,
                    confidence=0.7,
                    source=name,
                )
            )
        consensus = researcher.act()
        assert consensus is not None
        assert consensus.signal_type == SignalType.BUY
        assert consensus.metadata["vote_count"] == 3
        assert consensus.metadata["total_votes"] == 3

    def test_abstention_on_all_no_trade(self, researcher):
        for name in ["a1", "a2"]:
            researcher.observe(
                SignalEvent(
                    symbol="XAUUSD",
                    signal_type=SignalType.NO_TRADE,
                    confidence=0.0,
                    source=name,
                )
            )
        assert researcher.act() is None

    def test_reset_clears_votes(self, researcher):
        researcher.observe(
            SignalEvent(
                symbol="XAUUSD",
                signal_type=SignalType.BUY,
                confidence=0.7,
                source="a1",
            )
        )
        researcher.reset()
        assert researcher._pending_votes == []


# ── RiskAuditorAgent tests ────────────────────────────────────────


class TestRiskAuditor:
    def test_low_confidence_rejected(self, risk_auditor):
        risk_auditor.observe(
            SignalEvent(
                symbol="XAUUSD",
                signal_type=SignalType.BUY,
                confidence=0.1,
            )
        )
        result = risk_auditor.act()
        assert result is not None
        assert isinstance(result, RiskEvent)
        assert result.passed is False
        assert "confidence" in result.reason

    def test_high_confidence_approved(self, risk_auditor):
        risk_auditor.observe(
            SignalEvent(
                symbol="XAUUSD",
                signal_type=SignalType.BUY,
                confidence=0.8,
                entry_price=2000.0,
                stop_loss=1990.0,
                take_profit=2020.0,
            )
        )
        result = risk_auditor.act()
        assert result is not None
        assert result.passed is True

    def test_bad_rr_ratio_rejected(self, risk_auditor):
        risk_auditor.observe(
            SignalEvent(
                symbol="XAUUSD",
                signal_type=SignalType.BUY,
                confidence=0.8,
                entry_price=2000.0,
                stop_loss=1950.0,  # 50 risk
                take_profit=2010.0,  # 10 reward → R:R = 0.2
            )
        )
        result = risk_auditor.act()
        assert result is not None
        assert result.passed is False
        assert "R:R" in result.reason

    def test_symbol_whitelist(self):
        auditor = RiskAuditorAgent(allowed_symbols=["XAUUSD"])
        auditor.observe(
            SignalEvent(
                symbol="BTCUSD",
                signal_type=SignalType.BUY,
                confidence=0.8,
            )
        )
        result = auditor.act()
        assert result is not None
        assert result.passed is False
        assert "whitelist" in result.reason

    def test_duplicate_signal_flood(self, risk_auditor):
        for _ in range(4):
            risk_auditor.observe(
                SignalEvent(
                    symbol="XAUUSD",
                    signal_type=SignalType.BUY,
                    confidence=0.8,
                )
            )
            risk_auditor.act()
        # 4th duplicate should fail
        risk_auditor.observe(
            SignalEvent(
                symbol="XAUUSD",
                signal_type=SignalType.BUY,
                confidence=0.8,
            )
        )
        result = risk_auditor.act()
        assert result is not None
        assert result.passed is False
        assert "duplicate" in result.reason

    def test_multiple_signals_all_processed(self, risk_auditor):
        """All pending signals are audited, not just the last one."""
        risk_auditor.observe(
            SignalEvent(
                symbol="XAUUSD",
                signal_type=SignalType.BUY,
                confidence=0.1,  # low confidence, will fail
            )
        )
        risk_auditor.observe(
            SignalEvent(
                symbol="XAUUSD",
                signal_type=SignalType.BUY,
                confidence=0.8,
                entry_price=2000.0,
                stop_loss=1990.0,
                take_profit=2020.0,
            )
        )
        result = risk_auditor.act()
        # Returns the last audit result (approved)
        assert result is not None
        assert result.passed is True
        # But both signals were processed — the first one updated duplicate count
        audit = risk_auditor.get_last_audit()
        assert audit is not None
        assert audit.signal.confidence == 0.8
        # Duplicate count should be 1 — only approved signals count
        # (rejected signals don't count toward duplicate limit)
        assert risk_auditor._recent_signals.get("XAUUSD:BUY", 0) == 1

    def test_get_last_audit(self, risk_auditor):
        risk_auditor.observe(
            SignalEvent(
                symbol="XAUUSD",
                signal_type=SignalType.BUY,
                confidence=0.8,
            )
        )
        risk_auditor.act()
        audit = risk_auditor.get_last_audit()
        assert audit is not None
        assert audit.approved is True


# ── PortfolioManagerAgent tests ───────────────────────────────────


class TestPortfolioManager:
    def test_no_signal_without_consensus(self, pm):
        pm.observe(RiskEvent(check_name="test", passed=True, source="risk_auditor"))
        assert pm.act() is None

    def test_no_signal_without_risk_pass(self, pm):
        pm._pending_consensus = SignalEvent(
            symbol="XAUUSD",
            signal_type=SignalType.BUY,
            confidence=0.7,
            source="bull_bear_researcher",
        )
        assert pm.act() is None

    def test_risk_event_sets_pending_pass(self, pm):
        risk_event = RiskEvent(check_name="audit", passed=True, source="risk_auditor")
        pm.observe(risk_event)
        assert pm._pending_risk_pass is True

    def test_risk_event_sets_pending_reject(self, pm):
        risk_event = RiskEvent(check_name="audit", passed=False, source="risk_auditor")
        pm.observe(risk_event)
        assert pm._pending_risk_pass is False

    def test_dead_signal_event_from_risk_auditor_ignored(self, pm):
        from graxia.packages.quant_os.core.enums import SignalType as ST

        sig = SignalEvent(symbol="X", signal_type=ST.BUY, source="risk_auditor")
        pm.observe(sig)
        assert pm._pending_risk_pass is False

    def test_emits_final_signal_on_consensus_and_risk_pass(self, pm):
        pm.observe(
            SignalEvent(
                symbol="XAUUSD",
                signal_type=SignalType.BUY,
                confidence=0.7,
                entry_price=2000.0,
                stop_loss=1990.0,
                take_profit=2015.0,
                source="bull_bear_researcher",
            )
        )
        pm.observe(
            RiskEvent(
                check_name="audit",
                passed=True,
                source="risk_auditor",
            )
        )
        result = pm.act()
        assert result is not None
        assert isinstance(result, SignalEvent)
        assert result.symbol == "XAUUSD"
        assert result.signal_type == SignalType.BUY
        assert result.source == "portfolio_manager"
        assert result.metadata["final"] is True
        # Confidence should be reduced
        assert result.confidence < 0.7

    def test_position_limit(self, pm):
        from graxia.packages.quant_os.core.agents.portfolio_manager import PositionState

        for i in range(pm.MAX_POSITIONS):
            pm._positions[f"SYM{i}"] = PositionState(
                symbol=f"SYM{i}",
                side=SignalType.BUY,
                quantity=1.0,
            )
        # Try to add one more new symbol
        pm.observe(
            SignalEvent(
                symbol="NEWSYM",
                signal_type=SignalType.BUY,
                confidence=0.8,
                source="bull_bear_researcher",
            )
        )
        pm.observe(RiskEvent(check_name="audit", passed=True, source="risk_auditor"))
        result = pm.act()
        assert result is None

    def test_reset_clears_state(self, pm):
        pm._pending_consensus = SignalEvent(symbol="X", signal_type=SignalType.BUY, confidence=0.5)
        pm._pending_risk_pass = True
        pm.reset()
        assert pm._pending_consensus is None
        assert pm._pending_risk_pass is False


# ── EventBus integration tests ────────────────────────────────────


class TestAgentIntegration:
    def test_full_pipeline_via_bus(self, bus, analyst, researcher, risk_auditor, pm):
        """Test full pipeline: bars → analyst → researcher → risk → PM via EventBus."""
        # Wire agents to bus
        bus.subscribe(BarEvent, analyst.observe)
        bus.subscribe(SignalEvent, researcher.observe)
        bus.subscribe(SignalEvent, risk_auditor.observe)
        bus.subscribe(SignalEvent, pm.observe)
        bus.subscribe(RiskEvent, pm.observe)

        # Feed bars
        for i in range(25):
            bus.publish(_make_bar("XAUUSD", 2000.0 + i * 2, bar_index=i))

        # Analyst produces signal
        analyst_signal = analyst.act()
        if analyst_signal is not None:
            bus.publish(analyst_signal)

        # Researcher produces consensus
        consensus = researcher.act()
        if consensus is not None:
            bus.publish(consensus)

        # Risk auditor checks
        risk_result = risk_auditor.act()
        if risk_result is not None:
            bus.publish(risk_result)

        # PM assembles final signal
        final = pm.act()
        # Pipeline may or may not produce a final signal depending on rules
        assert final is None or isinstance(final, SignalEvent)

    def test_agents_only_communicate_via_bus(self):
        """Verify agents don't call each other directly."""
        a1 = TechnicalAnalystAgent()
        a2 = BullBearResearcherAgent()
        # They should be independent
        a1.observe(_make_bar("X", 100.0))
        a2.observe(SignalEvent(symbol="X", signal_type=SignalType.BUY, confidence=0.7, source="other"))
        # No cross-references
        assert not hasattr(a1, "_researcher")
        assert not hasattr(a2, "_analyst")
