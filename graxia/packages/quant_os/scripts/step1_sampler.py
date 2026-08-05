"""Step 1 continuous sampler (self-looping).

Runs measure_spread_continuous.py --once every 5 minutes IN-PROCESS until the
sampling window ends (2026-08-12 20:00 UTC), writing one snapshot per tick to
data/spread_measurements/YYYY-MM-DD_directionG.json.

Task Scheduler launches this ONCE (task: quantos_step1_spread). It self-loops
for the full 7-day window, avoiding Task Scheduler repetition duration limits.
A second watchdog (step1_daily_report.py) can be scheduled daily to check counts.

Design:
- Sentinel lock must exist (data/spread_measurements/.step1_sampling.lock).
- cwd is forced to the quant_os root so MT5 config resolves regardless of how
  Task Scheduler launches us.
- Each --once invocation appends 2 measurements (BTCUSD, EURUSD).
- ~288 snapshots/symbol/day expected (5-min cadence) => ~2016/symbol over 7d.
"""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(
    r"C:\Users\menum\graxia os\graxia\packages\quant_os"
)  # hardcoded: copy of this script may live elsewhere (Task Scheduler no-space path)
LOCK = ROOT / "data" / "spread_measurements" / ".step1_sampling.lock"

# Sampling window: 2026-08-04 20:00 UTC -> 2026-08-12 20:00 UTC (7 days).
WINDOW_START = datetime(2026, 8, 4, 20, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)
INTERVAL_SEC = 300  # 5 minutes


def now_utc() -> datetime:
    return datetime.now(UTC)


def sample_once() -> tuple[int, str]:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "measure_spread_continuous.py"),
        "--once",
        "--symbols",
        "BTCUSD",
        "EURUSD",
        "--output-suffix",
        "directionG",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=90, cwd=str(ROOT))
    return r.returncode, r.stdout.strip()


def main() -> int:
    log_path = ROOT / "data" / "spread_measurements" / "step1_sampler.log"

    with open(log_path, "a", encoding="utf-8") as log:

        def logline(msg: str) -> None:
            line = f"[{now_utc().isoformat()}] {msg}"
            print(line)
            log.write(line + "\n")
            log.flush()

        if not LOCK.exists():
            logline("Sentinel lock missing — Step 1 not authorized. Exiting.")
            return 1

        logline(f"Step 1 sampler started — window {WINDOW_START.isoformat()} -> {WINDOW_END.isoformat()}")
        ok = fail = 0
        while True:
            if now_utc() >= WINDOW_END:
                logline(f"Sampling window over. Total ok={ok} fail={fail}")
                return 0
            try:
                rc, out = sample_once()
                if rc == 0:
                    ok += 1
                    logline(f"ok: {out}")
                else:
                    fail += 1
                    logline(f"FAIL rc={rc}: {out}")
            except Exception as e:  # noqa: BLE001 - keep the loop alive across transient errors
                fail += 1
                logline(f"ERROR: {e}")

            # Sleep in small chunks so WINDOW_END is honored promptly on exit.
            deadline = now_utc().timestamp() + INTERVAL_SEC
            while now_utc().timestamp() < deadline:
                time.sleep(5)
        return 0


if __name__ == "__main__":
    sys.exit(main())
