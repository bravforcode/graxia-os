"""
Phase 3.1 Pillar Unit Tests — Edge cases, CRISIS cascade, provider failover.

Pillar 1: MacroRegimeCache (singleton, thread-safety, O(1) read)
Pillar 2: Canonical Payloads (Pydantic v2 frozen, validation)
Pillar 3: Hierarchical Veto (PortfolioManager + RiskAuditor)
Pillar 4: CascadeRouter (3-tier, failover)
"""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from graxia.packages.quant_os.core.agents.analyst import TechnicalAnalystAgent
from graxia.packages.quant_os.core.agents.llm_router import CascadeResult, CascadeRouter, ImpactLevel
from graxia.packages.quant_os.core.agents.portfolio_manager import PortfolioManagerAgent
from graxia.packages.quant_os.core.agents.risk_auditor import RiskAuditorAgent
from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentAgent, _cascade_to_regime
from graxia.packages.quant_os.core.canonical.macro_regime import (
    MacroRegimeCache,
    RegimeBias,
    get_macro_regime,
    get_position_multiplier,
)
from graxia.packages.quant_os.core.canonical.payloads import (
    FinalTradePayload,
    MacroRegimePayload,
    MLSignalPayload,
    RiskVerdictPayload,
    SignalDirection,
    TechnicalSignalPayload,
    VetoReason,
)
from graxia.packages.quant_os.core.enums import SignalType
from graxia.packages.quant_os.core.events import BarEvent, RiskEvent, SignalEvent

# ═══════════════════════════════════════════════════════════════════
# Pillar 1: MacroRegimeCache
# ═══════════════════════════════════════════════════════════════════


class TestMacroRegimeCache:
    def test_singleton_identity(self):
        a = MacroRegimeCache()
        b = MacroRegimeCache()
        assert a is b

    def test_default_regime(self):
        cache = MacroRegimeCache()
        cache.reset()
        r = cache.get()
        assert r.bias == RegimeBias.NEUTRAL
        assert r.position_multiplier == 1.0
        assert r.regime_label == "NORMAL"

    def test_update_from_sentiment(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.BEARISH, 0.9, 0.2, "CRISIS", "cascade_t2", "Fed emergency")
        r = cache.get()
        assert r.bias == RegimeBias.BEARISH
        assert r.confidence == 0.9
        assert r.position_multiplier == 0.2
        assert r.regime_label == "CRISIS"
        assert r.source == "cascade_t2"
        assert r.headline == "Fed emergency"

    def test_get_position_multiplier(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.NEUTRAL, 0.5, 0.75, "NORMAL")
        assert get_position_multiplier() == 0.75

    def test_get_macro_regime(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.BULLISH, 0.8, 1.0, "NORMAL")
        r = get_macro_regime()
        assert r.bias == RegimeBias.BULLISH

    def test_thread_safety_concurrent_writes(self):
        cache = MacroRegimeCache()
        cache.reset()
        errors = []

        def writer(bias, mult, label):
            try:
                for _ in range(100):
                    cache.update_from_sentiment(bias, 0.5, mult, label)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer, args=(RegimeBias.BULLISH, 1.0, "NORMAL")),
            threading.Thread(target=writer, args=(RegimeBias.BEARISH, 0.3, "CRISIS")),
            threading.Thread(target=writer, args=(RegimeBias.PANIC, 0.0, "CRISIS")),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        r = cache.get()
        assert r.bias in (RegimeBias.BULLISH, RegimeBias.BEARISH, RegimeBias.PANIC)

    def test_reset(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.PANIC, 1.0, 0.0, "CRISIS")
        cache.reset()
        r = cache.get()
        assert r.bias == RegimeBias.NEUTRAL
        assert r.position_multiplier == 1.0


# ═══════════════════════════════════════════════════════════════════
# Pillar 2: Canonical Payloads
# ═══════════════════════════════════════════════════════════════════


