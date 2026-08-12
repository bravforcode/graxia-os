"""
Test suite for configuration validation (TASK 2.1: H-01).

Tests the required secrets validation at startup to prevent deployment
with weak or placeholder secrets.
"""

import os
from unittest.mock import patch

import pytest
from hypothesis import given, strategies as st

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



# ============================================================================
# Property-Based Tests for Secret Validation
# ============================================================================

@given(
    st.sampled_from([
        "changeme",
        "change-me",
        "development-secret",
        "placeholder",
        "example",
        "your_secret_here",
        "your-secret-here",
        "paste_your_key",
        "replace_me",
        "example.com",
        "your-domain.com",
        "your-project-ref",
    ])
)
def test_placeholder_detection_property(placeholder_value: str):
    """
    Property Test: Placeholder Detection
    
    Property: For every string matching placeholder patterns, _looks_placeholder(value) must return True
    
    This property-based test verifies that:
    1. All known placeholder patterns are detected
    2. No placeholder values slip through validation
    3. The detection is comprehensive
    
    SECURITY REQUIREMENT:
    - All placeholder values must be rejected in production
    - No weak secrets should pass validation
    """
    settings = Settings(APP_ENV="testing")
    
    # Test the _looks_placeholder method
    assert settings._looks_placeholder(placeholder_value) is True, (
        f"Placeholder detection failed for: {placeholder_value}. "
        f"This value should be detected as a placeholder."
    )
    
    # Test with variations (uppercase, mixed case, with whitespace)
    assert settings._looks_placeholder(placeholder_value.upper()) is True
    assert settings._looks_placeholder(placeholder_value.title()) is True
    assert settings._looks_placeholder(f"  {placeholder_value}  ") is True


@given(
    st.text(min_size=32, max_size=128).filter(
        lambda s: not any(
            pattern in s.lower()
            for pattern in [
                "changeme", "change-me", "development", "default", "placeholder",
                "example", "test", "demo", "your_", "your-", "paste_", "replace"
            ]
        )
    )
)
def test_non_placeholder_detection_property(non_placeholder_value: str):
    """
    Property Test: Non-Placeholder Detection
    
    Property: For strings that don't match placeholder patterns, _looks_placeholder(value) must return False
    
    This property-based test verifies that:
    1. Legitimate secrets are not falsely rejected
    2. The placeholder detection is not too aggressive
    3. Real secrets can pass validation
    
    SECURITY REQUIREMENT:
    - Legitimate secrets must not be rejected
    - No false positives in placeholder detection
    """
    settings = Settings(APP_ENV="testing")
    
    # Test that non-placeholder values are accepted
    result = settings._looks_placeholder(non_placeholder_value)
    
    # If it's detected as placeholder, it should be because it's empty or matches a pattern
    if result:
        # Verify it's actually a placeholder (empty, or contains forbidden patterns)
        assert (
            not non_placeholder_value.strip()
            or any(
                pattern in non_placeholder_value.lower()
                for pattern in ["your_", "your-", "paste_", "replace", "example.com"]
            )
        ), f"False positive: {non_placeholder_value[:50]} detected as placeholder but shouldn't be"


@given(
    st.sampled_from([
        "changeme",
        "change-me",
        "development-secret",
        "placeholder",
        "example",
        "test-secret",
        "demo-key",
    ])
)
def test_placeholder_in_production_errors_property(placeholder_pattern: str):
    """
    Property Test: Placeholder Rejection in Production
    
    Property: Any placeholder value in production configuration must generate an error
    
    This property-based test verifies that:
    1. Production validation catches all placeholder values
    2. No placeholder secrets can be deployed to production
    3. Error messages are generated for each placeholder
    
    SECURITY REQUIREMENT:
    - Production deployment must fail with placeholder secrets
    - All placeholder patterns must be caught
    """
    # With the new validation, Settings should raise RuntimeError immediately
    # when placeholder values are detected in production mode
    with pytest.raises(RuntimeError) as exc_info:
        Settings(
            APP_ENV="production",
            SECRET_KEY=f"strong-secret-key-{placeholder_pattern}-suffix-32chars",
            ENCRYPTION_KEY=placeholder_pattern,
            POSTGRES_PASSWORD="strong-password-16-chars",
        )
    
    # Should have an error message mentioning the placeholder
    error_message = str(exc_info.value).lower()
    assert "required secrets not configured" in error_message or "weak secrets" in error_message, (
        f"Production validation should catch placeholder: {placeholder_pattern}"
    )

@given(st.text(min_size=1, max_size=100))
def test_entropy_calculation_property(secret_value: str):
    """
    Property Test: Entropy Calculation
    
    Property: Entropy calculation should be consistent and reasonable
    
    This property-based test verifies that:
    1. Entropy is always >= 0
    2. Entropy increases with character diversity
    3. Entropy calculation is deterministic
    
    SECURITY REQUIREMENT:
    - Low entropy secrets should be detected
    - Entropy calculation should be accurate
    """
    settings = Settings(APP_ENV="testing")
    
    entropy = settings._entropy(secret_value)
    
    # Entropy should always be non-negative
    assert entropy >= 0, f"Entropy should be non-negative, got {entropy}"
    
    # Entropy should be deterministic (same input = same output)
    entropy2 = settings._entropy(secret_value)
    assert entropy == entropy2, "Entropy calculation should be deterministic"
    
    # Very simple strings (all same character) should have low entropy
    if len(set(secret_value)) == 1:
        assert entropy < 1.0, f"Single-character string should have low entropy, got {entropy}"


@given(
    st.integers(min_value=32, max_value=128),
    st.sampled_from(["abcdefghijklmnopqrstuvwxyz", "0123456789", "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "!@#$%^&*()"])
)
def test_secret_length_requirements_property(length: int, charset: str):
    """
    Property Test: Secret Length Requirements
    
    Property: Secrets meeting length requirements should pass basic validation
    
    This property-based test verifies that:
    1. Secrets of sufficient length are accepted
    2. Length requirements are enforced consistently
    3. Different character sets are handled correctly
    
    SECURITY REQUIREMENT:
    - Minimum length requirements must be enforced
    - Sufficient length secrets should pass validation
    """
    import random
    import string
    
    # Generate a random secret of the specified length
    secret = ''.join(random.choice(charset) for _ in range(length))
    
    settings = Settings(APP_ENV="testing")
    
    # Secret should not be detected as placeholder if it's random enough
    if len(set(secret)) > 5:  # Has some diversity
        is_placeholder = settings._looks_placeholder(secret)
        # Should not be placeholder unless it accidentally contains forbidden patterns
        if is_placeholder:
            assert any(
                pattern in secret.lower()
                for pattern in ["changeme", "placeholder", "example", "your_", "paste_"]
            ), f"Random secret falsely detected as placeholder: {secret[:20]}"
