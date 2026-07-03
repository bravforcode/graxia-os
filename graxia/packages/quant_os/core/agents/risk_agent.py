"""
RiskAgent — Logs regime-based position sizing on news analysis.

Subscribes to NewsAnalyzedEvent via EventBus, reads MacroRegimeCache,
and logs regime, bias, confidence, position_multiplier.

Usage:
    bus = EventBus()
    agent = RiskAgent(name="risk_agent")
    bus.subscribe("news.analyzed", agent.observe)
"""

from __future__ import annotations

import structlog

from ..canonical.macro_regime import MacroRegimeCache, get_position_multiplier
from ..events import Event, NewsAnalyzedEvent
from .base import Agent

logger = structlog.get_logger(__name__)


class RiskAgent(Agent):
    """
    Observes NewsAnalyzedEvent, reads MacroRegimeCache,
    and logs regime-based position sizing info.
    """

    def __init__(self, name: str = "risk_agent") -> None:
        super().__init__(name)
        self._cache = MacroRegimeCache()

    def observe(self, event: Event) -> None:
        if not isinstance(event, NewsAnalyzedEvent):
            return

        cache_regime = self._cache.get()
        pos_mult = get_position_multiplier()

        logger.info(
            "risk_agent.news_analyzed",
            headline=event.headline[:80],
            regime=event.regime_label,
            bias=event.bias,
            confidence=event.confidence,
            event_position_multiplier=event.position_multiplier,
            cache_regime=cache_regime.regime_label,
            cache_position_multiplier=pos_mult,
            source_provider=event.source_provider,
        )

        self._observations.append(event)

    def act(self) -> Event | None:
        return None
