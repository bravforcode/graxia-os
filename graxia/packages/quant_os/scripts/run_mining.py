"""Ingest one source's raw JSON batch into the Direction I catalog."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from research.catalog import ingest_batch  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: run_mining.py <catalog_path> <raw_json>", file=sys.stderr)
        return 2
    catalog_path, raw_path = sys.argv[1], sys.argv[2]
    raw = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    added, errors = ingest_batch(catalog_path, raw.get("entries", []))
    print(f"added {added}, rejected {len(errors)}")
    for e in errors:
        print(f"  REJECT: {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
