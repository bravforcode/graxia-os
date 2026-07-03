"""Hash data manifest files for reproducibility."""
import hashlib
from pathlib import Path


def main():
    manifests_dir = Path(__file__).resolve().parent.parent / "data" / "manifests"
    if not manifests_dir.exists():
        print("No manifests directory found")
        return
    for manifest in sorted(manifests_dir.glob("*_manifest.json")):
        h = hashlib.sha256(manifest.read_bytes()).hexdigest()
        print(f"{manifest.name}: {h[:16]}")


if __name__ == "__main__":
    main()
