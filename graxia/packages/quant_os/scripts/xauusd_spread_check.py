#!/usr/bin/env python3
"""
Quick XAUUSD spread check — thin wrapper around measure_spread.py.

For one-shot snapshot, use:
    python scripts/measure_spread.py --symbols XAUUSD --report

For continuous logging:
    python scripts/measure_spread.py --symbols XAUUSD --interval 60

This script is kept for backward compatibility. Prefer measure_spread.py directly.
"""

import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MEASURE_SCRIPT = SCRIPT_DIR / "measure_spread.py"


def main():
    print("NOTE: xauusd_spread_check.py is a thin wrapper.")
    print("      Use 'python scripts/measure_spread.py --symbols XAUUSD' directly.\n")

    if "--report" in sys.argv:
        subprocess.run(
            [sys.executable, str(MEASURE_SCRIPT), "--report", "--symbols", "XAUUSD"],
            check=True,
        )
    else:
        # One-shot snapshot: measure once and exit
        subprocess.run(
            [sys.executable, str(MEASURE_SCRIPT), "--symbols", "XAUUSD", "--interval", "999999"],
            check=True,
        )


if __name__ == "__main__":
    main()
