"""
Tick Store for Quant OS

Persists TickRecord objects as JSON files, one file per symbol per day.
No order submission — pure data recording.
"""

import contextlib
import json
import os
import tempfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from .tick_recorder import TickRecord

# Column order for the parquet tick files (flat layout, extended schema).
TICK_COLUMNS = [
    "timestamp_utc", "received_at_utc", "symbol", "bid", "ask", "last",
    "spread_points", "flags", "sequence_id", "connection_session_id",
    "source", "data_quality", "time_msc", "volume", "flags_mt5",
]


def write_batch(records: List[TickRecord], out_dir: str | Path, symbol: str, trading_day: date) -> Path:
    """Atomic write of TickRecords to {out_dir}/{symbol}_{date}.parquet.

    Always replaces the complete file (never a partial append) and never
    leaves a temp file behind: write to a unique .parquet.tmp, fsync, then
    os.replace so DuckDB views only ever see complete files.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{symbol}_{trading_day.isoformat()}.parquet"
    df = pd.DataFrame(
        [
            {
                "timestamp_utc": r.timestamp_utc.astimezone(UTC).isoformat(),
                "received_at_utc": r.received_at_utc.astimezone(UTC).isoformat(),
                "symbol": r.symbol,
                "bid": float(r.bid),
                "ask": float(r.ask),
                "last": float(r.last),
                "spread_points": float(r.spread_points),
                "flags": r.flags,
                "sequence_id": r.sequence_id,
                "connection_session_id": r.connection_session_id,
                "source": r.source,
                "data_quality": r.data_quality,
                "time_msc": r.time_msc,
                "volume": r.volume,
                "flags_mt5": r.mt5_flags,
            }
            for r in records
        ],
        columns=TICK_COLUMNS,
    )
    fd, tmp_path = tempfile.mkstemp(dir=str(out_dir), prefix=".tick_", suffix=".parquet.tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            df.to_parquet(fh, index=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, str(path))
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
    return path


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
