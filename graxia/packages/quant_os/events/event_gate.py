"""Phase BE-P3 — Event gate state machine."""
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timezone


class GateState(Enum):
    CLEAR = "CLEAR"
    PRE_EVENT_BLOCK = "PRE_EVENT_BLOCK"
    DURING_EVENT_BLOCK = "DURING_EVENT_BLOCK"
    POST_EVENT_STABILIZATION = "POST_EVENT_STABILIZATION"
    UNKNOWN_FAIL_CLOSED = "UNKNOWN_FAIL_CLOSED"


@dataclass
class EventRecord:
    event_id: str
    event_name: str
    importance: str  # HIGH, MEDIUM, LOW
    scheduled_at_utc: str
    actual: str = ""
    forecast: str = ""
    previous: str = ""
    published_at_utc: str = ""
    received_at_utc: str = ""
    provider: str = ""
    payload_hash: str = ""


class EventGate:
    """Event-risk gate. Blocks entries during high-impact events."""

    def __init__(self, pre_block_minutes: int = 30, post_block_minutes: int = 15,
                 stabilization_ticks: int = 10):
        self._state = GateState.CLEAR
        self._pre_block_minutes = pre_block_minutes
        self._post_block_minutes = post_block_minutes
        self._stabilization_ticks = stabilization_ticks
        self._current_event: EventRecord | None = None
        self._blocks_received: int = 0
        self._block_reason: str = ""

    def get_state(self) -> GateState:
        return self._state

    def evaluate(self, now_utc: datetime, pending_events: list[EventRecord],
                 current_spread_multiplier: float = 1.0,
                 tick_age_ms: float = 0) -> GateState:
        """Evaluate gate state against current conditions."""

        # Check for high-impact events
        high_impact = [e for e in pending_events if e.importance == "HIGH"]

        if high_impact:
            for event in high_impact:
                scheduled = datetime.fromisoformat(event.scheduled_at_utc.replace("Z", "+00:00"))
                minutes_until = (scheduled - now_utc).total_seconds() / 60

                if minutes_until <= self._pre_block_minutes and minutes_until > 0:
                    self._state = GateState.PRE_EVENT_BLOCK
                    self._current_event = event
                    self._block_reason = f"pre_event: {event.event_name} in {minutes_until:.0f}min"
                    return self._state

                if event.published_at_utc:
                    published = datetime.fromisoformat(event.published_at_utc.replace("Z", "+00:00"))
                    minutes_since = (now_utc - published).total_seconds() / 60
                    if minutes_since < self._post_block_minutes:
                        self._state = GateState.DURING_EVENT_BLOCK
                        self._current_event = event
                        self._block_reason = f"during_event: {event.event_name} released {minutes_since:.0f}min ago"
                        return self._state

                    if minutes_since < self._post_block_minutes + self._stabilization_ticks:
                        self._state = GateState.POST_EVENT_STABILIZATION
                        self._current_event = event
                        self._block_reason = f"stabilization: {event.event_name}"
                        return self._state

        # No blocking events
        self._state = GateState.CLEAR
        self._current_event = None
        self._block_reason = ""
        return self._state

    def is_blocking(self) -> bool:
        return self._state != GateState.CLEAR

    def get_block_reason(self) -> str:
        return self._block_reason

    def get_current_event(self) -> EventRecord | None:
        return self._current_event

    def get_summary(self) -> dict:
        return {
            "state": self._state.value,
            "is_blocking": self.is_blocking(),
            "block_reason": self._block_reason,
            "current_event": self._current_event.event_name if self._current_event else None,
        }
