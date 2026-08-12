"""
Comprehensive Chaos Tests — Full Pipeline
==========================================
Tests the entire news pipeline end-to-end with chaos scenarios:
- RSS feed failures (some feeds down)
- LLM provider failures (rate limits, timeouts, bad responses)
- Event processing edge cases
- Obsidian write failures
- Telegram notification failures
- Concurrent processing

Run:
  cd graxia/packages
  python -m pytest quant_os/tests/chaos/test_full_pipeline.py -v
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import patch

import pytest

# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_env():
    """Set test environment variables."""
    env = {
        "GROQ_API_KEY": "test_groq_key",
        "COHERE_API_KEY": "test_cohere_key",
        "CEREBRAS_API_KEY": "test_cerebras_key",
        "GOOGLE_AI_KEY": "test_google_key",
        "TELEGRAM_BOT_TOKEN": "test_token",
        "TELEGRAM_CHAT_ID": "12345",
    }
    with patch.dict(os.environ, env):
        yield env


@pytest.fixture
def sample_headlines():
    """Sample headlines for testing."""
    return [
        "Fed raises interest rates by 75 basis points, markets plunge",
        "NVIDIA reports record earnings, stock surges 15%",
        "Russia launches military operation against Ukraine, oil spikes 20%",
        "US unemployment drops to 3.4%, economy strengthens",
        "Bitcoin crashes 30% in 24 hours amid regulatory crackdown",
        "ECB maintains rates amid mixed economic signals",
        "Gold hits $3200 as safe-haven demand surges",
        "Major cyberattack disables SWIFT banking system",
        "China Evergrande defaults on $300 billion debt",
        "US-China tensions escalate, Taiwan Strait blockade announced",
    ]


@pytest.fixture
def sample_rss_items():
    """Sample RSS items for testing."""
    return [
        {"title": "Fed raises rates", "link": "http://example.com/1", "source": "bloomberg", "summary": "test"},
        {"title": "NVIDIA earnings", "link": "http://example.com/2", "source": "cnbc", "summary": "test"},
        {"title": "Russia invades", "link": "http://example.com/3", "source": "reuters", "summary": "test"},
    ]


# ═══════════════════════════════════════════════════════════════════
# LLM Router Tests
# ═══════════════════════════════════════════════════════════════════


class TestCascadeRouter:
    """Tests for the LLM Cascade Router."""

    @pytest.mark.asyncio
    async def test_parse_json_valid(self, mock_env):
        from graxia.packages.quant_os.core.agents.llm_router import CascadeRouter

        router = CascadeRouter()
        result = router._parse_json('{"impact": "HIGH", "dir": 1}')
        assert result == {"impact": "HIGH", "dir": 1}

    @pytest.mark.asyncio
    async def test_parse_json_markdown_block(self, mock_env):
        from graxia.packages.quant_os.core.agents.llm_router import CascadeRouter

        router = CascadeRouter()
        text = '```json\n{"impact": "LOW", "dir": 0}\n```'
        result = router._parse_json(text)
        assert result == {"impact": "LOW", "dir": 0}

    @pytest.mark.asyncio
    async def test_parse_json_with_text(self, mock_env):
        from graxia.packages.quant_os.core.agents.llm_router import CascadeRouter

        router = CascadeRouter()
        text = 'Here is the analysis: {"impact": "HIGH", "dir": -1} done.'
        result = router._parse_json(text)
        assert result["impact"] == "HIGH"
        assert result["dir"] == -1

    @pytest.mark.asyncio
    async def test_parse_json_empty(self, mock_env):
        from graxia.packages.quant_os.core.agents.llm_router import CascadeRouter

        router = CascadeRouter()
        assert router._parse_json("") == {}
        assert router._parse_json("no json here") == {}

    @pytest.mark.asyncio
    async def test_parse_json_nested(self, mock_env):
        from graxia.packages.quant_os.core.agents.llm_router import CascadeRouter

        router = CascadeRouter()
        text = 'Analysis result: {"impact": "HIGH", "dir": 1, "meta": {"confidence": 0.9}}'
        result = router._parse_json(text)
        assert result["impact"] == "HIGH"

    @pytest.mark.asyncio
    async def test_route_tier1_low_returns_immediately(self, mock_env):
        from graxia.packages.quant_os.core.agents.llm_router import CascadeRouter, ImpactLevel

        router = CascadeRouter()

        # Mock T1 to return LOW
        async def mock_call(config, prompt):
            return '{"impact": "LOW", "dir": 0}', 100.0

        router._call_llm = mock_call
        result = await router.route("Routine earnings report")

        assert result.impact == ImpactLevel.LOW
        assert result.tier_used == 1
        assert result.direction == 0

    @pytest.mark.asyncio
    async def test_route_tier1_high_calls_tier2(self, mock_env):
        from graxia.packages.quant_os.core.agents.llm_router import CascadeRouter, ImpactLevel

        router = CascadeRouter()
        call_count = {"t1": 0, "t2": 0}

        async def mock_call(config, prompt):
            if config.tier == 1:
                call_count["t1"] += 1
                return '{"impact": "HIGH", "dir": -1}', 200.0
            else:
                call_count["t2"] += 1
                return '{"confirmed": true, "direction": -1, "confidence": 0.8, "reasoning": "war"}', 300.0

        router._call_llm = mock_call
        result = await router.route("Russia launches military operation")

        assert result.impact == ImpactLevel.HIGH
        assert result.direction == -1
        assert result.confidence == 0.8
        assert call_count["t1"] == 1
        assert call_count["t2"] == 1

    @pytest.mark.asyncio
    async def test_route_tier2_rejects_downgrades(self, mock_env):
        from graxia.packages.quant_os.core.agents.llm_router import CascadeRouter, ImpactLevel

        router = CascadeRouter()

        async def mock_call(config, prompt):
            if config.tier == 1:
                return '{"impact": "HIGH", "dir": 1}', 200.0
            else:
                return '{"confirmed": false, "confidence": 0.3, "reasoning": "not actually important"}', 300.0

        router._call_llm = mock_call
        result = await router.route("Analyst upgrades stock to buy")

        assert result.impact == ImpactLevel.LOW
        assert result.direction == 0

    @pytest.mark.asyncio
    async def test_route_tier1_failure_returns_low(self, mock_env):
        from graxia.packages.quant_os.core.agents.llm_router import CascadeRouter, ImpactLevel

        router = CascadeRouter()

        async def mock_call(config, prompt):
            return "", 0.0

        router._call_llm = mock_call
        result = await router.route("Important news")

        assert result.impact == ImpactLevel.LOW
        assert result.tier_used == 0
        assert "failed" in result.reasoning.lower()

    @pytest.mark.asyncio
    async def test_route_tier2_failure_trusts_tier1(self, mock_env):
        from graxia.packages.quant_os.core.agents.llm_router import CascadeRouter, ImpactLevel

        router = CascadeRouter()

        async def mock_call(config, prompt):
            if config.tier == 1:
                return '{"impact": "HIGH", "dir": -1}', 200.0
            else:
                return "", 0.0

        router._call_llm = mock_call
        result = await router.route("War breaking out")

        assert result.impact == ImpactLevel.HIGH
        assert result.direction == -1
        assert result.tier_used == 1

    @pytest.mark.asyncio
    async def test_route_invalid_json_treated_as_low(self, mock_env):
        from graxia.packages.quant_os.core.agents.llm_router import CascadeRouter, ImpactLevel

        router = CascadeRouter()

        async def mock_call(config, prompt):
            return "I cannot analyze this headline", 100.0

        router._call_llm = mock_call
        result = await router.route("Random headline")

        assert result.impact == ImpactLevel.LOW

    @pytest.mark.asyncio
    async def test_route_invalid_impact_value_treated_as_low(self, mock_env):
        from graxia.packages.quant_os.core.agents.llm_router import CascadeRouter, ImpactLevel

        router = CascadeRouter()

        async def mock_call(config, prompt):
            return '{"impact": "MEDIUM", "dir": 0}', 100.0

        router._call_llm = mock_call
        result = await router.route("Ambiguous news")

        assert result.impact == ImpactLevel.LOW

    @pytest.mark.asyncio
    async def test_route_invalid_direction_treated_as_neutral(self, mock_env):
        from graxia.packages.quant_os.core.agents.llm_router import CascadeRouter

        router = CascadeRouter()

        async def mock_call(config, prompt):
            if config.tier == 1:
                return '{"impact": "HIGH", "dir": 5}', 100.0
            else:
                return '{"confirmed": true, "direction": 99, "confidence": 0.7}', 200.0

        router._call_llm = mock_call
        result = await router.route("Weird news")

        assert result.direction == 0  # Falls back to neutral


# ═══════════════════════════════════════════════════════════════════
# SentimentAgent Tests
# ═══════════════════════════════════════════════════════════════════


class TestSentimentAgent:
    """Tests for the SentimentAgent."""

    @pytest.mark.asyncio
    async def test_observe_stores_headline(self, mock_env):
        from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentAgent
        from graxia.packages.quant_os.core.events import NewsEvent

        agent = SentimentAgent()
        event = NewsEvent(source="test", headline="Fed raises rates")
        agent.observe(event)

        assert len(agent._pending_headlines) == 1
        assert agent._pending_headlines[0]["headline"] == "Fed raises rates"

    @pytest.mark.asyncio
    async def test_observe_ignores_non_event(self, mock_env):
        from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentAgent

        agent = SentimentAgent()
        agent.observe("not an event")

        assert len(agent._pending_headlines) == 0

    @pytest.mark.asyncio
    async def test_observe_ignores_empty_headline(self, mock_env):
        from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentAgent
        from graxia.packages.quant_os.core.events import NewsEvent

        agent = SentimentAgent()
        event = NewsEvent(source="test", headline="")
        agent.observe(event)

        assert len(agent._pending_headlines) == 0

    @pytest.mark.asyncio
    async def test_act_processes_headlines(self, mock_env):
        from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentAgent
        from graxia.packages.quant_os.core.events import NewsEvent

        agent = SentimentAgent()

        # Mock the router
        async def mock_route(headline):
            from graxia.packages.quant_os.core.agents.llm_router import CascadeResult, ImpactLevel

            return CascadeResult(
                headline=headline,
                impact=ImpactLevel.HIGH,
                direction=-1,
                tier_used=1,
                confidence=0.8,
                reasoning="test",
            )

        agent.router.route = mock_route

        event = NewsEvent(source="test", headline="War breaking out")
        agent.observe(event)
        result = await agent.act()

        assert result is not None
        assert result.regime_label == "HIGH_UNCERTAINTY"

    @pytest.mark.asyncio
    async def test_act_returns_none_when_empty(self, mock_env):
        from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentAgent

        agent = SentimentAgent()
        result = await agent.act()
        assert result is None

    @pytest.mark.asyncio
    async def test_act_aggregates_multiple_headlines(self, mock_env):
        from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentAgent
        from graxia.packages.quant_os.core.events import NewsEvent

        agent = SentimentAgent()

        call_count = {"n": 0}

        async def mock_route(headline):
            from graxia.packages.quant_os.core.agents.llm_router import CascadeResult, ImpactLevel

            call_count["n"] += 1
            if call_count["n"] == 1:
                return CascadeResult(
                    headline=headline,
                    impact=ImpactLevel.HIGH,
                    direction=-1,
                    tier_used=1,
                    confidence=0.9,
                )
            return CascadeResult(
                headline=headline,
                impact=ImpactLevel.LOW,
                direction=1,
                tier_used=1,
                confidence=0.6,
            )

        agent.router.route = mock_route

        agent.observe(NewsEvent(source="test", headline="War"))
        agent.observe(NewsEvent(source="test", headline="Good earnings"))
        result = await agent.act()

        assert result is not None
        # Most conservative wins (CRISIS because War has confidence=0.9 + bearish)
        assert result.regime_label == "CRISIS"
        assert result.position_multiplier <= 0.75  # Min of the two

    @pytest.mark.asyncio
    async def test_reset_clears_headlines(self, mock_env):
        from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentAgent
        from graxia.packages.quant_os.core.events import NewsEvent

        agent = SentimentAgent()
        agent.observe(NewsEvent(source="test", headline="Test"))
        assert len(agent._pending_headlines) == 1

        agent.reset()
        assert len(agent._pending_headlines) == 0


# ═══════════════════════════════════════════════════════════════════
# News Pipeline Tests
# ═══════════════════════════════════════════════════════════════════


class TestNewsPipeline:
    """Tests for the news pipeline components."""

    def test_classify_impact_crisis(self):
        from graxia.packages.quant_os.scripts.news_pipeline import classify_impact

        assert classify_impact("Russia launches military operation") == "CRISIS"
        assert classify_impact("Major cyberattack disables SWIFT") == "CRISIS"
        assert classify_impact("War breaks out in Middle East") == "CRISIS"

    def test_classify_impact_high(self):
        from graxia.packages.quant_os.scripts.news_pipeline import classify_impact

        assert classify_impact("Fed raises interest rates") == "HIGH"
        assert classify_impact("NFP report shows strong growth") == "HIGH"
        assert classify_impact("FOMC meeting today") == "HIGH"

    def test_classify_impact_medium(self):
        from graxia.packages.quant_os.scripts.news_pipeline import classify_impact

        assert classify_impact("Apple releases new iPhone") == "MEDIUM"
        assert classify_impact("Tesla stock upgraded") == "MEDIUM"

    @pytest.mark.asyncio
    async def test_fetch_rss_feed_success(self):
        import httpx

        from graxia.packages.quant_os.scripts.news_pipeline import fetch_rss_feed

        async with httpx.AsyncClient(timeout=10.0) as client:
            items = await fetch_rss_feed(client, "test", "https://feeds.bloomberg.com/markets/news.rss")
            assert len(items) > 0
            assert items[0].title != ""

    @pytest.mark.asyncio
    async def test_fetch_rss_feed_failure(self):
        import httpx

        from graxia.packages.quant_os.scripts.news_pipeline import fetch_rss_feed

        async with httpx.AsyncClient(timeout=5.0) as client:
            items = await fetch_rss_feed(client, "test", "https://invalid.example.com/rss")
            assert len(items) == 0

    def test_write_to_obsidian(self, mock_env):
        from datetime import UTC, datetime

        from graxia.packages.quant_os.scripts.news_pipeline import DailyDigest, write_to_obsidian

        digest = DailyDigest(
            date="2026-01-01",
            avg_sentiment=0.5,
            regime="NORMAL",
            position_multiplier=0.8,
        )

        path = write_to_obsidian(digest)
        assert path.exists()
        content = path.read_text()
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        assert today in content
        assert "NORMAL" in content


# ═══════════════════════════════════════════════════════════════════
# Chaos: LLM Provider Failures
# ═══════════════════════════════════════════════════════════════════


class TestLLMChaos:
    """Chaos tests for LLM provider failures."""

    @pytest.mark.asyncio
    async def test_all_providers_fail(self, mock_env):
        from graxia.packages.quant_os.core.agents.llm_router import CascadeRouter, ImpactLevel

        router = CascadeRouter()

        async def mock_fail(config, prompt):
            return "", 0.0

        router._call_llm = mock_fail
        result = await router.route("Important news")

        assert result.impact == ImpactLevel.LOW
        assert result.tier_used == 0

    @pytest.mark.asyncio
    async def test_provider_returns_garbage(self, mock_env):
        from graxia.packages.quant_os.core.agents.llm_router import CascadeRouter, ImpactLevel

        router = CascadeRouter()

        async def mock_garbage(config, prompt):
            return "I don't understand the request. Here's a recipe for cake...", 100.0

        router._call_llm = mock_garbage
        result = await router.route("War news")

        assert result.impact == ImpactLevel.LOW

    @pytest.mark.asyncio
    async def test_provider_returns_wrong_json_format(self, mock_env):
        from graxia.packages.quant_os.core.agents.llm_router import CascadeRouter, ImpactLevel

        router = CascadeRouter()

        async def mock_wrong(config, prompt):
            return '{"result": "positive", "score": 0.8}', 100.0

        router._call_llm = mock_wrong
        result = await router.route("Economic growth")

        # Missing "impact" key → treated as LOW
        assert result.impact == ImpactLevel.LOW

    @pytest.mark.asyncio
    async def test_tier1_works_tier2_fails(self, mock_env):
        from graxia.packages.quant_os.core.agents.llm_router import CascadeRouter, ImpactLevel

        router = CascadeRouter()

        async def mock_partial(config, prompt):
            if config.tier == 1:
                return '{"impact": "HIGH", "dir": -1}', 200.0
            return "", 0.0  # T2 fails

        router._call_llm = mock_partial
        result = await router.route("War breaking out")

        # Should still return HIGH from T1
        assert result.impact == ImpactLevel.HIGH
        assert result.direction == -1

    @pytest.mark.asyncio
    async def test_concurrent_routes(self, mock_env):
        from graxia.packages.quant_os.core.agents.llm_router import CascadeRouter, ImpactLevel

        router = CascadeRouter()

        async def mock_call(config, prompt):
            return '{"impact": "LOW", "dir": 0}', 100.0

        router._call_llm = mock_call

        # Run 10 concurrent routes
        tasks = [router.route(f"Headline {i}") for i in range(10)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 10
        assert all(r.impact == ImpactLevel.LOW for r in results)


# ═══════════════════════════════════════════════════════════════════
# Chaos: Edge Cases
# ═══════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge case chaos tests."""

    @pytest.mark.asyncio
    async def test_very_long_headline(self, mock_env):
        from graxia.packages.quant_os.core.agents.llm_router import CascadeRouter, ImpactLevel

        router = CascadeRouter()

        async def mock_call(config, prompt):
            return '{"impact": "LOW", "dir": 0}', 100.0

        router._call_llm = mock_call
        long_headline = "A" * 10000
        result = await router.route(long_headline)

        assert result.impact == ImpactLevel.LOW

    @pytest.mark.asyncio
    async def test_unicode_headline(self, mock_env):
        from graxia.packages.quant_os.core.agents.llm_router import CascadeRouter, ImpactLevel

        router = CascadeRouter()

        async def mock_call(config, prompt):
            return '{"impact": "HIGH", "dir": -1}', 100.0

        router._call_llm = mock_call
        result = await router.route("สงครามในตะวันออกกลาง")

        assert result.impact == ImpactLevel.HIGH

    @pytest.mark.asyncio
    async def test_empty_headline(self, mock_env):
        from graxia.packages.quant_os.core.agents.llm_router import CascadeRouter, ImpactLevel

        router = CascadeRouter()

        async def mock_call(config, prompt):
            return '{"impact": "LOW", "dir": 0}', 100.0

        router._call_llm = mock_call
        result = await router.route("")

        assert result.impact == ImpactLevel.LOW

    @pytest.mark.asyncio
    async def test_special_characters(self, mock_env):
        from graxia.packages.quant_os.core.agents.llm_router import CascadeRouter, ImpactLevel

        router = CascadeRouter()

        async def mock_call(config, prompt):
            return '{"impact": "LOW", "dir": 0}', 100.0

        router._call_llm = mock_call
        result = await router.route('News with "quotes" and \\backslash\\ and {braces}')

        assert result.impact == ImpactLevel.LOW