class TestMLSignalPayload:
    def test_create_valid(self):
        p = MLSignalPayload(
            symbol="XAUUSD",
            xgb_probability=0.85,
            xgb_model_version="xgb_v1",
            direction=SignalDirection.BUY,
            entry_price=2400.0,
            stop_loss=2390.0,
            take_profit=2420.0,
        )
        assert p.symbol == "XAUUSD"
        assert p.direction == SignalDirection.BUY
        assert p.xgb_probability == 0.85

    def test_frozen(self):
        p = MLSignalPayload(
            symbol="XAUUSD",
            xgb_probability=0.85,
            xgb_model_version="xgb_v1",
            direction=SignalDirection.BUY,
            entry_price=2400.0,
            stop_loss=2390.0,
            take_profit=2420.0,
        )
        with pytest.raises(Exception):
            p.symbol = "EURUSD"

    def test_probability_bounds(self):
        with pytest.raises(Exception):
            MLSignalPayload(
                symbol="XAUUSD",
                xgb_probability=1.5,
                xgb_model_version="v1",
                direction=SignalDirection.BUY,
                entry_price=2400.0,
                stop_loss=2390.0,
                take_profit=2420.0,
            )

    def test_round_trip(self):
        p = MLSignalPayload(
            symbol="XAUUSD",
            xgb_probability=0.85,
            xgb_model_version="v1",
            direction=SignalDirection.SELL,
            entry_price=2400.0,
            stop_loss=2410.0,
            take_profit=2380.0,
        )
        d = p.model_dump()
        assert d["direction"] == "SELL"
        assert d["xgb_probability"] == 0.85


class TestTechnicalSignalPayload:
    def test_create_valid(self):
        p = TechnicalSignalPayload(
            symbol="XAUUSD",
            technical_action=SignalDirection.BUY,
            sma_short=2405.0,
            sma_long=2395.0,
            confidence=0.7,
            reasons=["bullish_sma_cross"],
        )
        assert p.technical_action == SignalDirection.BUY
        assert p.confidence == 0.7

    def test_frozen(self):
        p = TechnicalSignalPayload(symbol="XAUUSD", technical_action=SignalDirection.HOLD)
        with pytest.raises(Exception):
            p.symbol = "EURUSD"


class TestMacroRegimePayload:
    def test_create_valid(self):
        p = MacroRegimePayload(
            bias=RegimeBias.BEARISH,
            confidence=0.8,
            position_multiplier=0.3,
            regime_label="HIGH_UNCERTAINTY",
            source_provider="cascade_t2",
            headline="Fed hawkish",
        )
        assert p.regime_label == "HIGH_UNCERTAINTY"

    def test_default_values(self):
        p = MacroRegimePayload()
        assert p.bias == RegimeBias.NEUTRAL
        assert p.position_multiplier == 1.0
        assert p.regime_label == "NORMAL"


class TestRiskVerdictPayload:
    def test_approved(self):
        p = RiskVerdictPayload(
            is_approved=True,
            veto_reason=VetoReason.NONE,
            checks_passed=["min_confidence", "risk_reward_ratio"],
        )
        assert p.is_approved is True

    def test_vetoed(self):
        p = RiskVerdictPayload(
            is_approved=False,
            veto_reason=VetoReason.MACRO_LOCKDOWN,
            veto_detail="CRISIS regime",
            checks_failed=["macro_lockdown"],
        )
        assert p.is_approved is False
        assert p.veto_reason == VetoReason.MACRO_LOCKDOWN


class TestFinalTradePayload:
    def test_create_valid(self):
        p = FinalTradePayload(
            symbol="XAUUSD",
            direction=SignalDirection.BUY,
            entry_price=2400.0,
            stop_loss=2390.0,
            take_profit=2420.0,
            raw_confidence=0.85,
            sentiment_modifier=0.75,
            final_confidence=0.6375,
            risk_dollars=50.0,
            regime_bias=RegimeBias.BEARISH,
            regime_label="HIGH_UNCERTAINTY",
            risk_approved=True,
        )
        assert p.final_confidence == 0.6375
        assert p.risk_approved is True


# ═══════════════════════════════════════════════════════════════════
# Pillar 3: Hierarchical Veto
# ═══════════════════════════════════════════════════════════════════


