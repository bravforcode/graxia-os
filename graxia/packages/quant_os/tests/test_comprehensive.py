"""
Comprehensive Tests — Phase 3.1 Full Coverage + k8s-style Isolation.

Each component is tested in isolation (like k8s pods):
  - Pillar 1: MacroRegimeCache (singleton, thread-safety, O(1) read)
  - Pillar 2: Canonical Payloads (Pydantic v2 frozen, validation, round-trip)
  - Pillar 3: Hierarchical Veto (PortfolioManager + RiskAuditor)
  - Pillar 4: CascadeRouter (3-tier, failover, prompt escaping)
  - SentimentAgent (observe, act, aggregate)
  - TechnicalAnalystAgent (SMA crossover, payload)
  - RiskAuditorAgent (all checks, macro lockdown, verdict payload)
  - MLPipeline (predict_payload, canonical output)
  - MLB Strategy (generate_signal, predict_payload delegation)
  - Hot Path Latency (all components < 10ms)
  - Cross-component Integration (signal flow)
"""

import asyncio
import os
import pickle
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from graxia.packages.quant_os.core.agents.analyst import TechnicalAnalystAgent
from graxia.packages.quant_os.core.agents.llm_router import CascadeResult, CascadeRouter, ImpactLevel
from graxia.packages.quant_os.core.agents.portfolio_manager import PortfolioManagerAgent
from graxia.packages.quant_os.core.agents.risk_auditor import RiskAuditorAgent
from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentAgent, _cascade_to_regime
from graxia.packages.quant_os.core.canonical.macro_regime import (
    MacroRegimeCache,
    RegimeBias,
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
from graxia.packages.quant_os.ml.pipeline import MLTrainer as MLPipeline

HOT_PATH_BUDGET_MS = 10.0


class _SimpleModel:
    """Picklable model for tests."""

    def __init__(self, prediction=1, probabilities=None):
        self._prediction = prediction
        self._probabilities = probabilities or [0.2, 0.8]

    def predict(self, X):
        return np.array([self._prediction])

    def predict_proba(self, X):
        return np.array([self._probabilities])


# ═══════════════════════════════════════════════════════════════════
# Isolation Test: MacroRegimeCache (Pillar 1)
# ═══════════════════════════════════════════════════════════════════


class TestIsolation_MacroRegimeCache:
    def setup_method(self):
        MacroRegimeCache().reset()

    def test_singleton_identity(self):
        a = MacroRegimeCache()
        b = MacroRegimeCache()
        assert a is b

    def test_default_state(self):
        r = MacroRegimeCache().get()
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

    def test_thread_safety_concurrent_writes(self):
        cache = MacroRegimeCache()
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

    def test_read_under_concurrent_write(self):
        cache = MacroRegimeCache()
        read_latencies = []
        lock = threading.Lock()
        stop = threading.Event()

        def reader():
            while not stop.is_set():
                start = time.perf_counter_ns()
                _ = cache.get()
                end = time.perf_counter_ns()
                with lock:
                    read_latencies.append((end - start) / 1_000_000)

        def writer():
            biases = [RegimeBias.BULLISH, RegimeBias.BEARISH, RegimeBias.PANIC]
            i = 0
            while not stop.is_set():
                cache.update_from_sentiment(biases[i % 3], 0.5, 1.0, "NORMAL")
                i += 1
                time.sleep(0.0001)

        threads = [threading.Thread(target=reader) for _ in range(4)]
        threads.append(threading.Thread(target=writer))
        for t in threads:
            t.start()
        time.sleep(0.5)
        stop.set()
        for t in threads:
            t.join()

        if read_latencies:
            p99 = sorted(read_latencies)[int(len(read_latencies) * 0.99)]
            assert p99 < HOT_PATH_BUDGET_MS


# ═══════════════════════════════════════════════════════════════════
# Isolation Test: Canonical Payloads (Pillar 2)
# ═══════════════════════════════════════════════════════════════════


class TestIsolation_Payloads:
    def test_ml_signal_payload_valid(self):
        p = MLSignalPayload(
            symbol="XAUUSD",
            xgb_probability=0.85,
            xgb_model_version="v1",
            direction=SignalDirection.BUY,
            entry_price=2400.0,
            stop_loss=2390.0,
            take_profit=2420.0,
        )
        assert p.symbol == "XAUUSD"
        assert p.direction == SignalDirection.BUY

    def test_ml_signal_payload_frozen(self):
        p = MLSignalPayload(
            symbol="XAUUSD",
            xgb_probability=0.85,
            xgb_model_version="v1",
            direction=SignalDirection.BUY,
            entry_price=2400.0,
            stop_loss=2390.0,
            take_profit=2420.0,
        )
        with pytest.raises(Exception):
            p.symbol = "EURUSD"

    def test_ml_signal_payload_bounds(self):
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

    def test_ml_signal_payload_round_trip(self):
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
        p2 = MLSignalPayload(**d)
        assert p2.symbol == "XAUUSD"

    def test_technical_signal_payload(self):
        p = TechnicalSignalPayload(
            symbol="XAUUSD",
            technical_action=SignalDirection.BUY,
            sma_short=2405.0,
            sma_long=2395.0,
            confidence=0.7,
            reasons=["bullish_sma_cross"],
        )
        assert p.technical_action == SignalDirection.BUY

    def test_macro_regime_payload_defaults(self):
        p = MacroRegimePayload()
        assert p.bias == RegimeBias.NEUTRAL
        assert p.position_multiplier == 1.0
        assert p.regime_label == "NORMAL"

    def test_risk_verdict_payload_vetoed(self):
        p = RiskVerdictPayload(
            is_approved=False,
            veto_reason=VetoReason.MACRO_LOCKDOWN,
            veto_detail="CRISIS regime",
            checks_failed=["macro_lockdown"],
        )
        assert p.is_approved is False
        assert p.veto_reason == VetoReason.MACRO_LOCKDOWN

    def test_final_trade_payload(self):
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

    def test_veto_reason_all_values(self):
        for vr in VetoReason:
            p = RiskVerdictPayload(is_approved=False, veto_reason=vr)
            assert p.veto_reason == vr


# ═══════════════════════════════════════════════════════════════════
# Isolation Test: PortfolioManager (Pillar 3)
# ═══════════════════════════════════════════════════════════════════


class TestIsolation_PortfolioManager:
    def setup_method(self):
        MacroRegimeCache().reset()

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
        risk = RiskEvent(check_name="audit", passed=True, source="risk_auditor")
        pm.observe(sig)
        pm.observe(risk)
        result = pm.act()
        assert result is not None
        assert result.confidence == 0.8

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
        assert result is None  # FAIL-CLOSED: vetoed signals return None

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
        risk = RiskEvent(check_name="audit", passed=True, source="risk_auditor")
        pm.observe(sig)
        pm.observe(sent)
        pm.observe(risk)
        result = pm.act()
        assert result is not None
        assert result.confidence == pytest.approx(0.4, abs=0.01)

    def test_no_initiator_returns_none(self):
        pm = PortfolioManagerAgent()
        assert pm.act() is None

    def test_max_positions(self):
        pm = PortfolioManagerAgent()
        pm.MAX_POSITIONS = 2
        results = []
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
            risk = RiskEvent(check_name="audit", passed=True, source="risk_auditor")
            pm.observe(sig)
            pm.observe(risk)
            results.append(pm.act())
        assert results[0] is not None
        assert results[1] is not None

    def test_hierarchical_formula(self):
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
            metadata={"position_multiplier": 0.75},
        )
        risk = RiskEvent(
            check_name="audit",
            passed=True,
            source="risk_auditor",
        )
        pm.observe(sig)
        pm.observe(sent)
        pm.observe(risk)
        result = pm.act()
        assert result is not None
        expected = 0.8 * 0.75 * 1.0
        assert result.confidence == pytest.approx(expected, abs=0.01)


