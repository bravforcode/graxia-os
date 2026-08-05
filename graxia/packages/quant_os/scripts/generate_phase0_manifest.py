"""Generate Phase 0 manifest with hashes of all locked artifacts."""
import hashlib
import json
from datetime import datetime, UTC
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

ARTIFACTS = [
    "reports/stopping_rule_2026_07_12.md",
    "reports/hypothesis_02_real_yield_divergence.md",
    "reports/go_live_gate_corrected_sequencing.md",
    "scripts/split_sacred_holdout.py",
    "data/rydc/rydc_research.csv",
    "data/sacred_holdout/holdout.csv",
]

manifest = {
    "phase": 0,
    "description": "Stopping rule + sacred holdout separation",
    "lock_timestamp": datetime.now(UTC).isoformat(),
    "artifacts": [],
}

for path_str in ARTIFACTS:
    full_path = PROJECT_ROOT / path_str
    if full_path.exists():
        content = full_path.read_bytes()
        manifest["artifacts"].append({
            "path": path_str,
            "size_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "exists": True,
        })
    else:
        manifest["artifacts"].append({
            "path": path_str,
            "exists": False,
        })

# Write manifest
manifest_file = PROJECT_ROOT / "reports" / "phase_0_manifest.json"
with open(manifest_file, "w") as f:
    json.dump(manifest, f, indent=2)

print(f"Manifest: {manifest_file}")
print()
print("Artifacts:")
for a in manifest["artifacts"]:
    if a.get("exists"):
        print(f"  [OK] {a['path']}")
        print(f"       sha256: {a['sha256']}")
        print(f"       size: {a['size_bytes']:,} bytes")
    else:
        print(f"  [MISSING] {a['path']}")
