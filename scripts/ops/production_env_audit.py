"""Compatibility wrapper for backend.scripts.production_env_audit."""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.scripts.production_env_audit import *  # noqa: F401,F403
from backend.scripts.production_env_audit import main


if __name__ == "__main__":
    raise SystemExit(main())
