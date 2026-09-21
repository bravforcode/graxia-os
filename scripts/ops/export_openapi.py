"""Compatibility wrapper for backend.scripts.export_openapi."""

from backend.scripts.export_openapi import *  # noqa: F401,F403
from backend.scripts.export_openapi import main


if __name__ == "__main__":
    raise SystemExit(main())
