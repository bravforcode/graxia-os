"""Run Alembic after installing backend import guards."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app as _app_bootstrap  # noqa: F401 - install Windows platform import guards
from alembic.config import main


if __name__ == "__main__":
    main(argv=sys.argv[1:])
