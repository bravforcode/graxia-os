"""
Launch agent_loop.py as a background process (detached from terminal).
Usage: python launch_daemon.py [--start | --stop | --status]
"""

import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

LOOP_SCRIPT = Path(__file__).parent / "agent_loop.py"
PID_FILE = Path(__file__).parent.parent / "state" / "agent_loop.pid"
LOG_FILE = Path(__file__).parent.parent / "state" / "agent_loop.log"


def start():
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            # Check if process is running
            result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True, timeout=5)
            if str(pid) in result.stdout:
                print(f"[SKIP] Daemon already running (PID {pid})")
                return
        except Exception:
            pass

    print("[START] Launching agent loop daemon...")
    log_fh = open(LOG_FILE, "a", encoding="utf-8")  # noqa: SIM115 -- fd handed to detached subprocess, must outlive this function
    process = subprocess.Popen(
        [sys.executable, str(LOOP_SCRIPT), "--schedule"],
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
    )
    PID_FILE.write_text(str(process.pid))
    print(f"[OK] Daemon started (PID {process.pid})")
    print(f"  Log: {LOG_FILE}")
    print("  Schedule: hourly 6-9am")


def stop():
    if not PID_FILE.exists():
        print("[SKIP] No PID file found")
        return

    try:
        pid = int(PID_FILE.read_text().strip())
        print(f"[STOP] Stopping daemon (PID {pid})...")
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=5)
        PID_FILE.unlink(missing_ok=True)
        print("[OK] Daemon stopped")
    except Exception as e:
        print(f"[WARN] {e}")
        PID_FILE.unlink(missing_ok=True)


def status():
    if not PID_FILE.exists():
        print("[STATUS] Daemon not running (no PID file)")
        return

    try:
        pid = int(PID_FILE.read_text().strip())
        result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True, timeout=5)
        if str(pid) in result.stdout:
            print(f"[STATUS] Daemon running (PID {pid})")
            if LOG_FILE.exists():
                lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
                print(f"  Log lines: {len(lines)}")
                if lines:
                    print(f"  Last: {lines[-1][:100]}")
        else:
            print(f"[STATUS] Daemon NOT running (stale PID {pid})")
            PID_FILE.unlink(missing_ok=True)
    except Exception as e:
        print(f"[STATUS] Error: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--start", action="store_true")
    group.add_argument("--stop", action="store_true")
    group.add_argument("--status", action="store_true")
    args = parser.parse_args()

    if args.stop:
        stop()
    elif args.status:
        status()
    else:
        start()
