"""Compatibility wrapper for scripts.export_openapi."""

from scripts.export_openapi import *  # noqa: F401,F403
from scripts.export_openapi import main


if __name__ == "__main__":
    raise SystemExit(main())
