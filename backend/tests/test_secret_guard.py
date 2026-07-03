"""Test secret validation guards — enforce secret strength and reject placeholders."""

from __future__ import annotations

import pytest

from app.config import Settings


class TestSecretGuard:
    """Test secret validation at the config level."""

    def test_secret_guard_rejects_empty_secrets(self):
        """Empty secrets must fail validation."""
        with pytest.raises(RuntimeError) as exc_info:
            Settings(
                APP_ENV="development",
                SECRET_KEY=None,
                ENCRYPTION_KEY=None,
                POSTGRES_PASSWORD=None,
            )
        error = str(exc_info.value)
        assert "Required secrets not configured" in error

    def test_secret_guard_rejects_placeholder_secrets(self):
        """Placeholder secrets must fail validation."""
        with pytest.raises(RuntimeError) as exc_info:
            Settings(
                APP_ENV="development",
                SECRET_KEY="changeme",
                ENCRYPTION_KEY="your_encryption_key_here",
                POSTGRES_PASSWORD="placeholder",
            )
        error = str(exc_info.value)
        assert "Required secrets not configured" in error

    def test_secret_guard_rejects_short_secrets(self):
        """Secrets that are too short must fail."""
        with pytest.raises(RuntimeError) as exc_info:
            Settings(
                APP_ENV="development",
                SECRET_KEY="short",
                ENCRYPTION_KEY="weak",
                POSTGRES_PASSWORD="bad",
            )
        error = str(exc_info.value)
        assert "Weak secrets detected" in error

    def test_secret_guard_rejects_low_entropy_secrets(self):
        """Low entropy secrets must fail."""
        with pytest.raises(RuntimeError) as exc_info:
            Settings(
                APP_ENV="development",
                SECRET_KEY="a" * 64,
                ENCRYPTION_KEY="b" * 32,
                POSTGRES_PASSWORD="c" * 16,
            )
        error = str(exc_info.value)
        assert "insufficient entropy" in error

    def test_secret_guard_accepts_strong_secrets(self):
        """Strong secrets must pass validation."""
        settings = Settings(
            APP_ENV="development",
            SECRET_KEY="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6",
            ENCRYPTION_KEY="9f8e7d6c5b4a3928170615243f2e1d0c",
            POSTGRES_PASSWORD="StrongP@ssw0rd123!",
        )
        assert settings is not None

    def test_secret_guard_testing_mode_allows_defaults(self):
        """Testing mode auto-populates safe defaults."""
        settings = Settings(
            APP_ENV="testing",
            SECRET_KEY=None,
            ENCRYPTION_KEY=None,
            POSTGRES_PASSWORD=None,
        )
        assert settings is not None
        assert settings.SECRET_KEY is not None
        assert settings.ENCRYPTION_KEY is not None
        assert settings.POSTGRES_PASSWORD is not None

    def test_secret_guard_no_secret_leak_in_error(self):
        """Error messages must not contain the actual secret values."""
        with pytest.raises(RuntimeError) as exc_info:
            Settings(
                APP_ENV="development",
                SECRET_KEY="my-super-secret-value-12345",
                ENCRYPTION_KEY="another-secret-value",
                POSTGRES_PASSWORD="secret-password-value",
            )
        error = str(exc_info.value)
        # The actual secret values should NOT be in the error message
        assert "my-super-secret-value-12345" not in error
        assert "another-secret-value" not in error
        assert "secret-password-value" not in error
