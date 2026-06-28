"""
Sentiment Agent — Headline → CascadeRouter → MacroRegimeCache.

Dual-Speed Brain architecture:
  HOT PATH:  Read MacroRegimeCache (O(1), no lock in steady state)
  WARM PATH: This agent calls CascadeRouter → writes to MacroRegimeCache

Tier 1 (Cerebras ~200ms): Impact classification
Tier 2 (Groq ~700ms): HIGH-impact validation
Tier 3 (Gemini, cron 4h): Deep macro strategist

RULE: No raw dicts via EventBus. Output is MacroRegimePayload (Pydantic v2).

Usage:
    agent = SentimentAgent()
    bus.subscribe("news.high_impact", agent.observe)
    # ... later ...
    payload = await agent.act()  # writes to cache, returns payload
"""

from __future__ import annotations

import asyncio

import structlog

from ..canonical.macro_regime import (
    MacroRegimeCache,
    RegimeBias,
)
from ..canonical.payloads import MacroRegimePayload
from ..events import Event
from .base import Agent
from .llm_router import CascadeRouter, ImpactLevel, get_router

logger = structlog.get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

_BIAS_MAP = {
    1: RegimeBias.BULLISH,
    -1: RegimeBias.BEARISH,
    0: RegimeBias.NEUTRAL,
}

_REGIME_MAP = {
    "HIGH": "HIGH_UNCERTAINTY",
    "LOW": "NORMAL",
}


def _cascade_to_regime(result, headline: str) -> MacroRegimePayload:
    """Map CascadeResult → MacroRegimePayload."""
    impact_label = _REGIME_MAP.get(result.impact.value, "NORMAL")
    bias = _BIAS_MAP.get(result.direction, RegimeBias.NEUTRAL)

    # CRISIS heuristic: if Tier 2 gives confidence >= 0.9 AND bearish
    if result.direction == -1 and result.confidence >= 0.9:
        impact_label = "CRISIS"
        bias = RegimeBias.PANIC

    # Position multiplier from confidence
    pos_mult = result.confidence if result.impact == ImpactLevel.HIGH else 0.75
    if impact_label == "CRISIS":
        pos_mult = 0.0

    return MacroRegimePayload(
        bias=bias,
        confidence=result.confidence,
        position_multiplier=pos_mult,
        regime_label=impact_label,
        source_provider=f"cascade_t{result.tier_used}",
        headline=result.headline[:200],
        reasoning=result.reasoning,
    )


# ═══════════════════════════════════════════════════════════════════
# Sentiment Agent
# ═══════════════════════════════════════════════════════════════════


class SentimentAgent(Agent):
    """
    Multi-tier sentiment analyzer for news events.

    Lifecycle:
        1. observe(news_event) — stores headline
        2. act() — CascadeRouter → MacroRegimeCache → MacroRegimePayload
        3. reset() — clears pending headlines
    """

    MAX_CONCURRENT = 3  # parallel headline processing

    def __init__(self, name: str = "sentiment_agent") -> None:
        super().__init__(name)
        self._pending_headlines: list[dict] = []
        self._router: CascadeRouter | None = None
        self._cache = MacroRegimeCache()

    @property
    def router(self) -> CascadeRouter:
        if self._router is None:
            self._router = get_router()
        return self._router

    async def shutdown(self) -> None:
        if self._router:
            await self._router.close()
        logger.info("sentiment_agent.shutdown_complete")

    def observe(self, event: Event) -> None:
        if not isinstance(event, Event):
            return
        headline = getattr(event, "headline", "")
        source = getattr(event, "source", "unknown")
        if headline:
            self._pending_headlines.append(
                {
                    "headline": headline,
                    "source": source,
                    "timestamp": event.timestamp.isoformat(),
                }
            )

    async def act(self) -> MacroRegimePayload | None:
        if not self._pending_headlines:
            return None

        headlines = list(self._pending_headlines)
        self._pending_headlines.clear()

        # Process headlines through CascadeRouter
        tasks = [self._analyze(h["headline"]) for h in headlines]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        payloads = [r for r in results if isinstance(r, MacroRegimePayload)]
        if not payloads:
            return None

        # Aggregate: most conservative wins
        aggregated = self._aggregate(payloads)

        # Write to MacroRegimeCache (WARM PATH)
        self._cache.update_from_sentiment(
            bias=aggregated.bias,
            confidence=aggregated.confidence,
            position_multiplier=aggregated.position_multiplier,
            regime_label=aggregated.regime_label,
            source=aggregated.source_provider,
            headline=aggregated.headline,
        )

        logger.info(
            "sentiment_agent.result",
            bias=aggregated.bias.value,
            confidence=aggregated.confidence,
            regime=aggregated.regime_label,
            pos_mult=aggregated.position_multiplier,
            provider=aggregated.source_provider,
        )
        return aggregated

    async def _analyze(self, headline: str) -> MacroRegimePayload | None:
        try:
            result = await self.router.route(headline)
            return _cascade_to_regime(result, headline)
        except Exception as exc:
            logger.warning("sentiment_agent.route_error", error=str(exc))
            return None

    def _aggregate(self, payloads: list[MacroRegimePayload]) -> MacroRegimePayload:
        """Most conservative result wins across all headlines."""
        # Most conservative regime
        regime_order = {"CRISIS": 3, "HIGH_UNCERTAINTY": 2, "NORMAL": 1}
        worst_regime = max(payloads, key=lambda p: regime_order.get(p.regime_label, 0))

        # Min position multiplier
        min_pos = min(p.position_multiplier for p in payloads)

        # Average confidence
        avg_conf = sum(p.confidence for p in payloads) / len(payloads)

        return MacroRegimePayload(
            bias=worst_regime.bias,
            confidence=avg_conf,
            position_multiplier=min_pos,
            regime_label=worst_regime.regime_label,
            source_provider=worst_regime.source_provider,
            headline=worst_regime.headline,
            reasoning=f"Aggregated from {len(payloads)} headlines",
        )

    def reset(self) -> None:
        super().reset()
        self._pending_headlines.clear()
