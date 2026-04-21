#!/usr/bin/env python3
"""Compatibility wrapper for the no-daemon Universal Skills Hub."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    print("one_time_setup_auto_load.py has been replaced by the file-based hub builder.")
    print("Rebuilding Obsidian skills-universal and bridge links; no background script will run.")
    result = subprocess.call([sys.executable, str(ROOT / "scripts" / "consolidate_all_skills.py")], cwd=ROOT)
    if result != 0:
        return result
    return subprocess.call([sys.executable, str(ROOT / "scripts" / "verify_skills_hub.py")], cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
