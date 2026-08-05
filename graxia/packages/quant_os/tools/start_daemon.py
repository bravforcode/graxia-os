"""
Launch Real-Time News Daemon — Background Process Manager
=========================================================
Usage:
    python start_daemon.py --start              # Start in background
    python start_daemon.py --stop               # Stop daemon
    python start_daemon.py --status             # Check status
    python start_daemon.py --start --foreground # Run in foreground
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
import json
import subprocess
from pathlib import Path

DAEMON_SCRIPT = Path(__file__).parent / "realtime_daemon.py"
PID_FILE = Path(__file__).parent.parent / "state" / "daemon.pid"
LOG_FILE = Path(__file__).parent.parent / "state" / "daemon.log"
STATE_FILE = Path(__file__).parent.parent / "state" / "daemon_state.json"


def is_running() -> bool:
    """Check if daemon is running."""
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
        result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True, timeout=5)
        return str(pid) in result.stdout
    except Exception:
        return False


def start_daemon(foreground: bool = False):
    """Start the daemon."""
    if is_running():
        print("[SKIP] Daemon already running")
        return

    if foreground:
        print("[START] Running in foreground (Ctrl+C to stop)...")
        subprocess.run([sys.executable, str(DAEMON_SCRIPT), "--cycle", "300"])
    else:
        print("[START] Launching background daemon...")
        log_fh = open(LOG_FILE, "a", encoding="utf-8")  # noqa: SIM115 -- fd handed to detached subprocess, must outlive this function
        process = subprocess.Popen(
            [sys.executable, str(DAEMON_SCRIPT), "--cycle", "300"],
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
        )
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(process.pid))
        print(f"[OK] Daemon started (PID {process.pid})")
        print(f"  Log: {LOG_FILE}")
        print("  Cycle: 300s (5min)")


def stop_daemon():
    """Stop the daemon."""
    if not PID_FILE.exists():
        print("[SKIP] No PID file")
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


def show_status():
    """Show daemon status."""
    print("=" * 50)
    print("REAL-TIME NEWS DAEMON STATUS")
    print("=" * 50)

    running = is_running()
    print(f"  Running: {'YES' if running else 'NO'}")

    if PID_FILE.exists():
        print(f"  PID file: {PID_FILE.read_text().strip()}")

    if LOG_FILE.exists():
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
        print(f"  Log lines: {len(lines)}")
        if lines:
            print(f"  Last log: {lines[-1][:80]}")

    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        print(f"  Total cycles: {state.get('cycles', 0)}")
        print(f"  Total articles: {state.get('articles_total', 0)}")
        print(f"  Errors: {state.get('errors', 0)}")
        print(f"  Last cycle: {state.get('last_cycle', 'never')}")

    # Check sentiment file
    sentiment_file = Path(__file__).parent.parent / "state" / "latest_sentiment.json"
    if sentiment_file.exists():
        s = json.loads(sentiment_file.read_text(encoding="utf-8"))
        print(f"\n  Latest sentiment: {s.get('overall_sentiment', '?')}")
        print(f"  Articles analyzed: {s.get('articles_analyzed', 0)}")
        print(f"  Tickers: {s.get('ticker_count', 0)}")
        print(f"  Positive: {s.get('positive_tickers', [])}")
        print(f"  Negative: {s.get('negative_tickers', [])}")

    print("=" * 50)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--start", action="store_true")
    group.add_argument("--stop", action="store_true")
    group.add_argument("--status", action="store_true")
    parser.add_argument("--foreground", action="store_true", help="Run in foreground")
    args = parser.parse_args()

    if args.stop:
        stop_daemon()
    elif args.status:
        show_status()
    else:
        start_daemon(foreground=args.foreground)
