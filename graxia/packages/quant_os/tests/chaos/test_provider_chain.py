"""Chaos Tests — T1 provider chain order and fallback behavior."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from graxia.packages.quant_os.core.agents.llm_router import (
    CascadeRouter,
    ImpactLevel,
    TIER1_CEREBRAS,
    TIER1_GROQ,
    TIER1_OPENROUTER,
    TIER1_PROVIDERS,
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


def _make_mock_client(*responses):
    client = AsyncMock()
    client.is_closed = False
    client.post = AsyncMock(side_effect=list(responses))
    return client


class TestProviderChainOrder:
    def test_tier1_providers_count(self):
        assert len(TIER1_PROVIDERS) == 3

    def test_tier1_order_groq_cerebras_openrouter(self):
        assert TIER1_PROVIDERS[0].name == "groq-t1"
        assert TIER1_PROVIDERS[1].name == "cerebras"
        assert TIER1_PROVIDERS[2].name == "openrouter"

    def test_tier1_groq_is_first(self):
        assert TIER1_PROVIDERS[0] is TIER1_GROQ

    def test_tier1_cerebras_is_second(self):
        assert TIER1_PROVIDERS[1] is TIER1_CEREBRAS

    def test_tier1_openrouter_is_third(self):
        assert TIER1_PROVIDERS[2] is TIER1_OPENROUTER

    def test_all_tier1_configs_compatible(self):
        for p in TIER1_PROVIDERS:
            assert p.is_openai_compatible is True
            assert p.tier == 1


class TestFallbackChain:
    @pytest.mark.asyncio
    async def test_groq_succeeds_first(self, router):
        with patch.dict(os.environ, {"GROQ_API_KEY": "k1", "CEREBRAS_API_KEY": "k2", "OPENROUTER_API_KEY": "k3"}):
            router._client = _make_mock_client(
                _mock_response('{"impact": "HIGH", "dir": 1}'),
            )
            response, latency, provider = await router._call_llm_chain(
                TIER1_PROVIDERS, "test prompt"
            )
            assert response == '{"impact": "HIGH", "dir": 1}'
            assert provider.name == "groq-t1"
            assert router._client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_groq_empty_falls_to_cerebras(self, router):
        with patch.dict(os.environ, {"GROQ_API_KEY": "k1", "CEREBRAS_API_KEY": "k2", "OPENROUTER_API_KEY": "k3"}):
            router._client = _make_mock_client(
                _empty_response(),
                _mock_response('{"impact": "LOW", "dir": 0}'),
            )
            response, latency, provider = await router._call_llm_chain(
                TIER1_PROVIDERS, "test prompt"
            )
            assert response == '{"impact": "LOW", "dir": 0}'
            assert provider.name == "cerebras"
            assert router._client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_groq_cerebras_empty_falls_to_openrouter(self, router):
        with patch.dict(os.environ, {"GROQ_API_KEY": "k1", "CEREBRAS_API_KEY": "k2", "OPENROUTER_API_KEY": "k3"}):
            router._client = _make_mock_client(
                _empty_response(),
                _empty_response(),
                _mock_response('{"impact": "HIGH", "dir": -1}'),
            )
            response, latency, provider = await router._call_llm_chain(
                TIER1_PROVIDERS, "test prompt"
            )
            assert response == '{"impact": "HIGH", "dir": -1}'
            assert provider.name == "openrouter"
            assert router._client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_all_three_fail_returns_empty(self, router):
        with patch.dict(os.environ, {"GROQ_API_KEY": "k1", "CEREBRAS_API_KEY": "k2", "OPENROUTER_API_KEY": "k3"}):
            router._client = _make_mock_client(
                _empty_response(),
                _empty_response(),
                _empty_response(),
            )
            response, latency, provider = await router._call_llm_chain(
                TIER1_PROVIDERS, "test prompt"
            )
            assert response == ""
            assert provider is None
            assert router._client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_groq_429_falls_to_cerebras_then_openrouter(self, router):
        with patch.dict(os.environ, {"GROQ_API_KEY": "k1", "CEREBRAS_API_KEY": "k2", "OPENROUTER_API_KEY": "k3"}):
            resp_429 = MagicMock()
            resp_429.status_code = 429
            resp_429.json.return_value = {"error": "rate limited"}
            router._client = _make_mock_client(
                resp_429,
                resp_429,
                _mock_response('{"impact": "LOW", "dir": 0}'),
            )
            response, latency, provider = await router._call_llm_chain(
                TIER1_PROVIDERS, "test prompt"
            )
            assert response == '{"impact": "LOW", "dir": 0}'
            assert provider.name == "openrouter"
            assert router._client.post.call_count == 3


class TestRouteE2E:
    @pytest.mark.asyncio
    async def test_all_t1_fail_returns_low(self, router):
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
    async def test_openrouter_high_impact_triggers_tier2(self, router):
        with patch.dict(os.environ, {"GROQ_API_KEY": "k1", "CEREBRAS_API_KEY": "k2", "OPENROUTER_API_KEY": "k3"}):
            tier1_data = json.dumps({"impact": "HIGH", "dir": 1})
            tier2_data = json.dumps(
                {"confirmed": True, "direction": 1, "confidence": 0.85, "reasoning": "escalation"}
            )
            router._client = _make_mock_client(
                _empty_response(),
                _empty_response(),
                _mock_response(tier1_data),
                _mock_response(tier2_data),
            )
            result = await router.route("Crisis escalation")
            assert result.impact == ImpactLevel.HIGH
            assert result.direction == 1
            assert result.tier_used == 2
            assert result.confidence == 0.85
            assert router._client.post.call_count == 4
