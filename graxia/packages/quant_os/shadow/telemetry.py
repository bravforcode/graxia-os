from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
import json

@dataclass
class TelemetryEvent:
    event_type: str  # "signal_created", "signal_rejected", "signal_accepted", "pipeline_error"
    timestamp: datetime
    session_id: str
    signal_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "signal_id": self.signal_id,
            "details": self.details,
        }

@dataclass
class TelemetrySummary:
    session_id: str
    total_events: int = 0
    signals_created: int = 0
    signals_accepted: int = 0
    signals_rejected: int = 0
    pipeline_errors: int = 0
    uptime_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "total_events": self.total_events,
            "signals_created": self.signals_created,
            "signals_accepted": self.signals_accepted,
            "signals_rejected": self.signals_rejected,
            "pipeline_errors": self.pipeline_errors,
            "uptime_seconds": self.uptime_seconds,
        }

class ShadowTelemetry:
    """Telemetry collector for shadow trading sessions."""

    def __init__(self):
        self._events: list[TelemetryEvent] = []
        self._session_start: Optional[datetime] = None

    def start(self, session_id: str) -> None:
        self._session_start = datetime.utcnow()
        self._events.append(TelemetryEvent(
            event_type="session_started",
            timestamp=self._session_start,
            session_id=session_id,
        ))

    def record_signal_created(self, session_id: str, signal_id: str, details: dict = None) -> None:
        self._events.append(TelemetryEvent(
            event_type="signal_created",
            timestamp=datetime.utcnow(),
            session_id=session_id,
            signal_id=signal_id,
            details=details or {},
        ))

    def record_signal_accepted(self, session_id: str, signal_id: str, details: dict = None) -> None:
        self._events.append(TelemetryEvent(
            event_type="signal_accepted",
            timestamp=datetime.utcnow(),
            session_id=session_id,
            signal_id=signal_id,
            details=details or {},
        ))

    def record_signal_rejected(self, session_id: str, signal_id: str, reason: str, details: dict = None) -> None:
        d = details or {}
        d["rejection_reason"] = reason
        self._events.append(TelemetryEvent(
            event_type="signal_rejected",
            timestamp=datetime.utcnow(),
            session_id=session_id,
            signal_id=signal_id,
            details=d,
        ))

    def record_pipeline_error(self, session_id: str, error: str, details: dict = None) -> None:
        d = details or {}
        d["error"] = error
        self._events.append(TelemetryEvent(
            event_type="pipeline_error",
            timestamp=datetime.utcnow(),
            session_id=session_id,
            details=d,
        ))

    def get_summary(self, session_id: str) -> TelemetrySummary:
        session_events = [e for e in self._events if e.session_id == session_id]
        uptime = 0.0
        if self._session_start:
            uptime = (datetime.utcnow() - self._session_start).total_seconds()

        return TelemetrySummary(
            session_id=session_id,
            total_events=len(session_events),
            signals_created=sum(1 for e in session_events if e.event_type == "signal_created"),
            signals_accepted=sum(1 for e in session_events if e.event_type == "signal_accepted"),
            signals_rejected=sum(1 for e in session_events if e.event_type == "signal_rejected"),
            pipeline_errors=sum(1 for e in session_events if e.event_type == "pipeline_error"),
            uptime_seconds=uptime,
        )

    def export_json(self, session_id: str) -> str:
        session_events = [e for e in self._events if e.session_id == session_id]
        return json.dumps([e.to_dict() for e in session_events], indent=2)

    def list_events(self) -> list[TelemetryEvent]:
        return list(self._events)
