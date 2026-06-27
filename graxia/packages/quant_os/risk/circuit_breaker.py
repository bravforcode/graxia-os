"""
Circuit Breaker — per-asset-class persistent circuit breaker.

Tracks consecutive losses per class, trips when threshold exceeded,
auto-recovers after cooldown.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

ASSET_CLASSES = ("metals", "crypto", "forex", "indices")


@dataclass
class CircuitBreakerConfig:
    threshold: int = 3
    cooldown_minutes: int = 30


@dataclass
class _ClassState:
    consecutive_losses: int = 0
    open: bool = False
    reason: str = ""
    trip_count: int = 0


class CircuitBreaker:
    def __init__(
        self,
        state_file: str | None = None,
        configs: dict[str, CircuitBreakerConfig] | None = None,
        config: CircuitBreakerConfig | None = None,
    ):
        self._state_file = Path(state_file) if state_file else None
        self._configs = configs or {}
        self._default_config = config or CircuitBreakerConfig()
        self._classes: dict[str, _ClassState] = {c: _ClassState() for c in ASSET_CLASSES}
        if self._state_file and self._state_file.exists():
            self._load()

    def _cfg(self, cls: str) -> CircuitBreakerConfig:
        return self._configs.get(cls, self._default_config)

    def is_open(self, cls: str) -> bool:
        return self._classes.setdefault(cls, _ClassState()).open

    @property
    def is_blocked(self) -> bool:
        return any(s.open for s in self._classes.values())

    @property
    def is_triggered(self) -> bool:
        return self.is_blocked

    @property
    def reason(self) -> str:
        reasons = [f"{c}: {s.reason}" for c, s in self._classes.items() if s.open and s.reason]
        return "; ".join(reasons) if reasons else ""

    def trip(self, cls: str, reason: str = "manual") -> None:
        s = self._classes.setdefault(cls, _ClassState())
        cfg = self._cfg(cls)
        s.trip_count += 1
        if cfg.cooldown_minutes <= 0:
            s.open = False
            s.reason = ""
            s.consecutive_losses = 0
        else:
            s.open = True
            s.reason = reason
        self._save()

    def reset(self, cls: str) -> None:
        s = self._classes.setdefault(cls, _ClassState())
        s.open = False
        s.reason = ""
        s.consecutive_losses = 0
        self._save()

    def record_trade(self, cls: str, pnl: float) -> bool:
        s = self._classes.setdefault(cls, _ClassState())
        if pnl < 0:
            s.consecutive_losses += 1
            cfg = self._cfg(cls)
            if s.consecutive_losses >= cfg.threshold:
                s.open = True
                s.reason = f"{s.consecutive_losses} consecutive losses"
                s.trip_count += 1
                self._save()
                return True
        else:
            s.consecutive_losses = 0
        self._save()
        return False

    def get_status(self) -> dict:
        status = {}
        for cls in ASSET_CLASSES:
            s = self._classes.setdefault(cls, _ClassState())
            status[cls] = {
                "open": s.open,
                "consecutive_losses": s.consecutive_losses,
                "trip_count": s.trip_count,
                "reason": s.reason,
            }
        return status

    def _save(self) -> None:
        if not self._state_file:
            return
        data = {}
        for cls, s in self._classes.items():
            data[cls] = {"cl": s.consecutive_losses, "o": s.open, "r": s.reason, "tc": s.trip_count}
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(data))

    def _load(self) -> None:
        try:
            data = json.loads(self._state_file.read_text())
            for cls, d in data.items():
                s = self._classes.setdefault(cls, _ClassState())
                s.consecutive_losses = d.get("cl", 0)
                s.open = d.get("o", False)
                s.reason = d.get("r", "")
                s.trip_count = d.get("tc", 0)
        except (json.JSONDecodeError, ValueError):
            pass
