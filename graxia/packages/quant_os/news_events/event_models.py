from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import hashlib
import json

class EventStatus(Enum):
    SCHEDULED = "SCHEDULED"
    RELEASED = "RELEASED"
    REVISED = "REVISED"
    CANCELLED = "CANCELLED"
    DELAYED = "DELAYED"
    UNKNOWN = "UNKNOWN"

class EventImportance(Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class GateState(Enum):
    CLEAR = "CLEAR"
    PRE_EVENT_BLOCK = "PRE_EVENT_BLOCK"
    EVENT_BLOCK = "EVENT_BLOCK"
    POST_EVENT_STABILIZATION = "POST_EVENT_STABILIZATION"
    UNKNOWN = "UNKNOWN"

@dataclass(frozen=True)
class EconomicEvent:
    event_id: str
    source_event_id: str
    country: str
    currency: str
    event_name: str
    importance: EventImportance
    scheduled_at_utc: datetime
    actual: Optional[float]
    forecast: Optional[float]
    previous: Optional[float]
    revised_previous: Optional[float]
    source: str
    official_url: str
    received_at_utc: datetime
    available_to_strategy_at_utc: datetime
    source_revision_id: str
    status: EventStatus

    def payload_hash(self) -> str:
        """SHA-256 hash of deterministic event data."""
        data = json.dumps({
            "event_id": self.event_id,
            "source_event_id": self.source_event_id,
            "country": self.country,
            "currency": self.currency,
            "event_name": self.event_name,
            "importance": self.importance.value,
            "scheduled_at_utc": self.scheduled_at_utc.isoformat(),
            "actual": self.actual,
            "forecast": self.forecast,
            "previous": self.previous,
            "revised_previous": self.revised_previous,
            "status": self.status.value,
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()
