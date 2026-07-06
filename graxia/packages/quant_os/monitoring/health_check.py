"""
GRAXIA-OS Health Check + Dual Failover.

v2.0 fix: heartbeat file, watchdog restarts the SAME process on the SAME VPS.
v3.0 fix: watchdog also notifies the STANDBY VPS to take over if the primary
stays dead past a hard threshold — a local restart can't help if the VPS itself,
not just the Python process, is the thing that's down.
"""

import pathlib
import subprocess
import sys
import time
from datetime import UTC, datetime

import requests

from ..core.telegram_notify import TelegramNotifier

HEARTBEAT_FILE = pathlib.Path("data/heartbeat.txt")
MAX_STALE_SECONDS_LOCAL_RESTART = 900  # 15 min — try local restart first
MAX_STALE_SECONDS_FAILOVER = 1800  # 30 min — escalate to standby VPS


def update_heartbeat():
    """Call this inside webhook.py main loop at start of each bar."""
    HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_FILE.write_text(datetime.now(UTC).isoformat())


def trigger_standby_takeover(standby_webhook_url: str, notifier: TelegramNotifier):
    """
    POST to standby VPS to flip it from watch-only to active.

    standby_webhook_url: a small always-on listener on the standby VPS that
    flips from watch-only to active on receiving this call.
    Use a shared secret / IP allowlist — this endpoint can place real trades.
    """
    try:
        requests.post(
            standby_webhook_url,
            json={"action": "activate"},
            timeout=10,
        )
        notifier.failover_triggered("Primary VPS heartbeat stale > 30min")
    except Exception as e:
        notifier.risk_alert(f"FAILOVER CALL FAILED: {e} — standby may not have activated, check manually")


def watchdog_loop(standby_webhook_url: str, notifier: TelegramNotifier | None = None):
    """Run as a separate process. Checks heartbeat every 300 s."""
    if notifier is None:
        notifier = TelegramNotifier()
    failover_sent = False
    while True:
        time.sleep(300)  # check every 5 min
        if HEARTBEAT_FILE.exists():
            last = datetime.fromisoformat(HEARTBEAT_FILE.read_text(encoding="utf-8").strip())
            age = (datetime.now(UTC) - last).total_seconds()
            if MAX_STALE_SECONDS_LOCAL_RESTART < age <= MAX_STALE_SECONDS_FAILOVER:
                notifier.risk_alert(f"Bot heartbeat stale {age:.0f}s — attempting local RESTART")
                subprocess.Popen(
                    [sys.executable, "webhook.py", "--live"],
                    cwd=HEARTBEAT_FILE.parent.parent,
                )
            elif age > MAX_STALE_SECONDS_FAILOVER and not failover_sent:
                trigger_standby_takeover(standby_webhook_url, notifier)
                failover_sent = True
        else:
            notifier.risk_alert("No heartbeat file — bot never started!")


if __name__ == "__main__":
    import os

    standby = os.getenv("STANDBY_WEBHOOK_URL", "")
    if not standby:
        print("STANDBY_WEBHOOK_URL not set — failover disabled.")
    watchdog_loop(standby)
