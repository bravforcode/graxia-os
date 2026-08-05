"""Acquire the single-writer lock (Stream D, audit-reconciliation spec).

Mechanism: repo-root `.writer.lock` JSON {owner, pid, timestamp}.
Fail-closed: if the lock is held by another session, this script exits
non-zero and prints the holder's identity; it NEVER overwrites a live lock.

Usage::

    python scripts/acquire_writer_lock.py --owner "<name>" [--hours 24]

Exit codes:
    0  lock acquired (or already held by THIS owner+pid)
    1  lock held by another session (fail-closed)
    2  stale-lock confirmation required (use --force after manual review)

Stale-lock handling (no silent auto-clear):
    A lock older than --hours (default 24) is considered stale. This script
    will NOT clear it automatically; it requires --force to proceed.
    --force must be an explicit human decision.

Procedure (from spec section 6): run this before a gate lane / long write
session; run scripts/release_writer_lock.py when done. The gate refuses to
run while a foreign lock is held.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]  # monorepo root
# Test/dev override: WRITER_LOCK_ROOT env var redirects the lock location.
if os.environ.get("WRITER_LOCK_ROOT"):
    REPO_ROOT = Path(os.environ["WRITER_LOCK_ROOT"])
LOCK_PATH = REPO_ROOT / ".writer.lock"
DEFAULT_STALE_HOURS = 24


def _read_lock():
    if not LOCK_PATH.exists():
        return None
    try:
        return json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"owner": "unknown", "pid": -1, "timestamp": 0.0, "parse_error": True}


def _write_lock(owner, pid):
    LOCK_PATH.write_text(
        json.dumps({"owner": owner, "pid": pid, "timestamp": time.time()}, indent=2),
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser(description="Acquire single-writer lock")
    parser.add_argument("--owner", required=True, help="Session/agent owner name")
    parser.add_argument("--hours", type=float, default=DEFAULT_STALE_HOURS, help="Stale threshold hours")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Clear a stale lock (explicit manual confirmation; no silent auto-clear)",
    )
    args = parser.parse_args()

    existing = _read_lock()
    if existing is None:
        _write_lock(args.owner, os.getpid())
        print(f"Lock acquired: owner={args.owner}, pid={os.getpid()}")
        return 0

    # Same owner+pid already holds it -> idempotent re-acquire.
    if existing.get("owner") == args.owner and existing.get("pid") == os.getpid():
        print(f"Lock already held by this session (owner={args.owner}, pid={os.getpid()})")
        return 0

    age_h = (time.time() - existing.get("timestamp", 0)) / 3600.0
    stale = age_h > args.hours

    if stale and args.force:
        print(
            f"Stale lock cleared (age {age_h:.1f}h > {args.hours}h) by explicit --force: "
            f"owner={existing.get('owner')}, pid={existing.get('pid')}"
        )
        _write_lock(args.owner, os.getpid())
        print(f"Lock acquired: owner={args.owner}, pid={os.getpid()}")
        return 0

    if stale:
        print(
            f"LOCK HELD: owner={existing.get('owner')}, pid={existing.get('pid')}, "
            f"age={age_h:.1f}h (stale > {args.hours}h). "
            f"Re-run with --force after manual review to clear."
        )
        return 2

    print(
        f"LOCK HELD by another session: owner={existing.get('owner')}, "
        f"pid={existing.get('pid')}, age={age_h:.1f}h. Fail-closed; not overwriting."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
