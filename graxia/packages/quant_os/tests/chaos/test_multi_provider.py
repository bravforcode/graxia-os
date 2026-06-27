"""
Chaos Tests — Multi-Provider SentimentAgent.

OBSOLETE: The old 6-provider architecture (Groq, Google, Cerebras, OpenRouter,
Cohere, Cloudflare) was replaced by CascadeRouter (3-tier: Cerebras->Groq->Gemini)
in Phase 3.1. See tests/test_phase_3_1_pillars.py for current tests.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Obsolete: 6-provider architecture replaced by CascadeRouter")

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ═══════════════════════════════════════════════════════════════════
# Provider Base Tests
# ═══════════════════════════════════════════════════════════════════


class TestProviderAvailability:
    """Test provider availability checks."""

    def test_groq_available_with_key(self):
        from graxia.packages.quant_os.core.agents.sentiment_agent import GroqProvider, ProviderConfig

        with patch.dict(os.environ, {"GROQ_API_KEY": "test_key"}):
            config = ProviderConfig(name="groq", api_key_env="GROQ_API_KEY", base_url="", model="")
            provider = GroqProvider(config, MagicMock())
            assert provider.is_available

    def test_groq_unavailable_without_key(self):
        from graxia.packages.quant_os.core.agents.sentiment_agent import GroqProvider, ProviderConfig

        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            config = ProviderConfig(name="groq", api_key_env="GROQ_API_KEY", base_url="", model="")
            provider = GroqProvider(config, MagicMock())
            assert not provider.is_available

    def test_all_providers_check(self):
        from graxia.packages.quant_os.core.agents.sentiment_agent import create_providers

        with patch.dict(
            os.environ,
            {
                "GROQ_API_KEY": "key1",
                "GOOGLE_AI_KEY": "",
                "CEREBRAS_API_KEY": "key3",
                "OPENROUTER_API_KEY": "",
                "COHERE_API_KEY": "key5",
                "CF_API_TOKEN": "",
            },
        ):
            client = MagicMock()
            providers = create_providers(client)
            available = [p for p in providers if p.is_available]
            assert len(available) == 3  # groq, cerebras, cohere


# ═══════════════════════════════════════════════════════════════════
# GroqProvider Tests
# ═══════════════════════════════════════════════════════════════════


class TestGroqProviderChaos:
    """Chaos tests for GroqProvider."""

    @pytest.fixture
    def provider(self):
        from graxia.packages.quant_os.core.agents.sentiment_agent import GroqProvider, ProviderConfig

        config = ProviderConfig(
            name="groq",
            api_key_env="GROQ_API_KEY",
            base_url="https://api.groq.com/openai/v1/chat/completions",
            model="llama3-70b-8192",
        )
        client = AsyncMock()
        return GroqProvider(config, client), client

    @pytest.mark.asyncio
    async def test_analyze_success(self, provider):
        """Normal response — should parse correctly."""
        groq, client = provider
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "sentiment_score": -0.5,
                                "confidence": 0.8,
                                "regime_override": "NORMAL",
                                "position_multiplier": 0.7,
                                "reasoning": "bearish",
                            }
                        )
                    }
                }
            ]
        }
        client.post = AsyncMock(return_value=mock_resp)

        result = await groq.analyze("Fed raises rates")
        assert result is not None
        assert result.sentiment_score == -0.5
        assert result.provider == "groq"

    @pytest.mark.asyncio
    async def test_analyze_timeout(self, provider):
        """Timeout — should return None."""
        groq, client = provider
        client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        result = await groq.analyze("Test headline")
        assert result is None

    @pytest.mark.asyncio
    async def test_analyze_http_error(self, provider):
        """HTTP 500 — should return None."""
        groq, client = provider
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        client.post = AsyncMock(return_value=mock_resp)

        result = await groq.analyze("Test headline")
        assert result is None

    @pytest.mark.asyncio
    async def test_analyze_malformed_json(self, provider):
        """LLM returns non-JSON — should return None."""
        groq, client = provider
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "I don't understand"}}]}
        client.post = AsyncMock(return_value=mock_resp)

        result = await groq.analyze("Test headline")
        assert result is None

    @pytest.mark.asyncio
    async def test_analyze_json_in_markdown(self, provider):
        """JSON wrapped in ```json — should extract correctly."""
        groq, client = provider
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '```json\n{"sentiment_score": 0.3, "confidence": 0.7, "regime_override": "NORMAL", "position_multiplier": 0.9, "reasoning": "mild"}\n```'
                    }
                }
            ]
        }
        client.post = AsyncMock(return_value=mock_resp)

        result = await groq.analyze("Test headline")
        assert result is not None
        assert result.sentiment_score == 0.3


# ═══════════════════════════════════════════════════════════════════
# Multi-Provider Parallel Execution
# ═══════════════════════════════════════════════════════════════════


class TestMultiProviderParallel:
    """Test parallel execution across providers."""

    @pytest.fixture
    def agent(self):
        from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentAgent

        return SentimentAgent()

    @pytest.mark.asyncio
    async def test_distributes_headlines_across_providers(self, agent):
        """Headlines should be distributed round-robin across providers."""
        from graxia.packages.quant_os.core.agents.sentiment_agent import GroqProvider, ProviderConfig

        # Create 2 mock providers
        mock_providers = []
        for name in ["groq", "cerebras"]:
            config = ProviderConfig(name=name, api_key_env="GROQ_API_KEY", base_url="", model="")
            p = GroqProvider(config, AsyncMock())
            p._api_key = "mock_key"
            mock_providers.append(p)

        agent._providers = mock_providers
        agent._pending_headlines = [
            {"headline": "News 1", "source": "test", "timestamp": "2026-01-01"},
            {"headline": "News 2", "source": "test", "timestamp": "2026-01-01"},
            {"headline": "News 3", "source": "test", "timestamp": "2026-01-01"},
        ]

        # Mock analyze to track which provider gets which headline
        assignments = {}

        async def mock_analyze(headline):
            provider_name = "unknown"
            for p in mock_providers:
                if headline in ["News 1", "News 3"]:
                    provider_name = "groq"
                else:
                    provider_name = "cerebras"
            assignments.setdefault(provider_name, []).append(headline)
            from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentResult

            return SentimentResult(
                headline=headline,
                provider=provider_name,
                sentiment_score=0.5,
                confidence=0.8,
                regime_override="NORMAL",
                position_multiplier=1.0,
                reasoning="test",
            )

        for p in mock_providers:
            p.analyze = mock_analyze

        # Mock create_providers to return our mock providers
        with patch(
            "graxia.packages.quant_os.core.agents.sentiment_agent.create_providers", return_value=mock_providers
        ):
            agent._client = AsyncMock()
            result = await agent.act()

        assert result is not None
        assert result["headline_count"] == 3

    @pytest.mark.asyncio
    async def test_provider_failure_does_not_block_others(self, agent):
        """One provider failing should not block others."""
        from graxia.packages.quant_os.core.agents.sentiment_agent import (
            SentimentResult,
        )

        # Provider 1: fails
        p1 = MagicMock()
        p1.config.name = "failing"
        p1.is_available = True
        p1.analyze = AsyncMock(side_effect=Exception("provider crashed"))

        # Provider 2: succeeds
        p2 = MagicMock()
        p2.config.name = "working"
        p2.is_available = True

        async def success_analyze(headline):
            return SentimentResult(
                headline=headline,
                provider="working",
                sentiment_score=0.7,
                confidence=0.9,
                regime_override="NORMAL",
                position_multiplier=1.0,
                reasoning="good",
            )

        p2.analyze = success_analyze

        agent._providers = [p1, p2]
        # 2 headlines: round-robin assigns News 1 → p1 (fails), News 2 → p2 (works)
        agent._pending_headlines = [
            {"headline": "News 1", "source": "test", "timestamp": "2026-01-01"},
            {"headline": "News 2", "source": "test", "timestamp": "2026-01-01"},
        ]

        with patch("graxia.packages.quant_os.core.agents.sentiment_agent.create_providers", return_value=[p1, p2]):
            agent._client = AsyncMock()
            result = await agent.act()

        assert result is not None
        assert result["headline_count"] == 1
        assert result["provider_breakdown"]["working"] == 1

    @pytest.mark.asyncio
    async def test_all_providers_fail(self, agent):
        """All providers failing — should return None."""
        from graxia.packages.quant_os.core.agents.sentiment_agent import GroqProvider, ProviderConfig

        config = ProviderConfig(name="failing", api_key_env="GROQ_API_KEY", base_url="", model="")
        p = GroqProvider(config, AsyncMock())
        p._api_key = "mock_key"
        p.analyze = AsyncMock(side_effect=Exception("crashed"))

        agent._providers = [p]
        agent._pending_headlines = [
            {"headline": "News 1", "source": "test", "timestamp": "2026-01-01"},
        ]

        with patch("graxia.packages.quant_os.core.agents.sentiment_agent.create_providers", return_value=[p]):
            agent._client = AsyncMock()
            result = await agent.act()

        assert result is None


# ═══════════════════════════════════════════════════════════════════
# Result Aggregation
# ═══════════════════════════════════════════════════════════════════


class TestResultAggregation:
    """Test result aggregation logic."""

    @pytest.fixture
    def agent(self):
        from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentAgent

        return SentimentAgent()

    def test_average_sentiment(self, agent):
        """Average sentiment should be calculated correctly."""
        from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentResult

        results = [
            SentimentResult("H1", "groq", 0.8, 0.9, "NORMAL", 1.0, "bullish"),
            SentimentResult("H2", "cerebras", -0.4, 0.7, "NORMAL", 0.8, "bearish"),
        ]
        output = agent._aggregate_results(results, [{"headline": "H1"}, {"headline": "H2"}])
        # Average of 0.8 and -0.4 = 0.2
        assert abs(output["sentiment_score"] - 0.2) < 0.01

    def test_worst_case_multiplier(self, agent):
        """Position multiplier should be worst case (min)."""
        from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentResult

        results = [
            SentimentResult("H1", "groq", 0.5, 0.8, "NORMAL", 1.0, "ok"),
            SentimentResult("H2", "cerebras", -0.9, 0.95, "CRISIS", 0.0, "crisis"),
        ]
        output = agent._aggregate_results(results, [{"headline": "H1"}, {"headline": "H2"}])
        assert output["position_multiplier"] == 0.0
        assert output["regime_override"] == "CRISIS"

    def test_regime_priority(self, agent):
        """CRISIS should override HIGH_UNCERTAINTY should override NORMAL."""
        from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentResult

        results = [
            SentimentResult("H1", "groq", 0.1, 0.8, "NORMAL", 1.0, "ok"),
            SentimentResult("H2", "cerebras", -0.3, 0.7, "HIGH_UNCERTAINTY", 0.5, "uncertain"),
            SentimentResult("H3", "cohere", -0.9, 0.9, "CRISIS", 0.0, "crisis"),
        ]
        output = agent._aggregate_results(results, [{"headline": "H1"}, {"headline": "H2"}, {"headline": "H3"}])
        assert output["regime_override"] == "CRISIS"

    def test_provider_breakdown(self, agent):
        """Provider breakdown should count results per provider."""
        from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentResult

        results = [
            SentimentResult("H1", "groq", 0.5, 0.8, "NORMAL", 1.0, "ok"),
            SentimentResult("H2", "groq", 0.3, 0.7, "NORMAL", 0.9, "ok"),
            SentimentResult("H3", "cerebras", -0.2, 0.6, "NORMAL", 0.8, "mild"),
        ]
        output = agent._aggregate_results(results, [{"headline": "H1"}, {"headline": "H2"}, {"headline": "H3"}])
        assert output["provider_breakdown"]["groq"] == 2
        assert output["provider_breakdown"]["cerebras"] == 1
        assert output["provider_count"] == 2


# ═══════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge case chaos tests."""

    @pytest.fixture
    def agent(self):
        from graxia.packages.quant_os.core.agents.sentiment_agent import SentimentAgent

        return SentimentAgent()

    @pytest.mark.asyncio
    async def test_no_providers_configured(self, agent):
        """No API keys set — should return None."""
        with patch.dict(
            os.environ,
            {
                "GROQ_API_KEY": "",
                "GOOGLE_AI_KEY": "",
                "CEREBRAS_API_KEY": "",
                "OPENROUTER_API_KEY": "",
                "COHERE_API_KEY": "",
                "CF_API_TOKEN": "",
            },
        ):
            agent._pending_headlines = [{"headline": "Test", "source": "test", "timestamp": "2026-01-01"}]
            agent._client = None
            agent._providers = None
            result = await agent.act()
            assert result is None

    @pytest.mark.asyncio
    async def test_duplicate_headlines(self, agent):
        """Duplicate headlines — should handle gracefully."""
        from graxia.packages.quant_os.core.agents.sentiment_agent import GroqProvider, ProviderConfig, SentimentResult

        config = ProviderConfig(name="groq", api_key_env="GROQ_API_KEY", base_url="", model="")
        p = GroqProvider(config, AsyncMock())
        p._api_key = "mock"

        async def analyze(headline):
            return SentimentResult(headline, "groq", 0.5, 0.8, "NORMAL", 1.0, "test")

        p.analyze = analyze

        agent._providers = [p]
        agent._pending_headlines = [
            {"headline": "Same news", "source": "test", "timestamp": "2026-01-01"},
            {"headline": "Same news", "source": "test", "timestamp": "2026-01-01"},
        ]

        with patch("graxia.packages.quant_os.core.agents.sentiment_agent.create_providers", return_value=[p]):
            agent._client = AsyncMock()
            result = await agent.act()

        assert result is not None
        assert result["headline_count"] == 2

    @pytest.mark.asyncio
    async def test_very_long_headline(self, agent):
        """Very long headline — should not crash."""
        from graxia.packages.quant_os.core.agents.sentiment_agent import GroqProvider, ProviderConfig, SentimentResult

        config = ProviderConfig(name="groq", api_key_env="GROQ_API_KEY", base_url="", model="")
        p = GroqProvider(config, AsyncMock())
        p._api_key = "mock"

        async def analyze(headline):
            return SentimentResult(headline[:50], "groq", 0.5, 0.8, "NORMAL", 1.0, "test")

        p.analyze = analyze

        agent._providers = [p]
        long_headline = "A" * 10000
        agent._pending_headlines = [{"headline": long_headline, "source": "test", "timestamp": "2026-01-01"}]

        with patch("graxia.packages.quant_os.core.agents.sentiment_agent.create_providers", return_value=[p]):
            agent._client = AsyncMock()
            result = await agent.act()

        assert result is not None

    def test_observe_ignores_empty_headline(self, agent):
        """Empty headline — should not add to pending."""
        from graxia.packages.quant_os.core.events import Event

        event = Event(source="test")
        agent.observe(event)
        assert len(agent._pending_headlines) == 0

    def test_observe_ignores_non_event(self, agent):
        """Non-Event object — should not crash."""
        agent.observe("not an event")
        agent.observe(None)
        assert len(agent._pending_headlines) == 0

    @pytest.mark.asyncio
    async def test_concurrent_act_calls(self, agent):
        """Multiple concurrent act() — no race condition."""
        from graxia.packages.quant_os.core.agents.sentiment_agent import GroqProvider, ProviderConfig, SentimentResult

        config = ProviderConfig(name="groq", api_key_env="GROQ_API_KEY", base_url="", model="")
        p = GroqProvider(config, AsyncMock())
        p._api_key = "mock"

        async def analyze(headline):
            return SentimentResult(headline, "groq", 0.5, 0.8, "NORMAL", 1.0, "test")

        p.analyze = analyze

        agent._providers = [p]
        agent._pending_headlines = [{"headline": "Test", "source": "test", "timestamp": "2026-01-01"}]

        with patch("graxia.packages.quant_os.core.agents.sentiment_agent.create_providers", return_value=[p]):
            agent._client = AsyncMock()
            tasks = [agent.act() for _ in range(3)]
            results = await asyncio.gather(*tasks)
            assert all(r is None or isinstance(r, dict) for r in results)