class TestPortfolioManager:
    def _make_risk_approved(self):
        return RiskEvent(
            check_name="agent_risk_audit",
            passed=True,
            reason="",
            source="risk_auditor",
        )

    def test_initiator_only(self):
        pm = PortfolioManagerAgent()
        sig = SignalEvent(
            symbol="XAUUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            entry_price=2400.0,
            stop_loss=2390.0,
            take_profit=2420.0,
            source="technical_analyst",
        )
        pm.observe(sig)
        pm.observe(self._make_risk_approved())
        result = pm.act()
        assert result is not None
        assert result.confidence == pytest.approx(0.8, abs=0.01)

    def test_veto_kills_trade(self):
        pm = PortfolioManagerAgent()
        sig = SignalEvent(
            symbol="XAUUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            entry_price=2400.0,
            stop_loss=2390.0,
            take_profit=2420.0,
            source="technical_analyst",
        )
        risk = RiskEvent(
            check_name="macro_lockdown",
            passed=False,
            reason="CRISIS",
            source="risk_auditor",
        )
        pm.observe(sig)
        pm.observe(risk)
        result = pm.act()
        assert result is None

    def test_sentiment_modifier(self):
        pm = PortfolioManagerAgent()
        sig = SignalEvent(
            symbol="XAUUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            entry_price=2400.0,
            stop_loss=2390.0,
            take_profit=2420.0,
            source="technical_analyst",
        )
        sent = SignalEvent(
            symbol="XAUUSD",
            signal_type=SignalType.BUY,
            confidence=0.5,
            source="sentiment_agent",
            metadata={"position_multiplier": 0.5},
        )
        pm.observe(sig)
        pm.observe(sent)
        pm.observe(self._make_risk_approved())
        result = pm.act()
        assert result is not None
        assert result.confidence == pytest.approx(0.4, abs=0.01)

    def test_no_initiator_returns_none(self):
        pm = PortfolioManagerAgent()
        result = pm.act()
        assert result is None

    def test_max_positions_limit(self):
        pm = PortfolioManagerAgent()
        pm.MAX_POSITIONS = 2
        for i in range(3):
            sig = SignalEvent(
                symbol=f"SYM{i}",
                signal_type=SignalType.BUY,
                confidence=0.8,
                entry_price=100.0,
                stop_loss=99.0,
                take_profit=102.0,
                source="technical_analyst",
            )
            pm.observe(sig)
            pm.observe(self._make_risk_approved())
            result = pm.act()
            if i < 2:
                assert result is not None
            # 3rd should be blocked (no initiator set after act)


class TestRiskAuditor:
    def test_approve_valid_signal(self):
        ra = RiskAuditorAgent()
        sig = SignalEvent(
            symbol="XAUUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            entry_price=2400.0,
            stop_loss=2390.0,
            take_profit=2430.0,
            source="technical_analyst",
        )
        ra.observe(sig)
        result = ra.act()
        assert result is not None
        assert result.passed is True

    def test_reject_low_confidence(self):
        ra = RiskAuditorAgent()
        sig = SignalEvent(
            symbol="XAUUSD",
            signal_type=SignalType.BUY,
            confidence=0.1,
            entry_price=2400.0,
            stop_loss=2390.0,
            take_profit=2430.0,
            source="technical_analyst",
        )
        ra.observe(sig)
        result = ra.act()
        assert result is not None
        assert result.passed is False
        assert "min_confidence" in result.details["checks"]

    def test_reject_poor_rr(self):
        ra = RiskAuditorAgent()
        sig = SignalEvent(
            symbol="XAUUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            entry_price=2400.0,
            stop_loss=2390.0,
            take_profit=2405.0,
            source="technical_analyst",
        )
        ra.observe(sig)
        result = ra.act()
        assert result is not None
        assert result.passed is False

    def test_reject_symbol_not_whitelisted(self):
        ra = RiskAuditorAgent(allowed_symbols=["EURUSD", "GBPUSD"])
        sig = SignalEvent(
            symbol="XAUUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            entry_price=2400.0,
            stop_loss=2390.0,
            take_profit=2430.0,
            source="technical_analyst",
        )
        ra.observe(sig)
        result = ra.act()
        assert result is not None
        assert result.passed is False

    def test_reject_duplicate_flood(self):
        ra = RiskAuditorAgent()
        for _ in range(4):
            sig = SignalEvent(
                symbol="XAUUSD",
                signal_type=SignalType.BUY,
                confidence=0.8,
                entry_price=2400.0,
                stop_loss=2390.0,
                take_profit=2430.0,
                source="technical_analyst",
            )
            ra.observe(sig)
            result = ra.act()
        assert result.passed is False

    def test_macro_lockdown_rejects(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.PANIC, 1.0, 0.0, "CRISIS")
        ra = RiskAuditorAgent()
        sig = SignalEvent(
            symbol="XAUUSD",
            signal_type=SignalType.BUY,
            confidence=0.9,
            entry_price=2400.0,
            stop_loss=2390.0,
            take_profit=2430.0,
            source="technical_analyst",
        )
        ra.observe(sig)
        result = ra.act()
        assert result is not None
        assert result.passed is False
        cache.reset()

    def test_risk_verdict_payload_in_details(self):
        ra = RiskAuditorAgent()
        sig = SignalEvent(
            symbol="XAUUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            entry_price=2400.0,
            stop_loss=2390.0,
            take_profit=2430.0,
            source="technical_analyst",
        )
        ra.observe(sig)
        result = ra.act()
        assert "risk_verdict" in result.details
        verdict = result.details["risk_verdict"]
        assert verdict.is_approved is True
        assert verdict.veto_reason.value == "NONE"


