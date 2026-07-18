"""
MacroRegime Cache — Shared memory for Dual-Speed Brain architecture.

HOT PATH reads: O(1) atomic load (no lock in steady state)
WARM PATH writes: Async LLM results update this cache
Thread-safe via threading.Lock
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path


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

    def to_dict(self) -> dict:
        d = asdict(self)
        d["bias"] = self.bias.value
        d["updated_at"] = self.updated_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> MacroRegime:
        data = dict(data)
        data["bias"] = RegimeBias(data["bias"])
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return cls(**data)


class MacroRegimeCache:
    """Thread-safe singleton cache for MacroRegime.

    Persists to disk via JSON so regime survives across process restarts.
    Pipeline writes → disk → trading process reads on startup.
    """

    _instance: MacroRegimeCache | None = None
    _lock: threading.Lock = threading.Lock()
    _STATE_PATH: Path = Path(__file__).parent.parent.parent / "data" / "macro_regime_state.json"

    def __new__(cls) -> MacroRegimeCache:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._regime = MacroRegime()
                    # Load persisted state on first access
                    cls._instance._load_state()
        return cls._instance

    def get(self) -> MacroRegime:
        with self._lock:
            return self._regime

    def update(self, regime: MacroRegime) -> None:
        with self._lock:
            self._regime = regime
        self._save_state()

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
        self._save_state()
        return regime

    def reset(self) -> None:
        with self._lock:
            self._regime = MacroRegime()
        self._save_state()

    def _save_state(self) -> None:
        try:
            self._STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                data = self._regime.to_dict()
            self._STATE_PATH.write_text(json.dumps(data, indent=2))
        except Exception:
            pass  # Best-effort persistence

    def _load_state(self) -> None:
        if not self._STATE_PATH.exists():
            return
        try:
            regime = MacroRegime.from_dict(json.loads(self._STATE_PATH.read_text()))
            with self._lock:
                self._regime = regime
        except Exception:
            pass  # Corrupted state — start fresh


_cache = MacroRegimeCache


def get_macro_regime() -> MacroRegime:
    return _cache().get()


def get_position_multiplier() -> float:
    return _cache().get().position_multiplier
