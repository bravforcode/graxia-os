"""
Circuit Breaker — per-asset-class persistent circuit breaker.

Tracks consecutive losses per class, trips when threshold exceeded,
auto-recovers after cooldown.  Optionally activates a KillSwitch on trip.
"""

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    opened_at: float = 0.0  # timestamp when opened


class CircuitBreaker:
    def __init__(
        self,
        state_file: str | None = None,
        configs: dict[str, CircuitBreakerConfig] | None = None,
        config: CircuitBreakerConfig | None = None,
        kill_switch: Any | None = None,
    ):
        self._state_file = Path(state_file) if state_file else None
        self._configs = configs or {}
        self._default_config = config or CircuitBreakerConfig()
        self._classes: dict[str, _ClassState] = {c: _ClassState() for c in ASSET_CLASSES}
        self._kill_switch = kill_switch
        if self._state_file and self._state_file.exists():
            self._load()

    def _cfg(self, cls: str) -> CircuitBreakerConfig:
        return self._configs.get(cls, self._default_config)

    def is_open(self, cls: str) -> bool:
        import time

        s = self._classes.get(cls, _ClassState())
        if not s.opened_at:
            return s.open
        # Auto-recover after cooldown
        cfg = self._cfg(cls)
        elapsed = time.time() - s.opened_at
        if s.open and elapsed > cfg.cooldown_minutes * 60:
            s.open = False
            s.consecutive_losses = 0
            s.reason = ""
            self._save()
            return False
        return s.open

    @property
    def is_blocked(self) -> bool:
        """Check if ANY class is open — uses is_open() to respect cooldown."""
        return any(self.is_open(cls) for cls in self._classes)

    @property
    def is_triggered(self) -> bool:
        return self.is_blocked

    @property
    def reason(self) -> str:
        reasons = [f"{c}: {s.reason}" for c, s in self._classes.items() if s.open and s.reason]
        return "; ".join(reasons) if reasons else ""

    def trip(self, cls: str, reason: str = "manual") -> None:
        import time

        s = self._classes.setdefault(cls, _ClassState())
        cfg = self._cfg(cls)
        s.trip_count += 1
        if cfg.cooldown_minutes <= 0:
            s.open = False
            s.reason = ""
            s.consecutive_losses = 0
            s.opened_at = 0.0
        else:
            s.open = True
            s.reason = reason
            s.opened_at = time.time()
        self._save()

        # Activate kill switch if wired
        if self._kill_switch is not None:
            try:
                self._kill_switch.activate(
                    reason=f"Circuit breaker tripped for {cls}: {reason}",
                    source=f"circuit_breaker:{cls}",
                )
                logger.warning(
                    "circuit_breaker.trip: kill_switch activated for %s: %s",
                    cls,
                    reason,
                )
            except Exception as exc:
                logger.error("circuit_breaker.trip: failed to activate kill_switch: %s", exc)

    def reset(self, cls: str, authorized_by: str, reason: str) -> None:
        """Reset circuit breaker for a class. Requires authorization and reason for audit."""
        if not authorized_by or not reason:
            raise ValueError("reset() requires both authorized_by and reason parameters")
        s = self._classes.setdefault(cls, _ClassState())
        s.open = False
        s.reason = ""
        s.consecutive_losses = 0
        logger.info(
            "circuit_breaker.reset: class=%s authorized_by=%s reason=%s",
            cls,
            authorized_by,
            reason,
        )
        self._save()

    def record_trade(self, cls: str, pnl: float) -> bool:
        import time

        s = self._classes.setdefault(cls, _ClassState())
        if pnl < 0:
            s.consecutive_losses += 1
            cfg = self._cfg(cls)
            if s.consecutive_losses >= cfg.threshold:
                s.open = True
                s.reason = f"{s.consecutive_losses} consecutive losses"
                s.trip_count += 1
                s.opened_at = time.time()
                self._save()

                # Activate kill switch on trip — prevents hemorrhage across asset classes
                if self._kill_switch is not None:
                    try:
                        self._kill_switch.activate(
                            reason=f"Circuit breaker tripped for {cls}: {s.reason}",
                            source=f"circuit_breaker:{cls}",
                        )
                        logger.warning(
                            "circuit_breaker.record_trade: kill_switch activated for %s: %s",
                            cls,
                            s.reason,
                        )
                    except Exception as exc:
                        logger.error(
                            "circuit_breaker.record_trade: failed to activate kill_switch: %s",
                            exc,
                        )

                return True
        else:
            # Only reset on actual profit, not break-even
            if pnl > 0:
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
        """Save state atomically using temp file + rename."""
        if not self._state_file:
            return
        data = {}
        for cls, s in self._classes.items():
            data[cls] = {"cl": s.consecutive_losses, "o": s.open, "r": s.reason, "tc": s.trip_count}
        self._state_file.parent.mkdir(parents=True, exist_ok=True)

        # Write to temp file first
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._state_file.parent),
            prefix=".circuit_breaker_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f)
                f.flush()
                os.fsync(f.fileno())
            # Atomic rename
            os.replace(tmp_path, str(self._state_file))
        except Exception:
            # Clean up temp file on failure
            import contextlib

            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise

    def _load(self) -> None:
        import time

        try:
            text = self._state_file.read_text(encoding="utf-8")
            if not text.strip():
                logger.critical(
                    "circuit_breaker: state file is empty — fail-closed default (all tripped). " "file=%s",
                    self._state_file,
                )
                for cls in ASSET_CLASSES:
                    s = self._classes[cls]
                    s.open = True
                    s.reason = "State file empty — fail-closed default"
                    s.opened_at = time.time()
                return
            data = json.loads(text)
            for cls, d in data.items():
                s = self._classes.setdefault(cls, _ClassState())
                s.consecutive_losses = d.get("cl", 0)
                s.open = d.get("o", False)
                s.reason = d.get("r", "")
                s.trip_count = d.get("tc", 0)
        except (json.JSONDecodeError, ValueError) as exc:
            # Fail-closed: corrupted circuit breaker state → trip all classes
            logger.critical(
                "circuit_breaker: state file corrupted — fail-closed default (all tripped). " "file=%s error=%s",
                self._state_file,
                exc,
            )
            for cls in ASSET_CLASSES:
                s = self._classes[cls]
                s.open = True
                s.reason = "State file corrupted — fail-closed default"
                s.opened_at = time.time()
        except FileNotFoundError:
            pass
