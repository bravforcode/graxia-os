"""Money kill switch (P0 T6, IMF best practice).

JSON-file backed (quant_os pattern). Fail-closed: corrupt/unreadable state
file blocks ALL money operations. Missing file = normal operation.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class MoneyKillSwitchError(RuntimeError):
    """Raised when a money operation is attempted while the kill switch is active."""


class MoneyKillSwitch:
    def __init__(self, path: Optional[str] = None) -> None:
        self.path = Path(
            path or os.getenv("REVENUE_OS_KILL_SWITCH_FILE", "data/revenue_os_kill_switch.json")
        )

    def is_triggered(self) -> bool:
        if not self.path.exists():
            return False
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
            return bool(state.get("triggered", False))
        except (json.JSONDecodeError, OSError):
            return True  # fail-closed

    def get_status(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"triggered": False, "reason": None, "triggered_at": None}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"triggered": True, "reason": "corrupt state file (fail-closed)", "triggered_at": None}

    def trigger(self, reason: str) -> dict[str, Any]:
        state = {
            "triggered": True,
            "reason": reason,
            "triggered_at": datetime.now(timezone.utc).isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return state

    def reset(self, reason: str) -> dict[str, Any]:
        state = {
            "triggered": False,
            "reason": reason,
            "triggered_at": datetime.now(timezone.utc).isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return state


def ensure_money_ops_allowed(switch: Optional[MoneyKillSwitch] = None) -> None:
    """Fail-closed guard for money operations. Raises MoneyKillSwitchError when active."""
    if (switch or MoneyKillSwitch()).is_triggered():
        raise MoneyKillSwitchError("Money operations disabled (kill switch active)")