"""Phase BE-P3 — Event gate state machine."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


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

    def __init__(self, pre_block_minutes: int = 30, post_block_minutes: int = 15, stabilization_ticks: int = 10):
        self._state = GateState.CLEAR
        self._pre_block_minutes = pre_block_minutes
        self._post_block_minutes = post_block_minutes
        self._stabilization_ticks = stabilization_ticks
        self._current_event: EventRecord | None = None
        self._blocks_received: int = 0
        self._block_reason: str = ""

    def get_state(self) -> GateState:
        return self._state

    def evaluate(
        self,
        now_utc: datetime,
        pending_events: list[EventRecord],
        current_spread_multiplier: float = 1.0,
        tick_age_ms: float = 0,
    ) -> GateState:
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

        # Check MEDIUM importance events (shorter block window)
        medium_impact = [e for e in pending_events if e.importance == "MEDIUM"]

        if medium_impact and not high_impact:  # Don't double-block
            for event in medium_impact:
                scheduled = datetime.fromisoformat(event.scheduled_at_utc.replace("Z", "+00:00"))
                minutes_until = (scheduled - now_utc).total_seconds() / 60

                # MEDIUM: block only in the 15-minute window before
                if 0 < minutes_until <= 15:
                    self._state = GateState.PRE_EVENT_BLOCK
                    self._current_event = event
                    self._block_reason = f"pre_event_medium: {event.event_name} in {minutes_until:.0f}min"
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

    def set_unknown(self, reason: str = "") -> GateState:
        """Set UNKNOWN_FAIL_CLOSED state for partial/unknown event data."""
        self._state = GateState.UNKNOWN_FAIL_CLOSED
        self._block_reason = f"unknown: {reason}" if reason else "unknown: event data incomplete"
        self._current_event = None
        return self._state

    def evaluate_unknown(self, events: list[EventRecord]) -> GateState:
        """Check if any event has incomplete data requiring fail-closed."""
        for event in events:
            if not event.scheduled_at_utc:
                return self.set_unknown(f"missing scheduled_at: {event.event_id}")
            if event.importance not in ("HIGH", "MEDIUM", "LOW"):
                return self.set_unknown(f"invalid importance: {event.importance}")
            if not event.event_name:
                return self.set_unknown(f"missing event_name: {event.event_id}")
        return GateState.CLEAR

    def get_summary(self) -> dict:
        return {
            "state": self._state.value,
            "is_blocking": self.is_blocking(),
            "block_reason": self._block_reason,
            "current_event": self._current_event.event_name if self._current_event else None,
        }
