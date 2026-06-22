"""Phase BE-P13 — Expansion decision tracker."""
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ExpansionRecord:
    tier: str
    strategy_id: str
    justification: str
    approved: bool
    violations: list = field(default_factory=list)
    timestamp_utc: str = ""
    operator_notes: str = ""
    
    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()


class ExpansionTracker:
    """Track all expansion decisions."""
    
    def __init__(self):
        self._records: list[ExpansionRecord] = []
    
    def record(self, record: ExpansionRecord) -> None:
        self._records.append(record)
    
    def get_records(self) -> list[ExpansionRecord]:
        return self._records.copy()
    
    def get_by_tier(self, tier: str) -> list[ExpansionRecord]:
        return [r for r in self._records if r.tier == tier]
    
    def get_approved(self) -> list[ExpansionRecord]:
        return [r for r in self._records if r.approved]
    
    def get_rejected(self) -> list[ExpansionRecord]:
        return [r for r in self._records if not r.approved]
    
    def summary(self) -> dict:
        return {
            "total": len(self._records),
            "approved": len(self.get_approved()),
            "rejected": len(self.get_rejected()),
        }
