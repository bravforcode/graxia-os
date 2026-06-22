"""Phase 6 — Event risk gate for shadow mode."""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class EventRiskResult:
    blocked: bool
    reason: str
    event_name: str = ""
    minutes_to_event: int = 0


class EventRiskGate:
    def __init__(self, blackout_minutes: int = 30):
        self.blackout_minutes = blackout_minutes
        self._blocked_events: list[dict] = []

    def check(self, now: datetime, events: list[dict]) -> EventRiskResult:
        for event in events:
            event_time = event.get("time")
            if event_time and isinstance(event_time, datetime):
                diff = (event_time - now).total_seconds() / 60
                if 0 <= diff <= self.blackout_minutes:
                    return EventRiskResult(
                        blocked=True,
                        reason=f"High-impact event in {diff:.0f} minutes",
                        event_name=event.get("name", "unknown"),
                        minutes_to_event=int(diff),
                    )
        return EventRiskResult(blocked=False, reason="No events in blackout window")
