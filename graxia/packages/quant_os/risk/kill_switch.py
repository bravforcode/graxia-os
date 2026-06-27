"""
Kill Switch — Persistent kill switch with Telegram command interface.
"""

import json
import logging
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ASSET_CLASS_COMMANDS: dict[str, list[str]] = {
    "metals": ["XAUUSD", "XAGUSD", "XAUEUR", "XAUJPY"],
    "crypto": ["BTCUSD", "ETHUSD", "SOLUSD", "ADAUSD", "XRPUSD"],
    "forex": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY"],
    "indices": ["US30", "NAS100", "SPX500", "GER40", "UK100", "JP225"],
}


class KillSwitchState(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    INACTIVE = "INACTIVE"


class KillSwitch:
    def __init__(self, state_file: str = "data/kill_switch_state.json"):
        self._state_file = Path(state_file)
        self._allowed_users: set[int] = self._load_allowed_users()
        self._state: dict[str, Any] = self._load()
        self._last_user_id: int | None = None

    def is_active(self) -> bool:
        return self._get_state_enum() == KillSwitchState.ACTIVE

    def is_paused(self) -> bool:
        return self._get_state_enum() == KillSwitchState.PAUSED

    def is_class_killed(self, asset_class: str) -> bool:
        if self._get_state_enum() == KillSwitchState.ACTIVE:
            return True
        return asset_class.lower() in self._state.get("killed_classes", [])

    @property
    def is_triggered(self) -> bool:
        return self.is_active() or self.is_paused()

    @property
    def trigger_type(self) -> str:
        return self._state.get("state", KillSwitchState.INACTIVE.value)

    def get_status(self) -> dict[str, Any]:
        return {
            "state": self._state.get("state", KillSwitchState.INACTIVE.value),
            "killed_classes": self._state.get("killed_classes", []),
            "reason": self._state.get("reason", ""),
            "activated_at_utc": self._state.get("activated_at_utc"),
            "authorized_by": self._state.get("authorized_by"),
        }

    def handle_command(self, command: str, user_id: int) -> str:
        if not self._is_authorized(user_id):
            return f"UNAUTHORIZED: user {user_id} not in TELEGRAM_ALLOWED_USERS"
        cmd = command.strip().lower().split()[0]
        self._last_user_id = user_id
        handlers: dict[str, Any] = {
            "/kill_all": self._cmd_kill_all,
            "/kill_metals": lambda: self._cmd_kill_class("metals"),
            "/kill_crypto": lambda: self._cmd_kill_class("crypto"),
            "/kill_forex": lambda: self._cmd_kill_class("forex"),
            "/kill_indices": lambda: self._cmd_kill_class("indices"),
            "/pause": self._cmd_pause,
            "/resume": self._cmd_resume,
        }
        handler = handlers.get(cmd)
        if handler is None:
            return f"UNKNOWN COMMAND: {cmd}"
        return handler()

    def activate(self, reason: str, source: str = "manual") -> None:
        self._set_state(KillSwitchState.ACTIVE, reason=reason, authorized_by=source)

    def deactivate(self, reason: str, authorized_by: str = "system") -> None:
        self._set_state(KillSwitchState.INACTIVE, reason=reason, authorized_by=authorized_by)
        self._state["killed_classes"] = []
        self._save()

    def _cmd_kill_all(self) -> str:
        self._set_state(KillSwitchState.ACTIVE, reason="Telegram /kill_all", authorized_by=f"telegram:{self._last_user_id}")
        return "KILL SWITCH ACTIVATED — all trading halted."

    def _cmd_kill_class(self, asset_class: str) -> str:
        killed = self._state.get("killed_classes", [])
        if asset_class not in killed:
            killed.append(asset_class)
            self._state["killed_classes"] = killed
        self._append_history(f"/kill_{asset_class}", self._last_user_id)
        self._save()
        return f"KILLED: {asset_class} trading halted. Active kills: {killed}"

    def _cmd_pause(self) -> str:
        self._set_state(KillSwitchState.PAUSED, reason="Telegram /pause", authorized_by=f"telegram:{self._last_user_id}")
        return "PAUSED — no new entries. Closes still allowed."

    def _cmd_resume(self) -> str:
        self._set_state(KillSwitchState.INACTIVE, reason="Telegram /resume", authorized_by=f"telegram:{self._last_user_id}")
        self._state["killed_classes"] = []
        self._save()
        return "RESUMED — normal operation."

    def _load_allowed_users(self) -> set[int]:
        raw = os.getenv("TELEGRAM_ALLOWED_USERS", "")
        if not raw:
            return set()
        return {int(uid.strip()) for uid in raw.split(",") if uid.strip().isdigit()}

    def _is_authorized(self, user_id: int) -> bool:
        if not self._allowed_users:
            return False
        return user_id in self._allowed_users

    def _get_state_enum(self) -> KillSwitchState:
        try:
            return KillSwitchState(self._state.get("state", "INACTIVE"))
        except ValueError:
            return KillSwitchState.INACTIVE

    def _set_state(self, state: KillSwitchState, reason: str, authorized_by: str) -> None:
        self._state["state"] = state.value
        self._state["reason"] = reason
        self._state["authorized_by"] = authorized_by
        self._state["activated_at_utc"] = datetime.now(timezone.utc).isoformat()
        self._append_history(f"state={state.value}", authorized_by)
        self._save()

    def _append_history(self, action: str, user: Any) -> None:
        history: list[dict[str, str]] = self._state.get("history", [])
        history.append({"action": action, "user": str(user), "timestamp": datetime.now(timezone.utc).isoformat()})
        self._state["history"] = history[-100:]
        self._last_user_id = user

    def _load(self) -> dict[str, Any]:
        if self._state_file.exists():
            try:
                return json.loads(self._state_file.read_text())
            except (json.JSONDecodeError, ValueError):
                pass
        return {"state": KillSwitchState.INACTIVE.value, "killed_classes": [], "reason": "", "activated_at_utc": None, "authorized_by": "", "history": []}

    def _save(self) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(self._state, indent=2))
