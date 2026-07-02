"""Phase BE-P12 — Micro-live evidence pack."""
from dataclasses import dataclass
from datetime import datetime, UTC


@dataclass
class EvidenceRecord:
    record_id: str
    category: str
    description: str
    timestamp_utc: str = ""
    data: dict = None

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(UTC).isoformat()
        if self.data is None:
            self.data = {}


class MicroLiveEvidencePack:
    """Collect micro-live evidence."""

    def __init__(self):
        self._records: list[EvidenceRecord] = []

    def add(self, record: EvidenceRecord) -> None:
        self._records.append(record)

    def get_records(self) -> list[EvidenceRecord]:
        return self._records.copy()

    def get_by_category(self, category: str) -> list[EvidenceRecord]:
        return [r for r in self._records if r.category == category]

    def count(self) -> int:
        return len(self._records)

    def summary(self) -> dict:
        cats = {}
        for r in self._records:
            cats[r.category] = cats.get(r.category, 0) + 1
        return {"total": self.count(), "by_category": cats}
