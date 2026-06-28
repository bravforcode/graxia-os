"""
MacroRegime Cache — Shared memory for Dual-Speed Brain architecture.

HOT PATH reads: O(1) atomic load (no lock in steady state)
WARM PATH writes: Async LLM results update this cache
Thread-safe via threading.Lock
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class RegimeBias(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    PANIC = "PANIC"


@dataclass(frozen=True)
class MacroRegime:
    """Immutable macro regime snapshot. Read by hot path."""

    bias: RegimeBias = RegimeBias.NEUTRAL
    confidence: float = 0.5
    position_multiplier: float = 1.0
    regime_label: str = "NORMAL"
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: str = "default"
    headline: str = ""


class MacroRegimeCache:
    """Thread-safe singleton cache for MacroRegime."""

    _instance: MacroRegimeCache | None = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> MacroRegimeCache:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._regime = MacroRegime()
        return cls._instance

    def get(self) -> MacroRegime:
        with self._lock:
            return self._regime

    def update(self, regime: MacroRegime) -> None:
        with self._lock:
            self._regime = regime

    def update_from_sentiment(
        self,
        bias: RegimeBias,
        confidence: float,
        position_multiplier: float,
        regime_label: str,
        source: str = "sentiment_agent",
        headline: str = "",
    ) -> MacroRegime:
        regime = MacroRegime(
            bias=bias,
            confidence=confidence,
            position_multiplier=position_multiplier,
            regime_label=regime_label,
            source=source,
            headline=headline,
        )
        with self._lock:
            self._regime = regime
        return regime

    def reset(self) -> None:
        with self._lock:
            self._regime = MacroRegime()


_cache = MacroRegimeCache


def get_macro_regime() -> MacroRegime:
    return _cache().get()


def get_position_multiplier() -> float:
    return _cache().get().position_multiplier
