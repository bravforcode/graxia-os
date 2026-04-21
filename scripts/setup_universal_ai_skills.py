#!/usr/bin/env python3
"""Compatibility wrapper for the Universal Skills Hub reindex."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    print("setup_universal_ai_skills.py is now a compatibility wrapper.")
    print("Rebuilding the file-based Obsidian skills hub; no daemon will be started.")
    return subprocess.call([sys.executable, str(ROOT / "scripts" / "consolidate_all_skills.py")], cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
