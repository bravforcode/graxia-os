"""
LLM Cascade Router — Tiered waterfall for news → sentiment.

Tier 1 (Cerebras ~200ms): Fast trigger
Tier 2 (Groq ~700ms): Validator for HIGH impact only
Tier 3 (Gemini, cron 4h): Deep strategist

RULE: No HTTP calls in hot path. Results go to MacroRegimeCache.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from enum import Enum

import httpx
import structlog

logger = structlog.get_logger(__name__)


class ImpactLevel(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"


@dataclass
class CascadeResult:
    headline: str
    impact: ImpactLevel
    direction: int
    tier_used: int
    confidence: float = 0.0
    reasoning: str = ""
    latency_ms: float = 0.0
    raw_response: str = ""


@dataclass
class ProviderConfig:
    name: str
    tier: int
    api_key_env: str
    base_url: str
    model: str
    max_tokens: int = 100
    temperature: float = 0.1
    timeout_seconds: float = 5.0


TIER1_CONFIG = ProviderConfig(
    name="cerebras",
    tier=1,
    api_key_env="CEREBRAS_API_KEY",
    base_url="https://api.cerebras.ai/v1/chat/completions",
    model="gpt-oss-120b",
    max_tokens=100,
    timeout_seconds=3.0,
)

TIER2_CONFIG = ProviderConfig(
    name="groq",
    tier=2,
    api_key_env="GROQ_API_KEY",
    base_url="https://api.groq.com/openai/v1/chat/completions",
    model="llama-3.3-70b-versatile",
    max_tokens=200,
    timeout_seconds=5.0,
)

TIER3_CONFIG = ProviderConfig(
    name="gemini",
    tier=3,
    api_key_env="GOOGLE_AI_KEY",
    base_url="https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    model="gemini-2.5-flash",
    max_tokens=500,
    timeout_seconds=30.0,
)


TIER1_PROMPT = """Analyze this financial news headline. Return ONLY a JSON object:
{{"impact": "HIGH" or "LOW", "dir": -1 (bearish), 0 (neutral), or 1 (bullish)}}

Rules:
- HIGH: Fed rate change, war, NFP, FOMC, major bank failure, geopolitical crisis
- LOW: routine earnings, analyst upgrades/downgrades, minor data

Headline: {headline}

Return ONLY valid JSON."""

TIER2_PROMPT = """Validate this HIGH-impact financial news headline for gold (XAUUSD) trading.

Return ONLY a JSON object:
{{"confirmed": true or false, "direction": -1 or 0 or 1, "confidence": 0.0-1.0, "reasoning": "brief"}}

Headline: {headline}

Return ONLY valid JSON."""


class CascadeRouter:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._last_tier3_run: float = 0.0
        self._tier3_interval: float = 4 * 3600

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient()
        return self._client

    async def _call_llm(self, config: ProviderConfig, prompt: str) -> tuple[str, float]:
        api_key = os.getenv(config.api_key_env, "")
        if not api_key:
            logger.warning("llm_no_api_key", provider=config.name)
            return "", 0.0
        client = await self._get_client()
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": config.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
        }
        start = time.monotonic()
        try:
            resp = await client.post(config.base_url, json=payload, headers=headers, timeout=config.timeout_seconds)
            latency_ms = (time.monotonic() - start) * 1000
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return content.strip(), latency_ms
            logger.warning("llm_error", provider=config.name, status=resp.status_code)
            return "", latency_ms
        except Exception as e:
            latency_ms = (time.monotonic() - start) * 1000
            logger.warning("llm_exception", provider=config.name, error=str(e))
            return "", latency_ms

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{[^}]+\}", text, re.DOTALL)
            if match:
                return json.loads(match.group())
            return {}

    async def route(self, headline: str) -> CascadeResult:
        start = time.monotonic()
        tier1_prompt = TIER1_PROMPT.format(headline=headline)
        tier1_response, _ = await self._call_llm(TIER1_CONFIG, tier1_prompt)
        if not tier1_response:
            return CascadeResult(
                headline=headline,
                impact=ImpactLevel.LOW,
                direction=0,
                tier_used=1,
                latency_ms=(time.monotonic() - start) * 1000,
                reasoning="Tier 1 failed",
            )
        tier1_data = self._parse_json(tier1_response)
        impact = ImpactLevel(tier1_data.get("impact", "LOW"))
        direction = tier1_data.get("dir", 0)
        if impact == ImpactLevel.LOW:
            return CascadeResult(
                headline=headline,
                impact=impact,
                direction=direction,
                tier_used=1,
                latency_ms=(time.monotonic() - start) * 1000,
                raw_response=tier1_response,
            )
        tier2_prompt = TIER2_PROMPT.format(headline=headline)
        tier2_response, _ = await self._call_llm(TIER2_CONFIG, tier2_prompt)
        total = (time.monotonic() - start) * 1000
        if not tier2_response:
            return CascadeResult(
                headline=headline,
                impact=impact,
                direction=direction,
                tier_used=1,
                confidence=0.5,
                reasoning="Tier 2 unavailable",
                latency_ms=total,
            )
        tier2_data = self._parse_json(tier2_response)
        if not tier2_data.get("confirmed", True):
            return CascadeResult(
                headline=headline,
                impact=ImpactLevel.LOW,
                direction=0,
                tier_used=2,
                confidence=tier2_data.get("confidence", 0.5),
                reasoning=tier2_data.get("reasoning", "rejected"),
                latency_ms=total,
                raw_response=tier2_response,
            )
        return CascadeResult(
            headline=headline,
            impact=impact,
            direction=tier2_data.get("direction", direction),
            tier_used=2,
            confidence=tier2_data.get("confidence", 0.7),
            reasoning=tier2_data.get("reasoning", ""),
            latency_ms=total,
            raw_response=tier2_response,
        )

    async def should_run_tier3(self) -> bool:
        return (time.time() - self._last_tier3_run) >= self._tier3_interval

    async def run_tier3(self, research_report_path: str) -> dict:
        self._last_tier3_run = time.time()
        report = ""
        if os.path.exists(research_report_path):
            with open(research_report_path) as f:
                report = f.read()[:3000]
        prompt = f"""You are a macro strategist for gold (XAUUSD).

Return ONLY JSON:
{{"bias": "BULLISH|BEARISH|NEUTRAL|PANIC", "confidence": 0.0-1.0, "position_multiplier": 0.0-1.0, "regime_label": "NORMAL|HIGH_UNCERTAINTY|CRISIS", "reasoning": "brief"}}

Research Report:
{report}

Return ONLY valid JSON."""
        for config in [TIER3_CONFIG]:
            response, latency = await self._call_llm(config, prompt)
            if response:
                data = self._parse_json(response)
                data["latency_ms"] = latency
                data["provider"] = config.name
                return data
        return {"error": "All Tier 3 providers failed"}

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


_router: CascadeRouter | None = None


def get_router() -> CascadeRouter:
    global _router
    if _router is None:
        _router = CascadeRouter()
    return _router
