"""
Tick Recorder for Quant OS

Records raw ticks with quality checks. Never invents, interpolates,
or silently upgrades stale streams. Every tick carries both the
provider timestamp and local receipt time.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional


STALE_THRESHOLD_SECONDS: float = 5.0
GAP_THRESHOLD_SECONDS: float = 2.0


@dataclass
class TickRecord:
    """Immutable record of a single tick."""

    timestamp_utc: datetime
    received_at_utc: datetime
    symbol: str
    bid: Decimal
    ask: Decimal
    last: Decimal
    spread_points: Decimal
    flags: str
    sequence_id: int
    connection_session_id: str
    source: str          # "mt5" | "simulated"
    data_quality: str    # "VALID" | "STALE" | "OUT_OF_ORDER" | "GAP"

    def __post_init__(self):
        if self.source not in ("mt5", "simulated"):
            raise ValueError(f"Invalid source: {self.source}")
        if self.data_quality not in ("VALID", "STALE", "OUT_OF_ORDER", "GAP"):
            raise ValueError(f"Invalid data_quality: {self.data_quality}")


class TickRecorder:
    """Accumulates ticks for a single symbol within a connection session."""

    def __init__(self, symbol: str, session_id: str):
        if not symbol:
            raise ValueError("symbol must not be empty")
        if not session_id:
            raise ValueError("session_id must not be empty")
        self.symbol = symbol
        self.session_id = session_id
        self._ticks: List[TickRecord] = []
        self._last_timestamp: Optional[datetime] = None
        self._sequence: int = 0

    def record_tick(
        self,
        bid: Decimal,
        ask: Decimal,
        last: Decimal,
        timestamp_utc: datetime,
        source: str = "mt5",
    ) -> TickRecord:
        """Record a tick with quality checks.

        Quality rules:
        - Out-of-order: timestamp_utc <= last recorded timestamp
        - Gap: timestamp_utc - last_timestamp > GAP_THRESHOLD_SECONDS
        - Stale: received_at_utc - timestamp_utc > STALE_THRESHOLD_SECONDS
        """
        received_at = datetime.now(timezone.utc)
        # ponytail: normalize naive → aware so callers passing utcnow()-style
        # timestamps don't break. Remove when all callers pass aware datetimes.
        if timestamp_utc.tzinfo is None:
            timestamp_utc = timestamp_utc.replace(tzinfo=timezone.utc)
        self._sequence += 1

        # Determine quality
        quality = "VALID"
        flags_parts: list[str] = []

        if self._last_timestamp is not None:
            if timestamp_utc <= self._last_timestamp:
                quality = "OUT_OF_ORDER"
                flags_parts.append("OUT_OF_ORDER")
            elif (timestamp_utc - self._last_timestamp) > timedelta(seconds=GAP_THRESHOLD_SECONDS):
                quality = "GAP"
                flags_parts.append("GAP")

        if (received_at - timestamp_utc) > timedelta(seconds=STALE_THRESHOLD_SECONDS):
            quality = "STALE"
            flags_parts.append("STALE")

        # Spread
        spread = ask - bid

        record = TickRecord(
            timestamp_utc=timestamp_utc,
            received_at_utc=received_at,
            symbol=self.symbol,
            bid=bid,
            ask=ask,
            last=last,
            spread_points=spread,
            flags=",".join(flags_parts) if flags_parts else "",
            sequence_id=self._sequence,
            connection_session_id=self.session_id,
            source=source,
            data_quality=quality,
        )

        self._ticks.append(record)
        self._last_timestamp = timestamp_utc
        return record

    def get_ticks(self, since: Optional[datetime] = None) -> List[TickRecord]:
        """Return ticks, optionally filtered to those >= since."""
        if since is None:
            return list(self._ticks)
        return [t for t in self._ticks if t.timestamp_utc >= since]

    def get_latest_tick(self) -> Optional[TickRecord]:
        """Return the most recent tick or None."""
        return self._ticks[-1] if self._ticks else None

    def count(self) -> int:
        return len(self._ticks)
