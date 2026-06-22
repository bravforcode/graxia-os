from dataclasses import dataclass
from enum import Enum

class EventRegion(Enum):
    US = "US"
    EU = "EU"
    UK = "UK"
    JAPAN = "JAPAN"

class EventImpact(Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

@dataclass(frozen=True)
class EventMapping:
    event_name: str
    region: EventRegion
    impact: EventImpact
    typical_impact_pips: float
    blackout_before_minutes: int
    blackout_after_minutes: int

# Key EURUSD events
KEY_EVENTS = [
    EventMapping("NFP", EventRegion.US, EventImpact.HIGH, 50.0, 30, 15),
    EventMapping("CPI YoY", EventRegion.US, EventImpact.HIGH, 30.0, 30, 15),
    EventMapping("FOMC Rate Decision", EventRegion.US, EventImpact.HIGH, 40.0, 60, 30),
    EventMapping("ECB Rate Decision", EventRegion.EU, EventImpact.HIGH, 40.0, 60, 30),
    EventMapping("GDP YoY", EventRegion.US, EventImpact.HIGH, 25.0, 30, 15),
    EventMapping("PMI Manufacturing", EventRegion.US, EventImpact.MEDIUM, 15.0, 15, 10),
    EventMapping("Retail Sales MoM", EventRegion.US, EventImpact.MEDIUM, 12.0, 15, 10),
    EventMapping("Unemployment Rate", EventRegion.US, EventImpact.MEDIUM, 10.0, 15, 10),
    EventMapping("ECB Press Conference", EventRegion.EU, EventImpact.HIGH, 35.0, 30, 30),
    EventMapping("German ZEW", EventRegion.EU, EventImpact.MEDIUM, 8.0, 15, 10),
]

def get_event_blackout(event_name: str) -> tuple[int, int]:
    for e in KEY_EVENTS:
        if e.event_name == event_name:
            return e.blackout_before_minutes, e.blackout_after_minutes
    return 15, 10  # Default

def get_high_impact_events() -> list[EventMapping]:
    return [e for e in KEY_EVENTS if e.impact == EventImpact.HIGH]
