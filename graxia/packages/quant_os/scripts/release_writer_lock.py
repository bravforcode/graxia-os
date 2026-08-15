"""Release the single-writer lock (Stream D, audit-reconciliation spec).

Removes `.writer.lock` at the monorepo root. Only releases when the lock
is held by the requesting owner+pid (fail-closed: never delete a foreign
lock). Exit 0 on release, 1 when no lock exists, 2 when held by another
owner/pid.

Usage::

    python scripts/release_writer_lock.py --owner "<name>"

Procedure: always pair with scripts/acquire_writer_lock.py --owner "<name>".
"""

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]  # monorepo root
# Test/dev override: WRITER_LOCK_ROOT env var redirects the lock location.
if os.environ.get("WRITER_LOCK_ROOT"):
    REPO_ROOT = Path(os.environ["WRITER_LOCK_ROOT"])
LOCK_PATH = REPO_ROOT / ".writer.lock"


def main():
    parser = argparse.ArgumentParser(description="Release single-writer lock")
    parser.add_argument("--owner", required=True, help="Session/agent owner name")
    args = parser.parse_args()

    if not LOCK_PATH.exists():
        print("No lock file present; nothing to release")
        return 0

    try:
        data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        print(f"Lock file unreadable; remove manually: {LOCK_PATH}")
        return 2

    if data.get("owner") != args.owner or data.get("pid") != os.getpid():
        print(
            f"Refusing to release: lock held by owner={data.get('owner')}, "
            f"pid={data.get('pid')} (not {args.owner}/{os.getpid()})"
        )
        return 2

    LOCK_PATH.unlink(missing_ok=True)
    print(f"Lock released: owner={args.owner}, pid={os.getpid()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
