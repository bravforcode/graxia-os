"""Compatibility wrapper for backend.scripts.production_env_audit."""

from backend.scripts.production_env_audit import *  # noqa: F401,F403
from backend.scripts.production_env_audit import main


if __name__ == "__main__":
    raise SystemExit(main())
