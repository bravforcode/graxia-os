"""Production entrypoint that enforces a Redis singleton lock before Celery beat starts."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time

from app.tasks.beat_lock import BEAT_LOCK_KEY, BEAT_LOCK_TTL
from app.tasks.queues import get_sync_redis_client

HEARTBEAT_INTERVAL_SECONDS = 60


def main() -> int:
    redis_client = get_sync_redis_client()
    if redis_client is None:
        print("Redis is required for production beat singleton lock.", file=sys.stderr)
        return 1

    instance_id = f"beat:{os.uname().nodename if hasattr(os, 'uname') else os.getenv('COMPUTERNAME', 'host')}:{os.getpid()}"
    acquired = redis_client.set(BEAT_LOCK_KEY, instance_id, ex=BEAT_LOCK_TTL, nx=True)
    if not acquired:
        owner = redis_client.get(BEAT_LOCK_KEY)
        print(f"Beat lock is already held by {owner}; refusing to start.", file=sys.stderr)
        return 1

    process = subprocess.Popen(
        [sys.executable, "-m", "celery", "-A", "app.tasks.celery_app", "beat"],
    )

    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(HEARTBEAT_INTERVAL_SECONDS):
            current = redis_client.get(BEAT_LOCK_KEY)
            if current != instance_id:
                process.terminate()
                os._exit(1)
            redis_client.expire(BEAT_LOCK_KEY, BEAT_LOCK_TTL)

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()

    def shutdown(_signum, _frame) -> None:
        stop.set()
        process.terminate()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        return process.wait()
    finally:
        stop.set()
        current = redis_client.get(BEAT_LOCK_KEY)
        if current == instance_id:
            redis_client.delete(BEAT_LOCK_KEY)


if __name__ == "__main__":
    raise SystemExit(main())
