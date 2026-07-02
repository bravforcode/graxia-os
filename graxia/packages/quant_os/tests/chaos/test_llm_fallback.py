"""Chaos Tests — CascadeRouter provider fallback chain."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from graxia.packages.quant_os.core.agents.llm_router import (
    TIER1_PROVIDERS,
    CascadeRouter,
    ImpactLevel,
    ProviderConfig,
)


@pytest.fixture
def router():
    return CascadeRouter()


def _mock_response(content: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return resp


def _empty_response() -> MagicMock:
    return _mock_response("", status_code=200)


def _error_response(status_code: int = 429) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"error": "rate limited"}
    return resp


def _make_mock_client(*responses):
    client = AsyncMock()
    client.is_closed = False
    client.post = AsyncMock(side_effect=list(responses))
    return client


class TestProviderConfigCompat:
    def test_is_openai_compatible_default(self):
        cfg = ProviderConfig(name="test", tier=1, api_key_env="K", base_url="http://x", model="m")
        assert cfg.is_openai_compatible is True

    def test_tier1_providers_count(self):
        assert len(TIER1_PROVIDERS) == 3
        assert TIER1_PROVIDERS[0].name == "groq-t1"
        assert TIER1_PROVIDERS[1].name == "cerebras"
        assert TIER1_PROVIDERS[2].name == "openrouter"

    def test_tier1_providers_compatible(self):
        for p in TIER1_PROVIDERS:
            assert p.is_openai_compatible is True


class TestCallLlmChain:
    @pytest.mark.asyncio
    async def test_returns_first_success(self, router):
        with patch.dict(os.environ, {"GROQ_API_KEY": "k1", "CEREBRAS_API_KEY": "k2", "OPENROUTER_API_KEY": "k3"}):
            router._client = _make_mock_client(
                _mock_response('{"impact": "HIGH", "dir": 1}'),
            )
            response, latency, provider = await router._call_llm_chain(TIER1_PROVIDERS, "test prompt")
            assert response == '{"impact": "HIGH", "dir": 1}'
            assert provider.name == "groq-t1"
            assert router._client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_fallback_on_empty_response(self, router):
        with patch.dict(os.environ, {"GROQ_API_KEY": "k1", "CEREBRAS_API_KEY": "k2", "OPENROUTER_API_KEY": "k3"}):
            router._client = _make_mock_client(
                _empty_response(),
                _mock_response('{"impact": "LOW", "dir": 0}'),
            )
            response, latency, provider = await router._call_llm_chain(TIER1_PROVIDERS, "test prompt")
            assert response == '{"impact": "LOW", "dir": 0}'
            assert provider.name == "cerebras"
            assert router._client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_fallback_on_exception(self, router):
        with patch.dict(os.environ, {"GROQ_API_KEY": "k1", "CEREBRAS_API_KEY": "k2", "OPENROUTER_API_KEY": "k3"}):
            router._client = _make_mock_client(
                _error_response(500),
                _mock_response('{"impact": "LOW", "dir": 0}'),
            )
            response, latency, provider = await router._call_llm_chain(TIER1_PROVIDERS, "test prompt")
            assert response == '{"impact": "LOW", "dir": 0}'
            assert provider.name == "cerebras"

    @pytest.mark.asyncio
    async def test_fallback_on_429(self, router):
        with patch.dict(os.environ, {"GROQ_API_KEY": "k1", "CEREBRAS_API_KEY": "k2", "OPENROUTER_API_KEY": "k3"}):
            router._client = _make_mock_client(
                _error_response(429),
                _mock_response('{"impact": "HIGH", "dir": 1}'),
            )
            response, latency, provider = await router._call_llm_chain(TIER1_PROVIDERS, "test prompt")
            assert response == '{"impact": "HIGH", "dir": 1}'
            assert provider.name == "cerebras"

    @pytest.mark.asyncio
    async def test_all_providers_fail(self, router):
        with patch.dict(os.environ, {"GROQ_API_KEY": "k1", "CEREBRAS_API_KEY": "k2", "OPENROUTER_API_KEY": "k3"}):
            router._client = _make_mock_client(
                _empty_response(),
                _empty_response(),
                _empty_response(),
            )
            response, latency, provider = await router._call_llm_chain(TIER1_PROVIDERS, "test prompt")
            assert response == ""
            assert provider is None

    @pytest.mark.asyncio
    async def test_no_api_keys(self, router):
        with patch.dict(os.environ, {"GROQ_API_KEY": "", "CEREBRAS_API_KEY": "", "OPENROUTER_API_KEY": ""}):
            response, latency, provider = await router._call_llm_chain(TIER1_PROVIDERS, "test prompt")
            assert response == ""
            assert provider is None


class TestRouteFallback:
    @pytest.mark.asyncio
    async def test_fallback_triggers_when_primary_returns_empty(self, router):
        """Primary Groq returns empty, Cerebras fallback succeeds with LOW impact."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "k1", "CEREBRAS_API_KEY": "k2", "OPENROUTER_API_KEY": "k3"}):
            tier1_data = json.dumps({"impact": "LOW", "dir": 0})
            router._client = _make_mock_client(
                _empty_response(),
                _mock_response(tier1_data),
            )
            result = await router.route("Test headline")
            assert result.impact == ImpactLevel.LOW
            assert result.direction == 0
            assert result.tier_used == 1
            assert router._client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_no_fallback_when_primary_succeeds(self, router):
        """Primary Groq succeeds, no fallback needed."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "k1", "CEREBRAS_API_KEY": "k2", "OPENROUTER_API_KEY": "k3"}):
            tier1_data = json.dumps({"impact": "LOW", "dir": 1})
            router._client = _make_mock_client(
                _mock_response(tier1_data),
            )
            result = await router.route("Test headline")
            assert result.impact == ImpactLevel.LOW
            assert result.direction == 1
            assert result.tier_used == 1
            assert router._client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_all_t1_fail_returns_low(self, router):
        """All T1 providers fail — returns LOW impact."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "k1", "CEREBRAS_API_KEY": "k2", "OPENROUTER_API_KEY": "k3"}):
            router._client = _make_mock_client(
                _empty_response(),
                _empty_response(),
                _empty_response(),
            )
            result = await router.route("Test headline")
            assert result.impact == ImpactLevel.LOW
            assert result.direction == 0
            assert result.reasoning == "Tier 1 failed"

    @pytest.mark.asyncio
    async def test_high_impact_proceeds_to_tier2(self, router):
        """HIGH impact from fallback triggers tier2 validation."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "k1", "CEREBRAS_API_KEY": "k2", "OPENROUTER_API_KEY": "k3"}):
            tier1_data = json.dumps({"impact": "HIGH", "dir": 1})
            tier2_data = json.dumps({"confirmed": True, "direction": 1, "confidence": 0.8, "reasoning": "war"})
            router._client = _make_mock_client(
                _empty_response(),
                _mock_response(tier1_data),
                _mock_response(tier2_data),
            )
            result = await router.route("War escalation")
            assert result.impact == ImpactLevel.HIGH
            assert result.direction == 1
            assert result.tier_used == 2
            assert result.confidence == 0.8
            assert router._client.post.call_count == 3
