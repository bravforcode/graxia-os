#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

PATTERNS = (
    re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bDROP\s+COLUMN\b", re.IGNORECASE),
    re.compile(r"\bALTER\s+TYPE\b", re.IGNORECASE),
    re.compile(r"\bTRUNCATE\b", re.IGNORECASE),
)


def main() -> int:
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    failures: list[str] = []
    for path in sorted(versions_dir.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "rollback-limited" in text.lower():
            continue
        for pattern in PATTERNS:
            if pattern.search(text):
                failures.append(f"{path.name}: matched {pattern.pattern}")
    if failures:
        print("Destructive migration patterns detected without rollback-limited annotation:")
        for failure in failures:
            print(f" - {failure}")
        return 1
    print("No unannotated destructive migration patterns detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
