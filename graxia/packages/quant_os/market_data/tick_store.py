"""
Tick Store for Quant OS

Persists TickRecord objects as JSON files, one file per symbol per day.
No order submission — pure data recording.
"""

import json
import os
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List

from .tick_recorder import TickRecord


class TickStore:
    """Append-only tick persistence keyed by symbol and date."""

    def __init__(self, base_dir: str = "data/ticks"):
        self.base_dir = base_dir

    def store_tick(self, record: TickRecord) -> str:
        """Append tick to daily file. Returns the file path."""
        date_str = record.timestamp_utc.strftime("%Y-%m-%d")
        file_path = self._file_path(record.symbol, date_str)

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        entry = _tick_to_dict(record)

        # Append as a single JSON object per line (JSONL)
        with open(file_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")

        return file_path

    def load_ticks(self, symbol: str, date: str) -> List[TickRecord]:
        """Load all ticks for a symbol on a specific date (YYYY-MM-DD)."""
        file_path = self._file_path(symbol, date)

        if not os.path.exists(file_path):
            return []

        records: List[TickRecord] = []
        with open(file_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    records.append(_dict_to_tick(data))
                except json.JSONDecodeError:
                    continue  # skip corrupted lines from concurrent writes

        return records

    def get_date_files(self, symbol: str) -> List[str]:
        """List available date files for a symbol, sorted ascending."""
        symbol_dir = os.path.join(self.base_dir, symbol)
        if not os.path.isdir(symbol_dir):
            return []

        files = sorted(
            f for f in os.listdir(symbol_dir)
            if f.endswith(".jsonl")
        )
        return [os.path.join(symbol_dir, f) for f in files]

    def _file_path(self, symbol: str, date_str: str) -> str:
        return os.path.join(self.base_dir, symbol, f"{date_str}.jsonl")


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _tick_to_dict(record: TickRecord) -> Dict[str, Any]:
    return {
        "timestamp_utc": record.timestamp_utc.isoformat(),
        "received_at_utc": record.received_at_utc.isoformat(),
        "symbol": record.symbol,
        "bid": str(record.bid),
        "ask": str(record.ask),
        "last": str(record.last),
        "spread_points": str(record.spread_points),
        "flags": record.flags,
        "sequence_id": record.sequence_id,
        "connection_session_id": record.connection_session_id,
        "source": record.source,
        "data_quality": record.data_quality,
    }


def _dict_to_tick(data: Dict[str, Any]) -> TickRecord:
    return TickRecord(
        timestamp_utc=datetime.fromisoformat(data["timestamp_utc"]),
        received_at_utc=datetime.fromisoformat(data["received_at_utc"]),
        symbol=data["symbol"],
        bid=Decimal(data["bid"]),
        ask=Decimal(data["ask"]),
        last=Decimal(data["last"]),
        spread_points=Decimal(data["spread_points"]),
        flags=data.get("flags", ""),
        sequence_id=data["sequence_id"],
        connection_session_id=data["connection_session_id"],
        source=data["source"],
        data_quality=data["data_quality"],
    )
