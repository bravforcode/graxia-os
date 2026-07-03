"""Phase BE-P2 — Tick storage with parquet + DuckDB."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


class TickStorage:
    """Immutable tick storage with partitioning."""

    def __init__(self, base_dir: str):
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)

    def _partition_path(self, broker: str, server: str, symbol: str, date: str) -> Path:
        return self.base / f"broker={broker}" / f"server={server}" / f"symbol={symbol}" / f"date={date}"

    def store_tick(self, tick: dict, broker: str, server: str, symbol: str) -> Path:
        """Store a single tick as JSON line in partition."""
        date = tick.get("source_timestamp_utc", "")[:10]
        part_dir = self._partition_path(broker, server, symbol, date)
        part_dir.mkdir(parents=True, exist_ok=True)

        part_file = part_dir / "part-000.jsonl"
        with open(part_file, "a") as f:
            f.write(json.dumps(tick, default=str) + "\n")

        return part_file

    def write_manifest(self, broker: str, server: str, symbol: str, date: str, tick_count: int) -> Path:
        """Write partition manifest."""
        part_dir = self._partition_path(broker, server, symbol, date)
        manifest = {
            "broker": broker,
            "server": server,
            "symbol": symbol,
            "date": date,
            "tick_count": tick_count,
            "created_at": datetime.now(UTC).isoformat(),
        }
        manifest_path = part_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))

        # Compute partition hash
        h = hashlib.sha256()
        for f in sorted(part_dir.iterdir()):
            if f.name != "sha256.txt":
                h.update(f.read_bytes())
        (part_dir / "sha256.txt").write_text(h.hexdigest())

        return manifest_path

    def read_ticks(self, broker: str, server: str, symbol: str, date: str) -> list[dict]:
        """Read all ticks from a partition."""
        part_dir = self._partition_path(broker, server, symbol, date)
        part_file = part_dir / "part-000.jsonl"
        if not part_file.exists():
            return []
        ticks = []
        for line in part_file.read_text().splitlines():
            if line.strip():
                ticks.append(json.loads(line))
        return ticks

    def verify_partition(self, broker: str, server: str, symbol: str, date: str) -> tuple[bool, str]:
        """Verify partition integrity."""
        part_dir = self._partition_path(broker, server, symbol, date)
        sha_file = part_dir / "sha256.txt"
        if not sha_file.exists():
            return False, "no sha256.txt"

        stored_hash = sha_file.read_text().strip()
        h = hashlib.sha256()
        for f in sorted(part_dir.iterdir()):
            if f.name != "sha256.txt":
                h.update(f.read_bytes())

        if h.hexdigest() == stored_hash:
            return True, "OK"
        return False, "hash_mismatch"
