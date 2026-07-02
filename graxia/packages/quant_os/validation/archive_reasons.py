"""Phase BE-P6 — Archive reason recorder."""
from dataclasses import dataclass
from datetime import UTC


@dataclass
class ArchiveRecord:
    strategy_id: str
    verdict: str  # ARCHIVE_NO_EDGE, INSUFFICIENT_SAMPLE, INVALID_RUN
    reason: str
    run_id: str = ""
    timestamp_utc: str = ""
    evidence: dict = None

    def __post_init__(self):
        if self.evidence is None:
            self.evidence = {}


class ArchiveRecorder:
    """Record archive decisions with reasons."""

    def __init__(self):
        self._records: list[ArchiveRecord] = []

    def record(self, strategy_id: str, verdict: str, reason: str,
               run_id: str = "", evidence: dict = None) -> ArchiveRecord:
        from datetime import datetime
        record = ArchiveRecord(
            strategy_id=strategy_id,
            verdict=verdict,
            reason=reason,
            run_id=run_id,
            timestamp_utc=datetime.now(UTC).isoformat(),
            evidence=evidence or {},
        )
        self._records.append(record)
        return record

    def get_records(self) -> list[ArchiveRecord]:
        return self._records.copy()

    def count(self) -> int:
        return len(self._records)

    def has_archive(self, strategy_id: str) -> bool:
        return any(r.strategy_id == strategy_id for r in self._records)
