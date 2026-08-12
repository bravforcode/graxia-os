"""Tests for Phase 22.6 safe local runtime profile.

Verifies that all safety invariants are maintained when starting
the backend with inline env overrides (no .env).
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import REPO_ROOT, Settings

ENV_FILE = REPO_ROOT / ".env"


def _make_safe_env() -> dict[str, str]:
    """Create a minimal safe environment for local runtime boot.

    Uses high-entropy strings to pass the config entropy checks
    (SECRET_KEY >= 4.0, ENCRYPTION_KEY >= 3.0, POSTGRES_PASSWORD >= 2.5).
    """
    return {
        "SECRET_KEY": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f",
        "ENCRYPTION_KEY": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
        "POSTGRES_PASSWORD": "a1b2c3d4e5f6g7h8",
        "DATABASE_URL": "sqlite+aiosqlite:///./test_runtime.db",
        "APP_ENV": "development",
        "ALLOW_LIVE_STRIPE": "false",
        "ALLOW_REAL_EMAIL_SEND": "false",
        "ALLOW_REAL_GOOGLE_MUTATION": "false",
        "ALLOW_REAL_LLM_CALLS": "false",
        "ALLOW_PRODUCTION_DB": "false",
        "NO_LIVE_PAYMENT_MODE": "true",
        "KILL_SWITCH_ALL_EXTERNAL_BETA": "true",
        "BETA_ENABLED": "false",
        "PRODUCTION_READY": "false",
    }


def test_safe_runtime_profile_loads_without_error():
    """The safe env should not raise during Settings construction."""
    env = _make_safe_env()
    with patch.dict("os.environ", env, clear=True):
        settings = Settings()  # type: ignore[call-arg]
        assert settings.SECRET_KEY == env["SECRET_KEY"]
        assert settings.ENCRYPTION_KEY == env["ENCRYPTION_KEY"]
        assert settings.POSTGRES_PASSWORD == env["POSTGRES_PASSWORD"]


def test_database_url_sqlite():
    """Safe profile should use SQLite, not Postgres."""
    env = _make_safe_env()
    with patch.dict("os.environ", env, clear=True):
        settings = Settings()  # type: ignore[call-arg]
        assert settings.DATABASE_URL.startswith("sqlite+aiosqlite")
        assert "test_runtime" in settings.DATABASE_URL


def test_production_readiness_false():
    """production_ready must be false in safe profile."""
    env = _make_safe_env()
    with patch.dict("os.environ", env, clear=True):
        settings = Settings()  # type: ignore[call-arg]
        assert settings.PRODUCTION_READY is False


def test_live_providers_disabled():
    """All live provider flags must be false in safe profile."""
    env = _make_safe_env()
    with patch.dict("os.environ", env, clear=True):
        settings = Settings()  # type: ignore[call-arg]
        assert settings.ALLOW_LIVE_STRIPE is False
        assert settings.ALLOW_REAL_EMAIL_SEND is False
        assert settings.ALLOW_REAL_GOOGLE_MUTATION is False
        assert settings.ALLOW_REAL_LLM_CALLS is False
        assert settings.ALLOW_PRODUCTION_DB is False


def test_no_live_payment_mode_true():
    """NO_LIVE_PAYMENT_MODE must be true in safe profile."""
    env = _make_safe_env()
    with patch.dict("os.environ", env, clear=True):
        settings = Settings()  # type: ignore[call-arg]
        assert settings.NO_LIVE_PAYMENT_MODE is True


def test_kill_switch_enabled():
    """Kill switch must be enabled (locked) in safe profile."""
    env = _make_safe_env()
    with patch.dict("os.environ", env, clear=True):
        settings = Settings()  # type: ignore[call-arg]
        assert settings.KILL_SWITCH_ALL_EXTERNAL_BETA is True


def test_beta_disabled():
    """Beta must be disabled in safe profile."""
    env = _make_safe_env()
    with patch.dict("os.environ", env, clear=True):
        settings = Settings()  # type: ignore[call-arg]
        assert settings.BETA_ENABLED is False


def test_app_env_development():
    """APP_ENV must be development in safe profile."""
    env = _make_safe_env()
    with patch.dict("os.environ", env, clear=True):
        settings = Settings()  # type: ignore[call-arg]
        assert settings.APP_ENV.lower() == "development"


def test_missing_secrets_still_fails():
    """Omitting a required secret should raise RuntimeError.

    Note: This test requires mocking the .env file away, which is
    difficult on Windows (Path.exists is read-only, builtins.open
    breaks pydantic internals). Skipped on Windows.
    """
    import sys as _sys
    if _sys.platform == "win32":
        pytest.skip("Cannot reliably mock .env absence on Windows")
    bad_env = _make_safe_env()
    bad_env.pop("SECRET_KEY")
    # Patch os.environ only; Settings() may read .env file on disk.
    # If .env is absent this test exercises the validator correctly.
    try:
        with patch.dict("os.environ", bad_env, clear=True):
            _ = Settings()  # type: ignore[call-arg]
        pytest.fail("Expected RuntimeError for missing SECRET_KEY")
    except RuntimeError as exc:
        msg = str(exc)
        assert "SECRET_KEY" in msg, f"Expected SECRET_KEY in error, got: {msg}"