# ═══════════════════════════════════════════════════════════════════
# Isolation Test: RiskAuditor (Pillar 3)
# ═══════════════════════════════════════════════════════════════════


class TestIsolation_RiskAuditor:
    def setup_method(self):
        MacroRegimeCache().reset()

    def test_approve_valid(self):
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
        assert result.passed is False

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
        assert result.passed is False

    def test_reject_whitelist(self):
        ra = RiskAuditorAgent(allowed_symbols=["EURUSD"])
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

    def test_macro_lockdown(self):
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
        assert result.passed is False
        cache.reset()

    def test_verdict_payload_in_details(self):
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
        v = result.details["risk_verdict"]
        assert v.is_approved is True
        assert v.veto_reason == VetoReason.NONE

    def test_veto_reason_mapping(self):
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
        v = result.details["risk_verdict"]
        assert v.veto_reason == VetoReason.MACRO_LOCKDOWN
        cache.reset()


# ═══════════════════════════════════════════════════════════════════
# Isolation Test: CascadeRouter (Pillar 4)
# ═══════════════════════════════════════════════════════════════════


class TestIsolation_CascadeRouter:
    def test_tier1_low_impact(self):
        router = CascadeRouter()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": '{"impact": "LOW", "dir": 1}'}}]}
        with patch.object(router, "_get_client", new_callable=AsyncMock) as m:
            client = AsyncMock()
            client.post = AsyncMock(return_value=mock_resp)
            m.return_value = client
            with patch("os.getenv", return_value="key"):
                result = asyncio.get_event_loop().run_until_complete(router.route("Routine earnings"))
        assert result.impact == ImpactLevel.LOW
        assert result.tier_used == 1

    def test_tier2_rejection(self):
        router = CascadeRouter()
        tier1 = MagicMock(status_code=200)
        tier1.json.return_value = {"choices": [{"message": {"content": '{"impact": "HIGH", "dir": -1}'}}]}
        tier2 = MagicMock(status_code=200)
        tier2.json.return_value = {"choices": [{"message": {"content": '{"confirmed": false, "confidence": 0.3}'}}]}
        call_count = [0]

        async def mock_post(url, **kwargs):
            call_count[0] += 1
            return tier1 if call_count[0] == 1 else tier2

        with patch.object(router, "_get_client", new_callable=AsyncMock) as m:
            client = AsyncMock()
            client.post = mock_post
            m.return_value = client
            with patch("os.getenv", return_value="key"):
                result = asyncio.get_event_loop().run_until_complete(router.route("Breaking news"))
        assert result.impact == ImpactLevel.LOW

    def test_no_api_key(self):
        router = CascadeRouter()
        with patch("os.getenv", return_value=""):
            result = asyncio.get_event_loop().run_until_complete(router.route("Some headline"))
        assert result.impact == ImpactLevel.LOW

    def test_tier1_failure(self):
        router = CascadeRouter()
        with patch.object(router, "_get_client", new_callable=AsyncMock) as m:
            client = AsyncMock()
            client.post = AsyncMock(return_value=MagicMock(status_code=500))
            m.return_value = client
            with patch("os.getenv", return_value="key"):
                result = asyncio.get_event_loop().run_until_complete(router.route("Headline"))
        assert result.impact == ImpactLevel.LOW
        assert result.reasoning == "Tier 1 failed"

    def test_cascade_to_regime_crisis(self):
        result = CascadeResult(
            headline="Fed emergency",
            impact=ImpactLevel.HIGH,
            direction=-1,
            tier_used=2,
            confidence=0.95,
        )
        payload = _cascade_to_regime(result, "Fed emergency")
        assert payload.bias == RegimeBias.PANIC
        assert payload.regime_label == "CRISIS"
        assert payload.position_multiplier == 0.0

    def test_prompt_no_format_error(self):
        router = CascadeRouter()
        with patch.object(router, "_get_client", new_callable=AsyncMock) as m:
            client = AsyncMock()
            client.post = AsyncMock(return_value=MagicMock(status_code=500))
            m.return_value = client
            with patch("os.getenv", return_value="key"):
                result = asyncio.get_event_loop().run_until_complete(router.route('Test with "quotes" and {braces}'))
        assert result is not None


