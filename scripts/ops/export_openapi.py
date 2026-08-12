from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import app


def export_openapi(output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    spec = app.openapi()
    target.write_text(json.dumps(spec, indent=2, sort_keys=True), encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Export FastAPI OpenAPI spec to JSON.")
    parser.add_argument(
        "--output",
        default="openapi.json",
        help="Path to write the OpenAPI JSON file.",
    )
    args = parser.parse_args()
    path = export_openapi(args.output)
    print(f"OpenAPI spec exported to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
