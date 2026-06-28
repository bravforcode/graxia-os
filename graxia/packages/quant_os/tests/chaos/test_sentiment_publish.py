"""
SentimentAgent EventBus Publish Tests
=====================================
Verifies SentimentAgent publishes NewsAnalyzedEvent via EventBus after cache update.

Run:
  cd graxia/packages
  python -m pytest quant_os/tests/chaos/test_sentiment_publish.py -v
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_env():
    env = {
        "GROQ_API_KEY": "test_groq_key",
        "CEREBRAS_API_KEY": "test_cerebras_key",
        "GOOGLE_AI_KEY": "test_google_key",
    }
    with patch.dict(__import__("os").environ, env):
        yield


class TestSentimentAgentPublish:
    def test_act_publishes_news_analyzed_to_bus(self, mock_env):
        from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentAgent
        from graxia.packages.quant_os.core.event_bus import EventBus
        from graxia.packages.quant_os.core.events import NewsEvent

        bus = MagicMock(spec=EventBus)
        bus.publish = MagicMock()
        agent = SentimentAgent(bus=bus)

        async def mock_route(headline):
            from graxia.packages.quant_os.core.agents.llm_router import CascadeResult, ImpactLevel
            return CascadeResult(
                headline=headline,
                impact=ImpactLevel.HIGH,
                direction=-1,
                tier_used=1,
                confidence=0.85,
                reasoning="test high impact",
            )

        agent.router.route = mock_route
        agent.observe(NewsEvent(source="test", headline="Fed emergency rate cut"))

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(agent.act())
        finally:
            loop.close()

        assert result is not None
        assert result.regime_label == "HIGH_UNCERTAINTY"

        bus.publish.assert_called_once()
        call_args = bus.publish.call_args
        assert call_args[0][0] == "news.analyzed"

        event = call_args[0][1]
        assert hasattr(event, "headline")
        assert hasattr(event, "regime_label")
        assert hasattr(event, "bias")
        assert hasattr(event, "confidence")
        assert hasattr(event, "position_multiplier")
        assert hasattr(event, "source_provider")
        assert event.headline == "Fed emergency rate cut"
        assert event.regime_label == "HIGH_UNCERTAINTY"
        assert event.confidence == 0.85

    def test_no_bus_no_publish(self, mock_env):
        from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentAgent
        from graxia.packages.quant_os.core.events import NewsEvent

        agent = SentimentAgent()  # bus=None (default)

        async def mock_route(headline):
            from graxia.packages.quant_os.core.agents.llm_router import CascadeResult, ImpactLevel
            return CascadeResult(
                headline=headline,
                impact=ImpactLevel.LOW,
                direction=0,
                tier_used=1,
                confidence=0.4,
                reasoning="low impact",
            )

        agent.router.route = mock_route
        agent.observe(NewsEvent(source="test", headline="Routine earnings"))

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(agent.act())
        finally:
            loop.close()

        assert result is not None

    def test_bus_none_backward_compatible(self, mock_env):
        from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentAgent

        agent = SentimentAgent()
        assert agent._bus is None

        agent = SentimentAgent(bus=None)
        assert agent._bus is None

    def test_aggregate_crisis_publishes_correct_bias(self, mock_env):
        from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentAgent
        from graxia.packages.quant_os.core.event_bus import EventBus
        from graxia.packages.quant_os.core.events import NewsEvent

        bus = MagicMock(spec=EventBus)
        agent = SentimentAgent(bus=bus)

        call_n = {"n": 0}

        async def mock_route(headline):
            from graxia.packages.quant_os.core.agents.llm_router import CascadeResult, ImpactLevel
            call_n["n"] += 1
            if call_n["n"] == 1:
                return CascadeResult(
                    headline=headline,
                    impact=ImpactLevel.HIGH,
                    direction=-1,
                    tier_used=2,
                    confidence=0.95,
                    reasoning="crisis confirmed",
                )
            return CascadeResult(
                headline=headline,
                impact=ImpactLevel.LOW,
                direction=1,
                tier_used=1,
                confidence=0.6,
                reasoning="mild positive",
            )

        agent.router.route = mock_route
        agent.observe(NewsEvent(source="test", headline="Major bank collapses"))
        agent.observe(NewsEvent(source="test", headline="Tech earnings beat"))

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(agent.act())
        finally:
            loop.close()

        assert result is not None
        assert result.regime_label == "CRISIS"
        assert result.bias.value == "PANIC"

        event = bus.publish.call_args[0][1]
        assert event.regime_label == "CRISIS"
        assert event.bias == "PANIC"
        # Weighted average: (0.0*0.95 + 0.75*0.6) / (0.95+0.6) ≈ 0.29
        assert event.position_multiplier < 0.5  # Aggregated conservative