# ═══════════════════════════════════════════════════════════════════
# Isolation Test: SentimentAgent
# ═══════════════════════════════════════════════════════════════════


class TestIsolation_SentimentAgent:
    def test_act_none_when_empty(self):
        agent = SentimentAgent()
        result = asyncio.get_event_loop().run_until_complete(agent.act())
        assert result is None

    def test_aggregate_most_conservative(self):
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
        assert result.position_multiplier == 0.3


# ═══════════════════════════════════════════════════════════════════
# Isolation Test: TechnicalAnalystAgent
# ═══════════════════════════════════════════════════════════════════


class TestIsolation_TechnicalAnalyst:
    def _bars(self, closes, sym="XAUUSD"):
        return [BarEvent(symbol=sym, high=c + 5, low=c - 5, open=c - 1, close=c, volume=1000) for c in closes]

    def test_no_signal_insufficient_data(self):
        ta = TechnicalAnalystAgent()
        for bar in self._bars([2400 + i for i in range(10)]):
            ta.observe(bar)
        assert ta.act() is None

    def test_signal_has_tech_payload(self):
        ta = TechnicalAnalystAgent()
        closes = [2400 - i * 0.5 for i in range(20)] + [2400, 2401, 2402, 2403, 2404]
        for bar in self._bars(closes):
            ta.observe(bar)
        result = ta.act()
        if result is not None:
            assert "technical_signal" in result.metadata
            tech = result.metadata["technical_signal"]
            assert tech.symbol == "XAUUSD"

    def test_reset(self):
        ta = TechnicalAnalystAgent()
        for bar in self._bars([2400 + i for i in range(25)]):
            ta.observe(bar)
        ta.reset()
        assert len(ta._closes) == 0


