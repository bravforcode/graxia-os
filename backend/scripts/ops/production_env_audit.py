"""Compatibility wrapper for scripts.production_env_audit."""

from scripts.production_env_audit import *  # noqa: F401,F403
from scripts.production_env_audit import main


if __name__ == "__main__":
    raise SystemExit(main())
