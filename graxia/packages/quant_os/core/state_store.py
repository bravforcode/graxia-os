"""Atomic state persistence for the trading system.

Provides a serialisable ``SystemState`` dataclass and atomic save/load
operations backed by a JSON file on disk.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class SystemStateEnum(str, Enum):
    """High-level system lifecycle states."""
    INIT = "INIT"
    RUNNING = "RUNNING"
    HALTED = "HALTED"
    RECOVERY = "RECOVERY"
    SHUTDOWN = "SHUTDOWN"


@dataclass
class SystemState:
    """Complete system state snapshot for persistence and recovery.

    Every field is JSON-serialisable so the entire object can round-trip
    through :func:`save` / :func:`load` without custom codecs.
    """

    # --- lifecycle ---
    system_state: str = SystemStateEnum.INIT.value
    last_heartbeat: str = ""           # ISO-8601 UTC
    kill_switch_active: bool = False
    environment: str = "development"   # development | staging | production

    # --- per-asset-class state ---
    asset_states: dict[str, str] = field(default_factory=dict)
    # e.g. {"XAUUSD": "RUNNING", "EURUSD": "HALTED"}

    # --- circuit breakers ---
    circuit_breakers: dict[str, bool] = field(default_factory=dict)
    # e.g. {"daily_loss": false, "drawdown": true}

    # --- positions & orders ---
    positions: list[dict[str, Any]] = field(default_factory=list)
    pending_orders: list[dict[str, Any]] = field(default_factory=list)

    # --- PnL tracking ---
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    peak_equity: float = 0.0
    current_drawdown_pct: float = 0.0

    # --- reconciliation ---
    last_reconciled: str = ""          # ISO-8601 UTC
    reconcile_ok: bool = True

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Return a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SystemState:
        """Construct from a dict, ignoring unknown keys."""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})

    # ------------------------------------------------------------------
    # Convenience classmethods
    # ------------------------------------------------------------------

    @classmethod
    def default(cls, environment: str = "development") -> SystemState:
        """Return a fresh state with sensible defaults."""
        now = dt.datetime.now(dt.UTC).isoformat()
        return cls(
            system_state=SystemStateEnum.INIT.value,
            last_heartbeat=now,
            kill_switch_active=False,
            environment=environment,
            asset_states={},
            circuit_breakers={},
            positions=[],
            pending_orders=[],
            daily_pnl=0.0,
            weekly_pnl=0.0,
            peak_equity=0.0,
            current_drawdown_pct=0.0,
            last_reconciled="",
            reconcile_ok=True,
        )


# ======================================================================
# Atomic file I/O
# ======================================================================

def save(state: SystemState, path: str | Path) -> None:
    """Atomically write *state* to *path*.

    Writes to a temporary file in the same directory, then performs an
    ``os.replace`` so the target is never in a half-written state.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp", prefix=".state_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(state.to_json())
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, str(path))
    except BaseException:
        # Clean up temp file on any failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load(path: str | Path) -> SystemState:
    """Load a :class:`SystemState` from *path*.

    Returns ``SystemState.default()`` if the file does not exist or is
    corrupt, so callers never need to handle file-level errors.
    """
    path = Path(path)
    if not path.exists():
        return SystemState.default()

    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        return SystemState.from_dict(data)
    except (json.JSONDecodeError, OSError, TypeError):
        return SystemState.default()
