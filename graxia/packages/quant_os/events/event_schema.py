"""Phase BE-P3 — Point-in-time event schema."""
from dataclasses import dataclass, asdict
import hashlib
import json


@dataclass
class PointInTimeEvent:
    """Event record per BE-P3 schema."""
    event_id: str = ""
    provider_event_id: str = ""
    country: str = ""
    currency: str = ""
    event_name: str = ""
    importance: str = "LOW"  # HIGH, MEDIUM, LOW
    scheduled_at_utc: str = ""
    actual: str = ""
    forecast: str = ""
    previous: str = ""
    revised_previous: str = ""
    published_at_utc: str = ""
    received_at_utc: str = ""
    available_to_strategy_at_utc: str = ""
    provider_version: str = ""
    official_confirmation: bool = False
    payload_hash: str = ""

    def compute_hash(self) -> None:
        """Compute payload hash for integrity."""
        d = asdict(self)
        d.pop("payload_hash", None)
        self.payload_hash = hashlib.sha256(
            json.dumps(d, sort_keys=True, default=str).encode()
        ).hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PointInTimeEvent":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def validate(self) -> tuple[bool, list[str]]:
        issues = []
        if not self.event_id:
            issues.append("event_id required")
        if not self.event_name:
            issues.append("event_name required")
        if self.importance not in ("HIGH", "MEDIUM", "LOW"):
            issues.append(f"invalid importance: {self.importance}")
        if not self.scheduled_at_utc:
            issues.append("scheduled_at_utc required")
        return len(issues) == 0, issues
