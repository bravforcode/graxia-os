from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


_state: dict[str, Any] = {
    "is_ready": False,
    "mode": "booting",
    "issues": [],
    "updated_at": None,
}


def set_runtime_state(is_ready: bool, mode: str, issues: list[str] | None = None) -> None:
    _state["is_ready"] = is_ready
    _state["mode"] = mode
    _state["issues"] = list(issues or [])
    _state["updated_at"] = datetime.now(timezone.utc)


def get_runtime_state() -> dict[str, Any]:
    updated_at = _state["updated_at"]
    return {
        "is_ready": _state["is_ready"],
        "mode": _state["mode"],
        "issues": list(_state["issues"]),
        "updated_at": updated_at.isoformat() if updated_at else None,
    }
