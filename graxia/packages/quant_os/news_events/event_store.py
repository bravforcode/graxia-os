from datetime import datetime
from typing import Optional
from .event_models import EconomicEvent, EventStatus

class EventStore:
    """Point-in-time event store. Never returns events from after the query timestamp."""

    def __init__(self):
        self._events: dict[str, EconomicEvent] = {}

    def add_event(self, event: EconomicEvent) -> None:
        if event.event_id in self._events:
            existing = self._events[event.event_id]
            if event.received_at_utc > existing.received_at_utc:
                self._events[event.event_id] = event
        else:
            self._events[event.event_id] = event

    def query_at(self, as_of: datetime, currency: Optional[str] = None,
                 min_importance: Optional[str] = None) -> list[EconomicEvent]:
        """Return events available at as_of timestamp, no future leakage."""
        results = []
        for event in self._events.values():
            if event.available_to_strategy_at_utc > as_of:
                continue
            if currency and event.currency != currency:
                continue
            if min_importance and self._importance_rank(event.importance) < self._importance_rank(min_importance):
                continue
            results.append(event)
        return sorted(results, key=lambda e: e.scheduled_at_utc)

    def get_latest_status(self, event_id: str, as_of: datetime) -> Optional[EconomicEvent]:
        for event in self._events.values():
            if event.event_id == event_id and event.available_to_strategy_at_utc <= as_of:
                return event
        return None

    @staticmethod
    def _importance_rank(importance) -> int:
        from .event_models import EventImportance
        ranks = {
            EventImportance.HIGH: 3, EventImportance.MEDIUM: 2, EventImportance.LOW: 1,
            "HIGH": 3, "MEDIUM": 2, "LOW": 1,
        }
        return ranks.get(importance, 0)
