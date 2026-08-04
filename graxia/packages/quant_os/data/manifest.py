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

MANIFEST_DIR = Path("data/manifests")
REPO_ROOT = Path(__file__).resolve().parent.parent


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


class DataManifestManager:
    """Dataset-level INV-005 manifests — one JSON per dataset listing files.

    Reconciled alongside the per-file ``DataManifest`` sidecars: this manager
    writes ``data/manifests/{dataset_name}_manifest.json`` with repo-root-
    relative paths, size_bytes and sha256, and verifies them. Spec 5.4 shape.
    """

    def __init__(self, manifest_dir: str | Path | None = None):
        self._manifest_dir = Path(manifest_dir or MANIFEST_DIR)
        self._manifest_dir.mkdir(parents=True, exist_ok=True)

    def generate_sha256(self, file_path: str | Path) -> str:
        """SHA-256 hex digest of file contents (chunked read)."""
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()

    def _entry_path(self, p: Path) -> str:
        try:
            return p.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
        except ValueError:
            # Outside the repo (e.g. temp staging) — absolute is the only
            # stable reference for verify to resolve later.
            return str(p.resolve())

    def update_manifest(self, dataset_name: str, files: list[Path]) -> Path:
        """Write ``data/manifests/{dataset_name}_manifest.json`` for `files`.

        Missing files are skipped; paths are repo-root-relative when possible.
        """
        entries = []
        for file in files:
            p = Path(file)
            if not p.exists():
                continue
            entries.append({
                "path": self._entry_path(p),
                "size_bytes": p.stat().st_size,
                "sha256": self.generate_sha256(p),
            })
        manifest_data = {
            "dataset": dataset_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "file_count": len(entries),
            "files": entries,
        }
        manifest_path = self._manifest_dir / f"{dataset_name}_manifest.json"
        manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
        return manifest_path

    def verify_manifest(self, manifest_path: str | Path) -> list[str]:
        """Return error strings; empty list = pass.

        Checks existence, size_bytes and sha256 for every entry.
        """
        errors: list[str] = []
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        for entry in manifest.get("files", []):
            raw = entry["path"]
            p = Path(raw) if Path(raw).is_absolute() else REPO_ROOT / raw
            if not p.exists():
                errors.append(f"missing file: {entry['path']}")
                continue
            if p.stat().st_size != entry["size_bytes"]:
                errors.append(f"size mismatch: {entry['path']}")
            if self.generate_sha256(p) != entry["sha256"]:
                errors.append(f"sha256 mismatch: {entry['path']}")
        return errors
