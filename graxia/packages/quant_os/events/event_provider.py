"""Phase BE-P3 — Event provider with versioning."""
from dataclasses import dataclass
from datetime import datetime, UTC
from .event_schema import PointInTimeEvent


@dataclass
class EventProvider:
    name: str
    version: str
    tier: int  # 1=official, 2=licensed, 3=research-only

    def create_event(self, event_name: str, importance: str,
                     scheduled_at: str, country: str = "", currency: str = "") -> PointInTimeEvent:
        """Create a point-in-time event record."""
        now = datetime.now(UTC).isoformat()
        event = PointInTimeEvent(
            event_id=f"{self.name}_{event_name}_{scheduled_at}",
            provider_event_id="",
            country=country,
            currency=currency,
            event_name=event_name,
            importance=importance,
            scheduled_at_utc=scheduled_at,
            received_at_utc=now,
            available_to_strategy_at_utc=now,
            provider_version=self.version,
        )
        event.compute_hash()
        return event

    def update_actual(self, event: PointInTimeEvent, actual: str,
                      published_at: str = "") -> PointInTimeEvent:
        """Update event with actual value."""
        event.actual = actual
        event.published_at_utc = published_at or datetime.now(UTC).isoformat()
        event.official_confirmation = self.tier == 1
        event.compute_hash()
        return event