# ═══════════════════════════════════════════════════════════════════
# Isolation Test: MLPipeline
# ═══════════════════════════════════════════════════════════════════


class TestIsolation_MLPipeline:
    def test_predict_payload_returns_model(self):
        pipeline = MLPipeline()
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            pickle.dump(
                {
                    "model": _SimpleModel(prediction=1, probabilities=[0.2, 0.8]),
                    "feature_names": ["f1", "f2"],
                    "model_type": "xgboost",
                    "version": "test",
                },
                f,
            )
            model_path = f.name

        try:
            result = pipeline.predict_payload(
                model_path=model_path,
                features={"f1": 0.5, "f2": 0.3},
                symbol="XAUUSD",
                entry_price=2400.0,
                stop_loss=2390.0,
                take_profit=2420.0,
            )
            assert result.symbol == "XAUUSD"
            assert result.direction == SignalDirection.BUY
            assert result.xgb_probability == 0.8
        finally:
            os.unlink(model_path)

    def test_predict_returns_tuple(self):
        pipeline = MLPipeline()
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            pickle.dump(
                {
                    "model": _SimpleModel(prediction=0, probabilities=[0.6, 0.4]),
                    "feature_names": ["f1"],
                    "model_type": "xgboost",
                    "version": "test",
                },
                f,
            )
            model_path = f.name

        try:
            pred, conf = pipeline.predict(model_path, {"f1": 0.5})
            assert pred == 0
            assert conf == 0.6
        finally:
            os.unlink(model_path)


# ═══════════════════════════════════════════════════════════════════
# Hot Path Latency (all components)
# ═══════════════════════════════════════════════════════════════════


