"""Phase BE-P1 — Quarantine manifest management."""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict


@dataclass
class QuarantineEntry:
    test_id: str
    reason: str
    owner: str
    issue_id: str
    expiry: str  # ISO date
    created_at: str
    signature: str = ""  # Hash of entry for integrity


class QuarantineManager:
    def __init__(self, manifest_path: str):
        self.path = Path(manifest_path)
        self._entries: list[dict] = []
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text())
            self._entries = data.get("entries", [])
        else:
            self._entries = []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        manifest = {
            "version": "1.0",
            "updated_at": datetime.utcnow().isoformat(),
            "entries": self._entries,
            "manifest_hash": self._compute_hash(),
        }
        self.path.write_text(json.dumps(manifest, indent=2))

    def _compute_hash(self) -> str:
        h = hashlib.sha256()
        for entry in self._entries:
            h.update(json.dumps(entry, sort_keys=True).encode())
        return h.hexdigest()

    def add(self, entry: QuarantineEntry) -> None:
        """Add quarantine entry."""
        entry_dict = asdict(entry)
        entry_dict.pop("signature", None)
        entry.signature = hashlib.sha256(
            json.dumps(entry_dict, sort_keys=True).encode()
        ).hexdigest()[:16]

        self._entries.append(asdict(entry))
        self._save()

    def remove(self, test_id: str) -> bool:
        """Remove quarantine entry."""
        before = len(self._entries)
        self._entries = [e for e in self._entries if e["test_id"] != test_id]
        if len(self._entries) < before:
            self._save()
            return True
        return False

    def is_quarantined(self, test_id: str) -> bool:
        """Check if test is quarantined."""
        return any(e["test_id"] == test_id for e in self._entries)

    def get_entry(self, test_id: str) -> dict | None:
        """Get quarantine entry."""
        for e in self._entries:
            if e["test_id"] == test_id:
                return e
        return None

    def list_entries(self) -> list[dict]:
        """List all entries."""
        return self._entries.copy()

    def verify_integrity(self) -> tuple[bool, str]:
        """Verify manifest integrity."""
        if not self.path.exists():
            return False, "no_manifest"
        data = json.loads(self.path.read_text())
        stored_hash = data.get("manifest_hash")
        disk_entries = data.get("entries", [])
        h = hashlib.sha256()
        for entry in disk_entries:
            h.update(json.dumps(entry, sort_keys=True).encode())
        computed_hash = h.hexdigest()
        if stored_hash == computed_hash:
            return True, "OK"
        return False, f"hash_mismatch: stored={stored_hash}, computed={computed_hash}"

    def count(self) -> int:
        return len(self._entries)
