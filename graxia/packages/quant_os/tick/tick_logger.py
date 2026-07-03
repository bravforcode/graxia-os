"""Phase BE-P2 — Structured tick logger."""

import json
from datetime import UTC, datetime
from pathlib import Path


class TickLogger:
    """Structured logging for tick events."""

    def __init__(self, log_dir: str = ""):
        self._log_dir = Path(log_dir) if log_dir else None
        self._entries: list[dict] = []

    def log_tick_received(self, symbol: str, bid: float, ask: float, source_time_ms: int) -> None:
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": "tick_received",
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
            "spread": ask - bid if ask > bid else 0,
            "source_time_ms": source_time_ms,
        }
        self._entries.append(entry)

    def log_quality_incident(self, incident_type: str, tick_id: int, detail: str) -> None:
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": "quality_incident",
            "incident_type": incident_type,
            "tick_id": tick_id,
            "detail": detail,
        }
        self._entries.append(entry)

    def log_gate_transition(self, from_state: str, to_state: str, reason: str) -> None:
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": "gate_transition",
            "from_state": from_state,
            "to_state": to_state,
            "reason": reason,
        }
        self._entries.append(entry)

    def get_entries(self) -> list[dict]:
        return self._entries.copy()

    def flush(self, path: str) -> None:
        if self._entries:
            Path(path).write_text("\n".join(json.dumps(e, default=str) for e in self._entries))
