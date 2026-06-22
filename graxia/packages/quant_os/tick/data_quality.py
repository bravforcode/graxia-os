"""Phase BE-P2 — Data quality rules for tick data."""
from dataclasses import dataclass
from enum import Enum


class IncidentType(Enum):
    INVALID_BID = "invalid_bid"
    INVALID_ASK = "invalid_ask"
    INVERTED_QUOTE = "inverted_quote"
    OUT_OF_ORDER = "out_of_order"
    GAP = "gap"
    DUPLICATE = "duplicate"
    STALE = "stale"
    SESSION_BREAK = "session_break"


@dataclass
class QualityIncident:
    incident_type: str
    tick_id: int
    detail: str
    severity: str  # "warning", "critical"


class DataQualityChecker:
    """Validate ticks against quality rules."""

    def __init__(self, stale_threshold_ms: int = 5000, gap_threshold: int = 100):
        self.stale_threshold_ms = stale_threshold_ms
        self.gap_threshold = gap_threshold
        self._last_source_time_ms: int = 0
        self._last_sequence: int = 0
        self._incidents: list[QualityIncident] = []

    def check_tick(self, tick: dict) -> list[QualityIncident]:
        """Run all quality checks on a tick."""
        incidents = []

        bid = tick.get("bid", 0)
        ask = tick.get("ask", 0)
        tick_id = tick.get("tick_id", 0)
        source_time_ms = tick.get("source_time_msc", 0)
        ingest_seq = tick.get("ingest_sequence", 0)

        # Rule: bid <= 0 -> invalid
        if bid <= 0:
            incidents.append(QualityIncident(
                IncidentType.INVALID_BID.value, tick_id,
                f"bid={bid}", "critical"
            ))

        # Rule: ask <= 0 -> invalid
        if ask <= 0:
            incidents.append(QualityIncident(
                IncidentType.INVALID_ASK.value, tick_id,
                f"ask={ask}", "critical"
            ))

        # Rule: ask < bid -> inverted
        if bid > 0 and ask > 0 and ask < bid:
            incidents.append(QualityIncident(
                IncidentType.INVERTED_QUOTE.value, tick_id,
                f"ask={ask} < bid={bid}", "critical"
            ))

        # Rule: source time moves backwards
        if source_time_ms > 0 and source_time_ms < self._last_source_time_ms:
            incidents.append(QualityIncident(
                IncidentType.OUT_OF_ORDER.value, tick_id,
                f"time={source_time_ms} < last={self._last_source_time_ms}", "warning"
            ))

        # Rule: sequence gap
        if ingest_seq > 0 and self._last_sequence > 0:
            gap = ingest_seq - self._last_sequence
            if gap > self.gap_threshold:
                incidents.append(QualityIncident(
                    IncidentType.GAP.value, tick_id,
                    f"gap={gap}", "warning"
                ))

        # Rule: same tick replayed (duplicate)
        if ingest_seq > 0 and ingest_seq == self._last_sequence and self._last_sequence > 0:
            incidents.append(QualityIncident(
                IncidentType.DUPLICATE.value, tick_id,
                f"seq={ingest_seq}", "warning"
            ))

        # Update state
        if source_time_ms > 0:
            self._last_source_time_ms = source_time_ms
        if ingest_seq > 0:
            self._last_sequence = ingest_seq

        self._incidents.extend(incidents)
        return incidents

    def get_incidents(self) -> list[QualityIncident]:
        return self._incidents.copy()

    def summary(self) -> dict:
        counts = {}
        for inc in self._incidents:
            counts[inc.incident_type] = counts.get(inc.incident_type, 0) + 1
        return counts
