"""Phase 10 — Emergency kill switch for micro-live canary."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class KillSwitchState:
    active: bool
    activated_at: str = ""
    reason: str = ""
    activated_by: str = "system"


class EmergencyKillSwitch:
    """Persistent kill switch that survives restarts."""

    def __init__(self, state_file: str = ""):
        self._state_file = Path(state_file) if state_file else None
        self._state = KillSwitchState(active=False)
        if self._state_file and self._state_file.exists():
            self._load()

    def _load(self) -> None:
        if self._state_file:
            data = json.loads(self._state_file.read_text())
            self._state = KillSwitchState(**data)

    def _save(self) -> None:
        if self._state_file:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(
                json.dumps(
                    {
                        "active": self._state.active,
                        "activated_at": self._state.activated_at,
                        "reason": self._state.reason,
                        "activated_by": self._state.activated_by,
                    },
                    indent=2,
                )
            )

    def activate(self, reason: str, activated_by: str = "manual") -> None:
        self._state = KillSwitchState(
            active=True,
            activated_at=datetime.now(UTC).isoformat(),
            reason=reason,
            activated_by=activated_by,
        )
        self._save()

    def deactivate(self) -> None:
        self._state = KillSwitchState(active=False)
        self._save()

    def is_active(self) -> bool:
        return self._state.active

    def get_state(self) -> KillSwitchState:
        return self._state
