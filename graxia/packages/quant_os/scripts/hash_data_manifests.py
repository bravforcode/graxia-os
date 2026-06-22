"""Phase BE-P1 — Hash all data manifests for release bundle."""
import hashlib
import json
import sys
from pathlib import Path


def hash_manifests(manifests_dir: str) -> dict:
    """Hash all JSON manifests in directory."""
    path = Path(manifests_dir)
    if not path.exists():
        return {"error": f"directory not found: {manifests_dir}"}
    
    results = {}
    h = hashlib.sha256()
    
    for f in sorted(path.glob("*.json")):
        content = f.read_bytes()
        file_hash = hashlib.sha256(content).hexdigest()
        results[f.name] = {
            "hash": file_hash,
            "size": len(content),
        }
        h.update(content)
    
    results["_combined_hash"] = h.hexdigest()
    results["_count"] = len([k for k in results if k not in ("_combined_hash", "_count")])
    
    return results


if __name__ == "__main__":
    dir_path = sys.argv[1] if len(sys.argv) > 1 else \
        "graxia/packages/quant_os/data/manifests"
    results = hash_manifests(dir_path)
    print(json.dumps(results, indent=2))