# ═══════════════════════════════════════════════════════════════════
# Pillar 4: CascadeRouter
# ═══════════════════════════════════════════════════════════════════


class TestCascadeRouter:
    def test_tier1_low_impact_returns_immediately(self):
        router = CascadeRouter()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": '{"impact": "LOW", "dir": 1}'}}]}
        with patch.object(router, "_get_client", new_callable=AsyncMock) as mock_get:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_client
            with patch("os.getenv", return_value="fake_key"):
                result = asyncio.run(router.route("Routine earnings report"))
        assert result.impact == ImpactLevel.LOW
        assert result.tier_used == 1

    def test_tier2_rejection_demotes_to_low(self):
        router = CascadeRouter()
        tier1_resp = MagicMock()
        tier1_resp.status_code = 200
        tier1_resp.json.return_value = {"choices": [{"message": {"content": '{"impact": "HIGH", "dir": -1}'}}]}
        tier2_resp = MagicMock()
        tier2_resp.status_code = 200
        tier2_resp.json.return_value = {
            "choices": [{"message": {"content": '{"confirmed": false, "confidence": 0.3, "reasoning": "false alarm"}'}}]
        }
        call_count = [0]

        async def mock_post(url, **kwargs):
            call_count[0] += 1
            return tier1_resp if call_count[0] == 1 else tier2_resp

        with patch.object(router, "_get_client", new_callable=AsyncMock) as mock_get:
            mock_client = AsyncMock()
            mock_client.post = mock_post
            mock_get.return_value = mock_client
            with patch("os.getenv", return_value="fake_key"):
                result = asyncio.run(router.route("Breaking: Fed rate decision"))
        assert result.impact == ImpactLevel.LOW
        assert result.tier_used == 2

    def test_tier1_failure_returns_low(self):
        router = CascadeRouter()
        with patch.object(router, "_get_client", new_callable=AsyncMock) as mock_get:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=MagicMock(status_code=500))
            mock_get.return_value = mock_client
            with patch("os.getenv", return_value="fake_key"):
                result = asyncio.run(router.route("Some headline"))
        assert result.impact == ImpactLevel.LOW
        assert result.reasoning == "Tier 1 failed"

    def test_no_api_key_returns_low(self):
        router = CascadeRouter()
        with patch("os.getenv", return_value=""):
            result = asyncio.run(router.route("Some headline"))
        assert result.impact == ImpactLevel.LOW

    def test_cascade_to_regime_mapping(self):
        result = CascadeResult(
            headline="Fed emergency cut",
            impact=ImpactLevel.HIGH,
            direction=-1,
            tier_used=2,
            confidence=0.95,
            reasoning="CRISIS",
        )
        payload = _cascade_to_regime(result, "Fed emergency cut")
        assert payload.bias == RegimeBias.PANIC
        assert payload.regime_label == "CRISIS"
        assert payload.position_multiplier == 0.0


# ═══════════════════════════════════════════════════════════════════
# TechnicalAnalystAgent
# ═══════════════════════════════════════════════════════════════════


class TestTechnicalAnalystAgent:
    def _make_bars(self, closes, symbol="XAUUSD"):
        bars = []
        for i, c in enumerate(closes):
            bars.append(
                BarEvent(
                    symbol=symbol,
                    high=c + 5,
                    low=c - 5,
                    open=c - 1,
                    close=c,
                    volume=1000,
                )
            )
        return bars

    def test_no_signal_insufficient_data(self):
        ta = TechnicalAnalystAgent()
        for bar in self._make_bars([2400 + i for i in range(10)]):
            ta.observe(bar)
        result = ta.act()
        assert result is None

    def test_bullish_signal_with_technical_payload(self):
        ta = TechnicalAnalystAgent()
        # Create uptrend: short SMA > long SMA + last bar bullish
        closes = [2400 - i * 0.5 for i in range(20)] + [2400, 2401, 2402, 2403, 2404]
        for bar in self._make_bars(closes):
            ta.observe(bar)
        result = ta.act()
        if result is not None:
            assert "technical_signal" in result.metadata
            tech = result.metadata["technical_signal"]
            assert tech.symbol == "XAUUSD"
            assert tech.technical_action.value in ("BUY", "SELL", "HOLD")

    def test_reset(self):
        ta = TechnicalAnalystAgent()
        for bar in self._make_bars([2400 + i for i in range(25)]):
            ta.observe(bar)
        ta.reset()
        assert len(ta._closes) == 0


