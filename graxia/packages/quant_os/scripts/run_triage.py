"""canonical_mechanisms.json -> shortlist.json"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from research.triage import shortlist  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: run_triage.py <canonical_path> <out_path>", file=sys.stderr)
        return 2
    canon_path, out_path = sys.argv[1], sys.argv[2]
    canon = json.loads(Path(canon_path).read_text(encoding="utf-8")).get("canonical", [])
    sl = shortlist(canon)
    Path(out_path).write_text(
        json.dumps({"schema_version": "1.0", "direction": "I", "shortlist": sl}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"shortlist {len(sl)} candidates -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
