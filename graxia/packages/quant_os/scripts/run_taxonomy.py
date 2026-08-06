"""raw catalog -> research/catalog_i/canonical_mechanisms.json"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from research.catalog import load_entries  # noqa: E402
from research.taxonomy import dedup_to_canonical  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: run_taxonomy.py <catalog_path> <out_path>", file=sys.stderr)
        return 2
    catalog_path, out_path = sys.argv[1], sys.argv[2]
    canon = dedup_to_canonical(load_entries(catalog_path))
    Path(out_path).write_text(
        json.dumps({"schema_version": "1.0", "direction": "I", "canonical": canon}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    print(f"canonical {len(canon)} mechanisms -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
