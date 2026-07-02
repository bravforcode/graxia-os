"""
RiskAgent Tests
===============
Verifies RiskAgent receives NewsAnalyzedEvent and reads MacroRegimeCache.

Run:
  cd graxia/packages
  python -m pytest quant_os/tests/chaos/test_risk_agent.py -v
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from graxia.packages.quant_os.core.agents.risk_agent import RiskAgent
from graxia.packages.quant_os.core.canonical.macro_regime import (
    MacroRegimeCache,
    RegimeBias,
)
from graxia.packages.quant_os.core.event_bus import EventBus
from graxia.packages.quant_os.core.events import NewsAnalyzedEvent, SignalEvent


@pytest.fixture(autouse=True)
def reset_macro_cache():
    """Reset singleton cache between tests."""
    MacroRegimeCache._instance = None
    yield
    MacroRegimeCache._instance = None


class TestRiskAgent:
    def test_observe_logs_news_analyzed_event(self):
        agent = RiskAgent()
        event = NewsAnalyzedEvent(
            headline="Fed raises rates by 50bps",
            regime_label="HIGH_UNCERTAINTY",
            bias="BEARISH",
            confidence=0.85,
            position_multiplier=0.4,
            source_provider="cascade_t2",
        )

        with patch("graxia.packages.quant_os.core.agents.risk_agent.logger") as mock_log:
            agent.observe(event)
            mock_log.info.assert_called_once()
            call_kwargs = mock_log.info.call_args[1]
            assert call_kwargs["regime"] == "HIGH_UNCERTAINTY"
            assert call_kwargs["bias"] == "BEARISH"
            assert call_kwargs["confidence"] == 0.85
            assert call_kwargs["event_position_multiplier"] == 0.4

    def test_observe_reads_macro_regime_cache(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(
            bias=RegimeBias.PANIC,
            confidence=0.9,
            position_multiplier=0.0,
            regime_label="CRISIS",
            source="test",
        )

        agent = RiskAgent()
        event = NewsAnalyzedEvent(
            headline="Market crash",
            regime_label="CRISIS",
            bias="PANIC",
            confidence=0.9,
            position_multiplier=0.0,
            source_provider="test",
        )

        with patch("graxia.packages.quant_os.core.agents.risk_agent.logger") as mock_log:
            agent.observe(event)
            call_kwargs = mock_log.info.call_args[1]
            assert call_kwargs["cache_regime"] == "CRISIS"
            assert call_kwargs["cache_position_multiplier"] == 0.0

    def test_observe_ignores_non_news_events(self):
        agent = RiskAgent()
        event = SignalEvent(symbol="XAUUSD", confidence=0.8)
        agent.observe(event)
        assert len(agent._observations) == 0

    def test_observe_stores_event_in_observations(self):
        agent = RiskAgent()
        event = NewsAnalyzedEvent(headline="Test", confidence=0.7)
        agent.observe(event)
        assert len(agent._observations) == 1
        assert agent._observations[0] is event

    def test_act_returns_none(self):
        agent = RiskAgent()
        assert agent.act() is None

    def test_bus_subscriber_receives_event(self):
        bus = EventBus()
        agent = RiskAgent()
        bus.subscribe("news.analyzed", agent.observe)

        event = NewsAnalyzedEvent(
            headline="NFP beats expectations",
            regime_label="NORMAL",
            bias="BULLISH",
            confidence=0.7,
            position_multiplier=1.0,
        )
        bus.publish("news.analyzed", event)

        assert len(agent._observations) == 1
        assert agent._observations[0].headline == "NFP beats expectations"

    def test_default_name(self):
        agent = RiskAgent()
        assert agent.name == "risk_agent"

    def test_custom_name(self):
        agent = RiskAgent(name="custom_risk")
        assert agent.name == "custom_risk"