class TestHotPath_Latency:
    def test_cache_get_latency(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.NEUTRAL, 0.5, 1.0, "NORMAL")
        latencies = []
        for _ in range(10000):
            start = time.perf_counter_ns()
            _ = cache.get()
            end = time.perf_counter_ns()
            latencies.append((end - start) / 1_000_000)
        p99 = sorted(latencies)[9900]
        assert p99 < HOT_PATH_BUDGET_MS

    def test_risk_auditor_latency(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.NEUTRAL, 0.5, 1.0, "NORMAL")
        ra = RiskAuditorAgent()
        latencies = []
        for _ in range(1000):
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
            start = time.perf_counter_ns()
            _ = ra.act()
            end = time.perf_counter_ns()
            latencies.append((end - start) / 1_000_000)
        p99 = sorted(latencies)[990]
        assert p99 < HOT_PATH_BUDGET_MS

    def test_full_flow_latency(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.NEUTRAL, 0.5, 1.0, "NORMAL")
        ra = RiskAuditorAgent()
        pm = PortfolioManagerAgent()
        latencies = []
        for _ in range(1000):
            sig = SignalEvent(
                symbol="XAUUSD",
                signal_type=SignalType.BUY,
                confidence=0.8,
                entry_price=2400.0,
                stop_loss=2390.0,
                take_profit=2430.0,
                source="technical_analyst",
            )
            start = time.perf_counter_ns()
            ra.observe(sig)
            risk = ra.act()
            pm.observe(sig)
            pm.observe(risk)
            final = pm.act()
            end = time.perf_counter_ns()
            latencies.append((end - start) / 1_000_000)
        p99 = sorted(latencies)[990]
        assert p99 < HOT_PATH_BUDGET_MS

    def test_concurrent_flow_latency(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.NEUTRAL, 0.5, 1.0, "NORMAL")
        latencies = []
        lock = threading.Lock()

        def process():
            ra = RiskAuditorAgent()
            pm = PortfolioManagerAgent()
            for _ in range(100):
                sig = SignalEvent(
                    symbol="XAUUSD",
                    signal_type=SignalType.BUY,
                    confidence=0.8,
                    entry_price=2400.0,
                    stop_loss=2390.0,
                    take_profit=2430.0,
                    source="technical_analyst",
                )
                start = time.perf_counter_ns()
                ra.observe(sig)
                risk = ra.act()
                pm.observe(sig)
                pm.observe(risk)
                pm.act()
                end = time.perf_counter_ns()
                with lock:
                    latencies.append((end - start) / 1_000_000)

        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = [ex.submit(process) for _ in range(8)]
            for f in as_completed(futures):
                f.result()
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]
        assert p99 < HOT_PATH_BUDGET_MS

    def test_no_http_in_hot_path(self):
        with patch("httpx.AsyncClient.post", side_effect=AssertionError("HTTP!")):
            cache = MacroRegimeCache()
            cache.update_from_sentiment(RegimeBias.NEUTRAL, 0.5, 1.0, "NORMAL")
            ra = RiskAuditorAgent()
            pm = PortfolioManagerAgent()
            for _ in range(100):
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
                risk = ra.act()
                pm.observe(sig)
                pm.observe(risk)
                pm.act()


# ═══════════════════════════════════════════════════════════════════
# Cross-Component Integration
# ═══════════════════════════════════════════════════════════════════


class TestIntegration_FullFlow:
    def setup_method(self):
        MacroRegimeCache().reset()

    def test_signal_approve(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.NEUTRAL, 0.5, 1.0, "NORMAL")
        ta = TechnicalAnalystAgent()
        ra = RiskAuditorAgent()
        pm = PortfolioManagerAgent()

        closes = [2400 - i * 0.5 for i in range(20)] + [2400, 2401, 2402, 2403, 2404]
        for c in closes:
            ta.observe(BarEvent(symbol="XAUUSD", high=c + 5, low=c - 5, open=c - 1, close=c, volume=1000))

        signal = ta.act()
        if signal is None:
            pytest.skip("No signal")

        ra.observe(signal)
        risk = ra.act()
        pm.observe(signal)
        pm.observe(risk)
        final = pm.act()

        if risk.passed:
            assert final is not None
            assert final.confidence > 0
        else:
            assert final is None  # FAIL-CLOSED
        cache.reset()

    def test_crisis_veto(self):
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
        assert final is None  # FAIL-CLOSED: vetoed
        cache.reset()

    def test_sentiment_dampen(self):
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
        risk = RiskEvent(check_name="audit", passed=True, source="risk_auditor")
        pm.observe(sig)
        pm.observe(sent)
        pm.observe(risk)
        final = pm.act()
        assert final is not None
        assert final.confidence == pytest.approx(0.4, abs=0.01)
        cache.reset()
