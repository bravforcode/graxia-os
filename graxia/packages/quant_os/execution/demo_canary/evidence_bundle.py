"""Sealed evidence bundle for one canary lifecycle."""
import hashlib
import json
import os
from datetime import datetime, timezone

class EvidenceBundle:
    """Tamper-evident evidence bundle for one canary."""

    def __init__(self, canary_id: str, output_dir: str = "artifacts/execution"):
        self.canary_id = canary_id
        self.output_dir = os.path.join(output_dir, canary_id)
        self._artifacts = {}

    def add_artifact(self, name: str, data: dict) -> str:
        """Add an artifact and return its SHA-256."""
        content = json.dumps(data, indent=2, sort_keys=True)
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        self._artifacts[name] = {"content": content, "hash": content_hash}
        return content_hash

    def seal(self) -> dict:
        """Seal the bundle. Returns manifest with all hashes."""
        os.makedirs(self.output_dir, exist_ok=True)

        manifest = {
            "canary_id": self.canary_id,
            "sealed_at_utc": datetime.now(timezone.utc).isoformat(),
            "artifacts": {},
            "seal_hash": "",
        }

        for name, data in self._artifacts.items():
            filepath = os.path.join(self.output_dir, name)
            with open(filepath, "w") as f:
                f.write(data["content"])
            manifest["artifacts"][name] = data["hash"]

        # Compute seal hash over all artifact hashes
        seal_input = json.dumps(manifest["artifacts"], sort_keys=True)
        manifest["seal_hash"] = hashlib.sha256(seal_input.encode()).hexdigest()

        # Write manifest
        manifest_path = os.path.join(self.output_dir, "00_manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        return manifest

    def verify(self) -> bool:
        """Verify sealed bundle integrity."""
        manifest_path = os.path.join(self.output_dir, "00_manifest.json")
        if not os.path.exists(manifest_path):
            return False

        with open(manifest_path) as f:
            manifest = json.load(f)

        for name, expected_hash in manifest.get("artifacts", {}).items():
            filepath = os.path.join(self.output_dir, name)
            if not os.path.exists(filepath):
                return False
            with open(filepath) as f:
                actual_hash = hashlib.sha256(f.read().encode()).hexdigest()
            if actual_hash != expected_hash:
                return False

        return True
