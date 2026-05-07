"""
Test suite for configuration validation (TASK 2.1: H-01).

Tests the required secrets validation at startup to prevent deployment
with weak or placeholder secrets.
"""

import os
from unittest.mock import patch

import pytest

from app.config import Settings


class TestRequiredSecretsValidation:
    """Test required secrets validation at startup."""

    def test_startup_without_secrets_fails_in_development(self):
        """Test that application fails to start without required secrets in development."""
        with pytest.raises(RuntimeError) as exc_info:
            Settings(
                APP_ENV="development",
                SECRET_KEY=None,
                ENCRYPTION_KEY=None,
                POSTGRES_PASSWORD=None,
            )
        
        error_message = str(exc_info.value)
        assert "Required secrets not configured" in error_message
        assert "SECRET_KEY" in error_message
        assert "ENCRYPTION_KEY" in error_message
        assert "POSTGRES_PASSWORD" in error_message
        assert "openssl rand" in error_message

    def test_startup_without_secrets_fails_in_production(self):
        """Test that application fails to start without required secrets in production."""
        with pytest.raises(RuntimeError) as exc_info:
            Settings(
                APP_ENV="production",
                SECRET_KEY=None,
                ENCRYPTION_KEY=None,
                POSTGRES_PASSWORD=None,
            )
        
        error_message = str(exc_info.value)
        assert "Required secrets not configured" in error_message
        assert "SECRET_KEY" in error_message
        assert "ENCRYPTION_KEY" in error_message
        assert "POSTGRES_PASSWORD" in error_message

    def test_startup_with_placeholder_secrets_fails(self):
        """Test that placeholder-looking secrets are rejected."""
        placeholder_values = [
            "changeme",
            "change-me",
            "development-secret-key",
            "your_secret_key_here",
            "paste_your_key_here",
            "replace_this",
            "placeholder",
        ]
        
        for placeholder in placeholder_values:
            with pytest.raises(RuntimeError) as exc_info:
                Settings(
                    APP_ENV="development",
                    SECRET_KEY=placeholder,
                    ENCRYPTION_KEY=placeholder,
                    POSTGRES_PASSWORD=placeholder,
                )
            
            error_message = str(exc_info.value)
            assert "Required secrets not configured" in error_message, \
                f"Placeholder '{placeholder}' should be rejected"

    def test_startup_with_weak_secret_key_fails(self):
        """Test that weak SECRET_KEY (too short) is rejected."""
        with pytest.raises(RuntimeError) as exc_info:
            Settings(
                APP_ENV="development",
                SECRET_KEY="short",  # Less than 32 characters
                ENCRYPTION_KEY="a" * 32,
                POSTGRES_PASSWORD="a" * 16,
            )
        
        error_message = str(exc_info.value)
        assert "Weak secrets detected" in error_message
        assert "SECRET_KEY must be at least 32 characters" in error_message

    def test_startup_with_weak_encryption_key_fails(self):
        """Test that weak ENCRYPTION_KEY (too short) is rejected."""
        with pytest.raises(RuntimeError) as exc_info:
            Settings(
                APP_ENV="development",
                SECRET_KEY="a" * 32,
                ENCRYPTION_KEY="short",  # Less than 32 characters
                POSTGRES_PASSWORD="a" * 16,
            )
        
        error_message = str(exc_info.value)
        assert "Weak secrets detected" in error_message
        assert "ENCRYPTION_KEY must be at least 32 characters" in error_message

    def test_startup_with_weak_postgres_password_fails(self):
        """Test that weak POSTGRES_PASSWORD (too short) is rejected."""
        with pytest.raises(RuntimeError) as exc_info:
            Settings(
                APP_ENV="development",
                SECRET_KEY="a" * 32,
                ENCRYPTION_KEY="a" * 32,
                POSTGRES_PASSWORD="short",  # Less than 16 characters
            )
        
        error_message = str(exc_info.value)
        assert "Weak secrets detected" in error_message
        assert "POSTGRES_PASSWORD must be at least 16 characters" in error_message

    def test_startup_with_low_entropy_secret_key_fails(self):
        """Test that SECRET_KEY with low entropy is rejected."""
        # String with low entropy (all same character)
        low_entropy_key = "a" * 64
        
        with pytest.raises(RuntimeError) as exc_info:
            Settings(
                APP_ENV="development",
                SECRET_KEY=low_entropy_key,
                ENCRYPTION_KEY="b" * 32,
                POSTGRES_PASSWORD="c" * 16,
            )
        
        error_message = str(exc_info.value)
        assert "Weak secrets detected" in error_message
        assert "insufficient entropy" in error_message

    def test_startup_with_strong_secrets_succeeds(self):
        """Test that application starts successfully with strong secrets."""
        settings = Settings(
            APP_ENV="development",
            SECRET_KEY="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6",  # 56 chars, mixed
            ENCRYPTION_KEY="9f8e7d6c5b4a3928170615243f2e1d0c",  # 32 chars hex-like
            POSTGRES_PASSWORD="StrongP@ssw0rd123!",  # 18 chars, mixed
        )
        
        assert settings is not None
        assert settings.SECRET_KEY == "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6"
        assert settings.ENCRYPTION_KEY == "9f8e7d6c5b4a3928170615243f2e1d0c"
        assert settings.POSTGRES_PASSWORD == "StrongP@ssw0rd123!"

    def test_testing_mode_allows_defaults(self):
        """Test that testing mode can use default values (auto-generated)."""
        settings = Settings(
            APP_ENV="testing",
            SECRET_KEY=None,
            ENCRYPTION_KEY=None,
            POSTGRES_PASSWORD=None,
        )
        
        assert settings is not None
        # Testing mode should auto-populate with test defaults
        assert settings.SECRET_KEY is not None
        assert settings.ENCRYPTION_KEY is not None
        assert settings.POSTGRES_PASSWORD is not None
        assert "test" in settings.SECRET_KEY.lower()
        assert "test" in settings.ENCRYPTION_KEY.lower()

    def test_testing_mode_case_insensitive(self):
        """Test that testing mode detection is case-insensitive."""
        for env_value in ["testing", "TESTING", "Testing", "TeStiNg"]:
            settings = Settings(
                APP_ENV=env_value,
                SECRET_KEY=None,
                ENCRYPTION_KEY=None,
                POSTGRES_PASSWORD=None,
            )
            
            assert settings is not None
            assert settings.SECRET_KEY is not None

    def test_error_messages_are_clear_and_helpful(self):
        """Test that error messages provide clear guidance."""
        with pytest.raises(RuntimeError) as exc_info:
            Settings(
                APP_ENV="development",
                SECRET_KEY=None,
                ENCRYPTION_KEY=None,
                POSTGRES_PASSWORD=None,
            )
        
        error_message = str(exc_info.value)
        
        # Should mention which secrets are missing
        assert "SECRET_KEY" in error_message
        assert "ENCRYPTION_KEY" in error_message
        assert "POSTGRES_PASSWORD" in error_message
        
        # Should provide generation commands
        assert "openssl rand -hex 32" in error_message
        assert "openssl rand -base64 32" in error_message
        
        # Should mention .env file
        assert ".env" in error_message

    def test_placeholder_detection_comprehensive(self):
        """Test that placeholder detection catches various patterns."""
        settings_class = Settings
        
        # Test various placeholder patterns
        placeholders = [
            "",
            "changeme",
            "change-me",
            "your_secret",
            "your-secret",
            "paste_here",
            "development-secret",
            "replace",
            "placeholder",
            "your-domain.com",
            "example.com",
            "example",
        ]
        
        for placeholder in placeholders:
            assert settings_class._looks_placeholder(placeholder), \
                f"Should detect '{placeholder}' as placeholder"
        
        # Test valid values that should NOT be detected as placeholders
        valid_values = [
            "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
            "9f8e7d6c5b4a3928170615243f2e1d0c",
            "StrongP@ssw0rd123!",
            "my-actual-domain.com",
        ]
        
        for valid in valid_values:
            assert not settings_class._looks_placeholder(valid), \
                f"Should NOT detect '{valid}' as placeholder"

    def test_entropy_calculation(self):
        """Test entropy calculation for secret strength validation."""
        settings = Settings(
            APP_ENV="testing",
            SECRET_KEY="test",
            ENCRYPTION_KEY="test",
            POSTGRES_PASSWORD="test",
        )
        
        # Low entropy (all same character)
        assert settings._entropy("aaaaaaaaaa") < 1.0
        
        # Medium entropy (repeated pattern)
        assert 1.0 < settings._entropy("abcabcabcabc") < 3.0
        
        # High entropy (random-looking)
        assert settings._entropy("a1b2c3d4e5f6g7h8i9j0") > 3.0

    def test_multiple_weak_secrets_all_reported(self):
        """Test that all weak secrets are reported in a single error."""
        with pytest.raises(RuntimeError) as exc_info:
            Settings(
                APP_ENV="development",
                SECRET_KEY="short",  # Too short
                ENCRYPTION_KEY="weak",  # Too short
                POSTGRES_PASSWORD="bad",  # Too short
            )
        
        error_message = str(exc_info.value)
        
        # All three should be mentioned
        assert "SECRET_KEY must be at least 32 characters" in error_message
        assert "ENCRYPTION_KEY must be at least 32 characters" in error_message
        assert "POSTGRES_PASSWORD must be at least 16 characters" in error_message

    def test_production_mode_enforces_validation(self):
        """Test that production mode enforces strict validation."""
        with pytest.raises(RuntimeError) as exc_info:
            Settings(
                APP_ENV="production",
                SECRET_KEY="a" * 32,  # Long enough but low entropy
                ENCRYPTION_KEY="b" * 32,
                POSTGRES_PASSWORD="c" * 16,
            )
        
        error_message = str(exc_info.value)
        assert "insufficient entropy" in error_message

    def test_development_mode_enforces_validation(self):
        """Test that development mode also enforces validation (not just production)."""
        with pytest.raises(RuntimeError) as exc_info:
            Settings(
                APP_ENV="development",
                SECRET_KEY=None,
                ENCRYPTION_KEY=None,
                POSTGRES_PASSWORD=None,
            )
        
        error_message = str(exc_info.value)
        assert "Required secrets not configured" in error_message

    def test_staging_mode_enforces_validation(self):
        """Test that staging mode also enforces validation."""
        with pytest.raises(RuntimeError) as exc_info:
            Settings(
                APP_ENV="staging",
                SECRET_KEY=None,
                ENCRYPTION_KEY=None,
                POSTGRES_PASSWORD=None,
            )
        
        error_message = str(exc_info.value)
        assert "Required secrets not configured" in error_message


class TestSecretsValidationEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_secret_key_exactly_32_chars_accepted(self):
        """Test that SECRET_KEY with exactly 32 characters is accepted."""
        settings = Settings(
            APP_ENV="development",
            SECRET_KEY="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",  # Exactly 32 chars
            ENCRYPTION_KEY="9f8e7d6c5b4a3928170615243f2e1d0c",
            POSTGRES_PASSWORD="StrongP@ssw0rd123!",
        )
        
        assert settings is not None

    def test_encryption_key_exactly_32_chars_accepted(self):
        """Test that ENCRYPTION_KEY with exactly 32 characters is accepted."""
        settings = Settings(
            APP_ENV="development",
            SECRET_KEY="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
            ENCRYPTION_KEY="12345678901234567890123456789012",  # Exactly 32 chars
            POSTGRES_PASSWORD="StrongP@ssw0rd123!",
        )
        
        assert settings is not None

    def test_postgres_password_exactly_16_chars_accepted(self):
        """Test that POSTGRES_PASSWORD with exactly 16 characters is accepted."""
        settings = Settings(
            APP_ENV="development",
            SECRET_KEY="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
            ENCRYPTION_KEY="9f8e7d6c5b4a3928170615243f2e1d0c",
            POSTGRES_PASSWORD="1234567890123456",  # Exactly 16 chars
        )
        
        assert settings is not None

    def test_whitespace_trimmed_before_validation(self):
        """Test that whitespace is trimmed before length validation."""
        with pytest.raises(RuntimeError) as exc_info:
            Settings(
                APP_ENV="development",
                SECRET_KEY="  short  ",  # Short even after trimming
                ENCRYPTION_KEY="  weak  ",
                POSTGRES_PASSWORD="  bad  ",
            )
        
        error_message = str(exc_info.value)
        assert "Weak secrets detected" in error_message

    def test_empty_string_treated_as_missing(self):
        """Test that empty strings are treated as missing secrets."""
        with pytest.raises(RuntimeError) as exc_info:
            Settings(
                APP_ENV="development",
                SECRET_KEY="",
                ENCRYPTION_KEY="",
                POSTGRES_PASSWORD="",
            )
        
        error_message = str(exc_info.value)
        assert "Required secrets not configured" in error_message

    def test_whitespace_only_treated_as_missing(self):
        """Test that whitespace-only strings are treated as missing."""
        with pytest.raises(RuntimeError) as exc_info:
            Settings(
                APP_ENV="development",
                SECRET_KEY="   ",
                ENCRYPTION_KEY="   ",
                POSTGRES_PASSWORD="   ",
            )
        
        error_message = str(exc_info.value)
        assert "Required secrets not configured" in error_message


class TestBackwardCompatibility:
    """Test backward compatibility and migration scenarios."""

    def test_testing_mode_provides_safe_defaults(self):
        """Test that testing mode provides safe defaults for CI/CD."""
        settings = Settings(
            APP_ENV="testing",
            SECRET_KEY=None,
            ENCRYPTION_KEY=None,
            POSTGRES_PASSWORD=None,
        )
        
        # Should have auto-generated test values
        assert len(settings.SECRET_KEY) >= 32
        assert len(settings.ENCRYPTION_KEY) >= 32
        assert len(settings.POSTGRES_PASSWORD) >= 16

    def test_explicit_test_values_override_defaults(self):
        """Test that explicit test values override auto-generated defaults."""
        custom_secret = "custom-test-secret-key-32-chars-long-enough!!"
        
        settings = Settings(
            APP_ENV="testing",
            SECRET_KEY=custom_secret,
            ENCRYPTION_KEY="custom-encryption-key-32-chars",
            POSTGRES_PASSWORD="custom-test-password",
        )
        
        assert settings.SECRET_KEY == custom_secret
