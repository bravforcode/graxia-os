"""Phase BE-P3 — Event metrics and logging hooks."""

import json
from datetime import UTC, datetime
from pathlib import Path


class EventMetrics:
    """Collects event gate metrics."""

    def __init__(self):
        self._events_received: int = 0
        self._events_blocked: int = 0
        self._block_durations_ms: list[float] = []
        self._gate_transitions: list[dict] = []

    def record_event_received(self, event_name: str, importance: str) -> None:
        self._events_received += 1

    def record_block(self, event_name: str, reason: str, duration_ms: float = 0) -> None:
        self._events_blocked += 1
        self._block_durations_ms.append(duration_ms)
        self._gate_transitions.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "event": event_name,
                "reason": reason,
                "duration_ms": duration_ms,
            }
        )

    def get_summary(self) -> dict:
        durations = self._block_durations_ms
        return {
            "events_received": self._events_received,
            "events_blocked": self._events_blocked,
            "block_rate": self._events_blocked / max(self._events_received, 1),
            "avg_block_duration_ms": sum(durations) / max(len(durations), 1),
            "transitions": len(self._gate_transitions),
        }

    def export(self, path: str) -> None:
        Path(path).write_text(json.dumps(self.get_summary(), indent=2))
