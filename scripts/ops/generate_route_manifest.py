"""Generate a route manifest with expected auth controls."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.route_manifest import build_route_manifest
from app.main import app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parents[2] / "docs" / "route-manifest.json"),
    )
    args = parser.parse_args()

    manifest = build_route_manifest(app)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if manifest["summary"]["gaps_found"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
