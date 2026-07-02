"""Run release truth check — verify all artifacts are present."""

import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    required = ["pyproject.toml", "setup.py", "tests"]
    missing = [r for r in required if not (root / r).exists()]
    if missing:
        print(f"MISSING: {missing}")
        sys.exit(1)
    print("All release artifacts present")


if __name__ == "__main__":
    main()
