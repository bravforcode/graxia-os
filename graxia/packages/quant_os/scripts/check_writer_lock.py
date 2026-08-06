"""Pre-commit hook: refuse commits while a LIVE foreign writer lock exists.

Closes the A18 advisory-lock gap: ``.writer.lock`` was previously enforced
only by run_release_gate.py. This hook makes it load-bearing for git commits.
Exit 0 = allow commit; exit 1 = refuse.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]  # monorepo root (same as acquire script)


def _lock_path() -> Path:
    """Resolve the lock path at CALL time so WRITER_LOCK_ROOT overrides work in tests."""
    if os.environ.get("WRITER_LOCK_ROOT"):
        return Path(os.environ["WRITER_LOCK_ROOT"]) / ".writer.lock"
    return REPO_ROOT / ".writer.lock"


def pid_alive(pid: int) -> bool:
    """Return True if a process with ``pid`` exists on this host."""
    if pid is None or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, int(pid))
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(int(pid), 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def main() -> int:
    lock_path = _lock_path()
    if not lock_path.exists():
        return 0
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        print(f"writer-lock: unreadable {lock_path} — remove manually or fix; refusing commit.")
        return 1
    owner = data.get("owner", "unknown")
    pid = data.get("pid", -1)
    if not pid_alive(pid):
        print(
            f"writer-lock: stale (owner={owner}, pid={pid} dead) — commit allowed; "
            f"clear with acquire --force after review."
        )
        return 0
    env_owner = os.environ.get("WRITER_LOCK_OWNER")
    if env_owner and data.get("owner") == env_owner:
        return 0  # committing session holds the lock
    print(
        f"writer-lock: LIVE foreign lock (owner={owner}, pid={pid}) — refusing commit per F26. "
        f"Set WRITER_LOCK_OWNER=<owner> if you are that session, or wait for release."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
