"""Persistent kill switch. Blocks all new orders when active."""

import json
from pathlib import Path
from datetime import datetime, timezone


class KillSwitch:
    """Persistent kill switch. Blocks all new orders when active."""

    def __init__(self, state_file: str = "data/kill_switch_state.json"):
        self._state_file = Path(state_file)
        self._state = self._load()

    def is_active(self) -> bool:
        """Check if kill switch is active."""
        return self._state.get("active", False)

    def activate(self, reason: str, source: str = "manual") -> None:
        """Activate kill switch. Records who/what activated it."""
        self._state = {
            "active": True,
            "activated_at_utc": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "source": source,
        }
        self._save()

    def deactivate(self, reason: str, authorized_by: str) -> None:
        """Deactivate kill switch. Requires authorization."""
        self._state = {
            "active": False,
            "deactivated_at_utc": datetime.now(timezone.utc).isoformat(),
            "deactivation_reason": reason,
            "authorized_by": authorized_by,
        }
        self._save()

    def _load(self) -> dict:
        if self._state_file.exists():
            return json.loads(self._state_file.read_text())
        return {"active": False}

    def _save(self):
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(self._state, indent=2))
