"""Data manifest system — INV-005 compliance.

Every dataset must have a manifest with SHA-256 checksum.

Usage:
    from data.manifest import DataManifest
    manifest = DataManifest(symbol="XAUUSD", date_range="2024-01-01:2024-12-31", ...)
    manifest.save(Path("data/warehouse/bronze/ohlcv/XAUUSD_M1.parquet"))
    valid, msg = DataManifest.validate(Path("data/warehouse/bronze/ohlcv/XAUUSD_M1.parquet"))
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class DataManifest:
    """Manifest for data partitions. INV-005: every dataset must have one."""

    symbol: str
    date_range: str  # "2024-01-01:2024-12-31"
    row_count: int
    checksum: str  # SHA-256 hex
    schema_hash: str  # hash of column names + types
    pipeline_version: str = "1.0.0"
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def save(self, data_path: Path) -> Path:
        """Write manifest.json next to data file. Returns manifest path."""
        manifest_path = data_path.parent / f"{data_path.stem}_manifest.json"
        manifest_path.write_text(json.dumps(asdict(self), indent=2, default=str))
        return manifest_path

    @classmethod
    def load(cls, data_path: Path) -> DataManifest:
        """Load manifest for a data file. Raises FileNotFoundError if missing."""
        manifest_path = data_path.parent / f"{data_path.stem}_manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(
                f"INV-005 violation: missing manifest for {data_path}. "
                f"Expected at {manifest_path}"
            )
        data = json.loads(manifest_path.read_text())
        return cls(**data)

    @classmethod
    def compute_checksum(cls, file_path: Path) -> str:
        """SHA-256 checksum of file contents."""
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    @classmethod
    def compute_schema_hash(cls, columns: list[str], dtypes: dict[str, str]) -> str:
        """Hash of schema (column names + types)."""
        schema_str = json.dumps({"columns": columns, "dtypes": dtypes}, sort_keys=True)
        return hashlib.sha256(schema_str.encode()).hexdigest()[:16]

    @classmethod
    def validate(cls, file_path: Path) -> tuple[bool, str]:
        """Validate file against manifest. Returns (valid, message).

        Checks:
        1. Manifest exists (INV-005)
        2. Checksum matches
        """
        try:
            manifest = cls.load(file_path)
        except FileNotFoundError as e:
            return False, str(e)

        actual = cls.compute_checksum(file_path)
        if actual != manifest.checksum:
            return (
                False,
                f"CHECKSUM_MISMATCH: manifest={manifest.checksum[:16]}... "
                f"actual={actual[:16]}...",
            )

        return True, "VALID"

    @classmethod
    def create_for_file(
        cls,
        file_path: Path,
        symbol: str,
        date_range: str,
        row_count: int,
        columns: list[str],
        dtypes: dict[str, str],
        pipeline_version: str = "1.0.0",
    ) -> DataManifest:
        """Create and save manifest for a data file."""
        checksum = cls.compute_checksum(file_path)
        schema_hash = cls.compute_schema_hash(columns, dtypes)
        manifest = cls(
            symbol=symbol,
            date_range=date_range,
            row_count=row_count,
            checksum=checksum,
            schema_hash=schema_hash,
            pipeline_version=pipeline_version,
        )
        manifest.save(file_path)
        return manifest