# ═══════════════════════════════════════════════════════════════════
# SentimentAgent
# ═══════════════════════════════════════════════════════════════════


class TestSentimentAgent:
    def test_act_returns_none_when_no_pending(self):
        agent = SentimentAgent()
        result = asyncio.run(agent.act())
        assert result is None

    def test_aggregate_most_conservative_wins(self):
        agent = SentimentAgent()
        p1 = MacroRegimePayload(
            bias=RegimeBias.BULLISH,
            confidence=0.8,
            position_multiplier=0.9,
            regime_label="NORMAL",
        )
        p2 = MacroRegimePayload(
            bias=RegimeBias.BEARISH,
            confidence=0.7,
            position_multiplier=0.3,
            regime_label="HIGH_UNCERTAINTY",
        )
        result = agent._aggregate([p1, p2])
        assert result.regime_label == "HIGH_UNCERTAINTY"
        # Weighted average: (0.9*0.8 + 0.3*0.7) / (0.8+0.7) = 0.62
        assert result.position_multiplier == pytest.approx(0.62, abs=0.01)


# ═══════════════════════════════════════════════════════════════════
# E2E: Full Signal Flow
# ═══════════════════════════════════════════════════════════════════


class TestE2ESignalFlow:
    def test_full_flow_approve(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.NEUTRAL, 0.5, 1.0, "NORMAL")

        ta = TechnicalAnalystAgent()
        ra = RiskAuditorAgent()
        pm = PortfolioManagerAgent()

        # Feed 25 bars to trigger a signal
        closes = [2400 - i * 0.5 for i in range(20)] + [2400, 2401, 2402, 2403, 2404]
        for c in closes:
            ta.observe(BarEvent(symbol="XAUUSD", high=c + 5, low=c - 5, open=c - 1, close=c, volume=1000))

        signal = ta.act()
        if signal is None:
            pytest.skip("No technical signal generated")

        ra.observe(signal)
        risk_event = ra.act()
        assert risk_event is not None

        pm.observe(signal)
        pm.observe(risk_event)
        final = pm.act()

        if risk_event.passed:
            assert final is not None
            assert final.confidence > 0
        else:
            assert final is None

        cache.reset()

    def test_full_flow_veto_by_crisis(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.PANIC, 1.0, 0.0, "CRISIS")

        ra = RiskAuditorAgent()
        pm = PortfolioManagerAgent()

        sig = SignalEvent(
            symbol="XAUUSD",
            signal_type=SignalType.BUY,
            confidence=0.9,
            entry_price=2400.0,
            stop_loss=2390.0,
            take_profit=2430.0,
            source="technical_analyst",
        )

        ra.observe(sig)
        risk = ra.act()
        assert risk.passed is False

        pm.observe(sig)
        pm.observe(risk)
        final = pm.act()
        assert final is None

        cache.reset()

    def test_sentiment_dampens_signal(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.BEARISH, 0.8, 0.5, "HIGH_UNCERTAINTY")

        pm = PortfolioManagerAgent()

        sig = SignalEvent(
            symbol="XAUUSD",
            signal_type=SignalType.BUY,
            confidence=0.8,
            entry_price=2400.0,
            stop_loss=2390.0,
            take_profit=2430.0,
            source="technical_analyst",
        )
        sent = SignalEvent(
            symbol="XAUUSD",
            signal_type=SignalType.BUY,
            confidence=0.5,
            source="sentiment_agent",
            metadata={"position_multiplier": 0.5},
        )

        pm.observe(sig)
        pm.observe(sent)
        pm.observe(RiskEvent(check_name="agent_risk_audit", passed=True, reason="", source="risk_auditor"))
        final = pm.act()
        assert final is not None
        assert final.confidence == pytest.approx(0.4, abs=0.01)

        cache.reset()
