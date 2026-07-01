"""
conftest.py — Local pytest fixtures for chaos tests.

These fixtures replace the previous module-level sys.modules mutation
and core.config monkeypatching with scoped, autouse pytest fixtures so
the side effects are active only during chaos tests and are restored
afterward.
"""

import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture(scope="session", autouse=True)
def _mock_revenue_os():
    """Mock graxia.packages.revenue_os.db only for chaos tests."""
    top_name = "graxia.packages.revenue_os"
    db_name = "graxia.packages.revenue_os.db"

    orig_top = sys.modules.get(top_name)
    orig_db = sys.modules.get(db_name)

    mock_pkg = MagicMock()
    mock_pkg.__name__ = top_name
    mock_rev_db = MagicMock()

    async def _fake_get_db():
        yield MagicMock()

    mock_rev_db.get_db = _fake_get_db

    sys.modules[top_name] = mock_pkg
    sys.modules[db_name] = mock_rev_db

    yield

    if orig_top is not None:
        sys.modules[top_name] = orig_top
    else:
        sys.modules.pop(top_name, None)
    if orig_db is not None:
        sys.modules[db_name] = orig_db
    else:
        sys.modules.pop(db_name, None)


@pytest.fixture(scope="session", autouse=True)
def _alias_get_settings():
    """Alias core.config.get_settings to get_config for chaos tests only."""
    import graxia.packages.quant_os.core.config as _cfg_mod

    already_exists = hasattr(_cfg_mod, "get_settings")
    if not already_exists:
        _cfg_mod.get_settings = _cfg_mod.get_config

    yield

    if not already_exists:
        delattr(_cfg_mod, "get_settings")
