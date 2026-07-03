"""
Data Watermark for Quant OS

Tracks the freshest tick seen per symbol and exposes staleness / gap
metrics. The watermark hash is a SHA-256 of the full state so downstream
consumers can detect drift without re-reading the tick stream.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from .tick_recorder import TickRecord


@dataclass
class DataWatermark:
    """Snapshot of data freshness for a single symbol."""

    symbol: str
    latest_timestamp_utc: datetime
    latest_received_utc: datetime
    tick_count: int
    last_sequence_id: int
    gap_count: int
    stale_count: int
    out_of_order_count: int
    watermark_hash: str  # SHA-256 of serialised state


class DataWatermarkTracker:
    """Mutable tracker that produces immutable DataWatermark snapshots."""

    def __init__(self, symbol: str):
        if not symbol:
            raise ValueError("symbol must not be empty")
        self.symbol = symbol
        self._watermark: DataWatermark | None = None
        self._tick_count: int = 0
        self._gap_count: int = 0
        self._stale_count: int = 0
        self._out_of_order_count: int = 0

    def update(self, tick: TickRecord) -> DataWatermark:
        """Ingest a tick and return the refreshed watermark."""
        if tick.symbol != self.symbol:
            raise ValueError(f"Tick symbol {tick.symbol} does not match tracker symbol {self.symbol}")

        self._tick_count += 1

        if tick.data_quality == "GAP":
            self._gap_count += 1
        elif tick.data_quality == "STALE":
            self._stale_count += 1
        elif tick.data_quality == "OUT_OF_ORDER":
            self._out_of_order_count += 1

        self._watermark = DataWatermark(
            symbol=self.symbol,
            latest_timestamp_utc=tick.timestamp_utc,
            latest_received_utc=tick.received_at_utc,
            tick_count=self._tick_count,
            last_sequence_id=tick.sequence_id,
            gap_count=self._gap_count,
            stale_count=self._stale_count,
            out_of_order_count=self._out_of_order_count,
            watermark_hash="",
        )
        # Compute hash over deterministic state (exclude the hash itself)
        self._watermark.watermark_hash = _compute_hash(self._watermark)
        return self._watermark

    def get_watermark(self) -> DataWatermark | None:
        return self._watermark

    def is_fresh(self, max_age_seconds: float = 3.0) -> bool:
        """True if the latest tick's provider timestamp is within max_age."""
        if self._watermark is None:
            return False
        age = (datetime.now(UTC) - self._watermark.latest_timestamp_utc).total_seconds()
        return age <= max_age_seconds

    def has_gaps(self) -> bool:
        return self._gap_count > 0


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def _compute_hash(wm: DataWatermark) -> str:
    """SHA-256 of serialised watermark state (hash field excluded)."""
    state = {
        "symbol": wm.symbol,
        "latest_timestamp_utc": wm.latest_timestamp_utc.isoformat(),
        "latest_received_utc": wm.latest_received_utc.isoformat(),
        "tick_count": wm.tick_count,
        "last_sequence_id": wm.last_sequence_id,
        "gap_count": wm.gap_count,
        "stale_count": wm.stale_count,
        "out_of_order_count": wm.out_of_order_count,
    }
    raw = json.dumps(state, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
