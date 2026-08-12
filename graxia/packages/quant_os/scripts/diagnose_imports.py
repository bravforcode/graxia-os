"""Diagnose which test files hang during collection."""
import subprocess
import sys
import time

BASE = "graxia.packages.quant_os"
FILES = [
    "test_single", "test_timing", "test_timing2", "test_timing3",
    "test_vwap", "test_phase_3b_regime", "test_phase_3b_exit_gate",
    "test_phase_3b_native", "test_phase_3_3_news_events",
    "test_repo_hooks", "test_repo_manifest", "test_supply_chain",
]

for f in FILES:
    mod = f"{BASE}.tests.{f}"
    t0 = time.time()
    try:
        r = subprocess.run(
            [sys.executable, "-c", f"import {mod}"],
            capture_output=True, text=True, timeout=8,
            cwd=r"C:\Users\menum\graxia os",
        )
        dt = time.time() - t0
        if r.returncode == 0:
            print(f"OK   {f} ({dt:.1f}s)")
        else:
            err = r.stderr.strip().split("\n")[-1][:100]
            print(f"FAIL {f} ({dt:.1f}s): {err}")
    except subprocess.TimeoutExpired:
        dt = time.time() - t0
        print(f"HUNG {f} ({dt:.1f}s) TIMEOUT")
    except Exception as e:
        dt = time.time() - t0
        print(f"ERR  {f} ({dt:.1f}s) {e}")
