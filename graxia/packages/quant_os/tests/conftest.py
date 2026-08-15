"""Shared pytest fixtures for the test suite.

Provides a ``repo_root`` path pointing at the quant_os package root so
tests can locate sample parquet data and other project resources.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# api/orders.py transitively imports backend.app.config, whose Settings()
# enforces production-strength secrets unless APP_ENV=testing (its own
# built-in test bypass). Set before any test module can trigger that import,
# without touching the real dev secrets in backend/.env.
os.environ.setdefault("APP_ENV", "testing")

# core/config.py is fail-closed on TRADING_MODE: an unrecognised value raises
# rather than silently falling back to PAPER. That is correct for production,
# but it makes the whole suite hostage to whatever happens to be exported in
# the developer's shell -- a stale `TRADING_MODE=DEMO` was breaking collection
# across many unrelated test files. Pin the safe mode here so tests are
# hermetic. Deliberately an assignment, not setdefault: the point is to
# override ambient environment, not defer to it. A test that needs another
# mode should monkeypatch it for its own scope.
os.environ["TRADING_MODE"] = "PAPER"

# docker/paper_executor.py raises RuntimeError at import time when
# DATABASE_URL is unset, and tests/test_paper_executor.py imports pure
# helpers from it (RISK_PER_TRADE, _calculate_lot_size, ...). Without a
# default here, collection of the entire suite aborts. The tests never touch
# the engine, so a throwaway sqlite URL is sufficient and hermetic; a
# developer who explicitly exported DATABASE_URL keeps theirs.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Absolute path to the quant_os package root."""
    return Path(__file__).resolve().parent.parent
