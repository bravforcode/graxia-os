"""
Test suite for CSRF token expiry functionality (TASK 2.5).

Tests the CSRF token expiry timestamp feature to ensure that:
1. Tokens include expiry timestamps
2. Expired tokens are rejected
3. Valid tokens within expiry window are accepted
4. Legacy tokens (without timestamp) are supported during grace period
5. Token format is correct
"""

import time
from unittest.mock import patch

import pytest
from app.config import settings
from app.middleware.security import generate_csrf_token, validate_csrf_token_signature


class TestCSRFTokenExpiry:
    """Test CSRF token expiry functionality."""

    def test_generate_token_includes_timestamp(self):
        """Test that generated tokens include timestamp."""
        session_id = "test-session-123"
        token = generate_csrf_token(session_id)
        
        # New format should have 3 parts: random.timestamp.signature
        parts = token.split(".")
        assert len(parts) == 3, f"Token should have 3 parts, got {len(parts)}"
        
        # All parts should be non-empty
        assert all(len(part) > 0 for part in parts), "All token parts should be non-empty"

    def test_valid_token_accepted(self):
        """Test that valid tokens within expiry window are accepted."""
        session_id = "test-session-456"
        token = generate_csrf_token(session_id)
        
        # Token should be valid immediately after generation
        assert validate_csrf_token_signature(token, session_id) is True

    def test_expired_token_rejected(self):
        """Test that expired tokens are rejected."""
        session_id = "test-session-789"
        
        # Mock time to generate token in the past
        past_time = int(time.time()) - (settings.CSRF_TOKEN_EXPIRY_HOURS * 3600 + 60)  # 1 hour + 1 minute ago
        
        with patch('time.time', return_value=past_time):
            token = generate_csrf_token(session_id)
        
        # Token should be rejected (expired)
        assert validate_csrf_token_signature(token, session_id) is False

    def test_token_expiry_boundary(self):
        """Test token expiry at exact boundary."""
        session_id = "test-session-boundary"
        
        # Generate token at expiry boundary (exactly 1 hour ago)
        past_time = int(time.time()) - (settings.CSRF_TOKEN_EXPIRY_HOURS * 3600)
        
        with patch('time.time', return_value=past_time):
            token = generate_csrf_token(session_id)
        
        # Token should be rejected (at or past expiry)
        assert validate_csrf_token_signature(token, session_id) is False

    def test_token_just_before_expiry(self):
        """Test token just before expiry is still valid."""
        session_id = "test-session-almost-expired"
        
        # Generate token just before expiry (59 minutes ago)
        past_time = int(time.time()) - (settings.CSRF_TOKEN_EXPIRY_HOURS * 3600 - 60)
        
        with patch('time.time', return_value=past_time):
            token = generate_csrf_token(session_id)
        
        # Token should still be valid
        assert validate_csrf_token_signature(token, session_id) is True

    def test_legacy_token_format_supported(self):
        """Test that legacy tokens (without timestamp) are still supported."""
        import base64
        import hashlib
        import hmac
        import secrets
        
        session_id = "test-session-legacy"
        secret = settings.CSRF_SIGNING_SECRET.encode("utf-8")
        
        # Generate legacy token (old format: random.signature)
        random_part = secrets.token_bytes(32)
        message = random_part + session_id.encode("utf-8")
        signature = hmac.new(secret, message, hashlib.sha256).digest()
        legacy_token = f"{base64.urlsafe_b64encode(random_part).decode()}.{base64.urlsafe_b64encode(signature).decode()}"
        
        # Legacy token should be accepted
        assert validate_csrf_token_signature(legacy_token, session_id) is True

    def test_legacy_token_logs_warning(self, caplog):
        """Test that legacy token usage is logged for monitoring."""
        import base64
        import hashlib
        import hmac
        import secrets
        
        session_id = "test-session-legacy-log"
        secret = settings.CSRF_SIGNING_SECRET.encode("utf-8")
        
        # Generate legacy token
        random_part = secrets.token_bytes(32)
        message = random_part + session_id.encode("utf-8")
        signature = hmac.new(secret, message, hashlib.sha256).digest()
        legacy_token = f"{base64.urlsafe_b64encode(random_part).decode()}.{base64.urlsafe_b64encode(signature).decode()}"
        
        # Validate token and check logs
        with caplog.at_level("INFO"):
            validate_csrf_token_signature(legacy_token, session_id)
        
        # Should log legacy token usage
        log_messages = [record.message for record in caplog.records]
        assert any("legacy token format" in msg.lower() for msg in log_messages)

    def test_malformed_token_rejected(self):
        """Test that malformed tokens are rejected."""
        session_id = "test-session-malformed"
        
        # Test various malformed tokens
        malformed_tokens = [
            "no-dots",
            "one.dot",
            "four.dots.are.too.many",
            "",
            ".",
            "..",
            "...",
        ]
        
        for token in malformed_tokens:
            assert validate_csrf_token_signature(token, session_id) is False, \
                f"Malformed token '{token}' should be rejected"

    def test_token_with_wrong_session_id_rejected(self):
        """Test that tokens are rejected if session ID doesn't match."""
        session_id = "test-session-correct"
        wrong_session_id = "test-session-wrong"
        
        token = generate_csrf_token(session_id)
        
        # Token should be rejected with wrong session ID
        assert validate_csrf_token_signature(token, wrong_session_id) is False

    def test_token_with_tampered_timestamp_rejected(self):
        """Test that tokens with tampered timestamps are rejected."""
        import base64
        
        session_id = "test-session-tampered"
        token = generate_csrf_token(session_id)
        
        # Tamper with timestamp part
        parts = token.split(".")
        # Change timestamp to future
        future_timestamp = int(time.time()) + 3600
        tampered_timestamp = base64.urlsafe_b64encode(future_timestamp.to_bytes(8, byteorder='big')).decode()
        tampered_token = f"{parts[0]}.{tampered_timestamp}.{parts[2]}"
        
        # Tampered token should be rejected (signature won't match)
        assert validate_csrf_token_signature(tampered_token, session_id) is False

    def test_configurable_expiry_time(self):
        """Test that token expiry time is configurable."""
        session_id = "test-session-config"
        
        # Test with different expiry times
        with patch.object(settings, 'CSRF_TOKEN_EXPIRY_HOURS', 2):
            # Generate token
            past_time = int(time.time()) - (1.5 * 3600)  # 1.5 hours ago
            
            with patch('time.time', return_value=past_time):
                token = generate_csrf_token(session_id)
            
            # Token should still be valid (within 2 hour window)
            assert validate_csrf_token_signature(token, session_id) is True
        
        with patch.object(settings, 'CSRF_TOKEN_EXPIRY_HOURS', 1):
            # Same token should be expired with 1 hour window
            assert validate_csrf_token_signature(token, session_id) is False

    def test_token_uniqueness_with_timestamp(self):
        """Test that tokens are unique even with same session ID."""
        session_id = "test-session-unique"
        
        tokens = [generate_csrf_token(session_id) for _ in range(100)]
        
        # All tokens should be unique (due to random component)
        assert len(set(tokens)) == 100

    def test_timestamp_extraction_accuracy(self):
        """Test that timestamp can be accurately extracted from token."""
        import base64
        
        session_id = "test-session-timestamp"
        
        # Generate token at known time
        known_time = 1234567890
        with patch('time.time', return_value=known_time):
            token = generate_csrf_token(session_id)
        
        # Extract timestamp from token
        parts = token.split(".")
        timestamp_bytes = base64.urlsafe_b64decode(parts[1].encode("utf-8"))
        extracted_timestamp = int.from_bytes(timestamp_bytes, byteorder='big')
        
        # Timestamp should match
        assert extracted_timestamp == known_time

    def test_empty_session_id_rejected(self):
        """Test that tokens with empty session ID are rejected."""
        # Generate token with empty session ID
        token = generate_csrf_token("")
        
        # Should be rejected
        assert validate_csrf_token_signature(token, "") is False

    def test_none_session_id_rejected(self):
        """Test that None session ID is rejected."""
        # Should be rejected
        assert validate_csrf_token_signature("any-token", None) is False

    def test_none_token_rejected(self):
        """Test that None token is rejected."""
        assert validate_csrf_token_signature(None, "session-id") is False

    def test_token_format_url_safe(self):
        """Test that token format is URL-safe (no special characters)."""
        import string
        
        session_id = "test-session-url-safe"
        token = generate_csrf_token(session_id)
        
        # Token should only contain URL-safe characters
        allowed_chars = set(string.ascii_letters + string.digits + "-_=.")
        assert all(c in allowed_chars for c in token), \
            f"Token contains non-URL-safe characters: {token}"

    def test_concurrent_token_generation(self):
        """Test that concurrent token generation works correctly."""
        import asyncio
        
        session_id = "test-session-concurrent"
        
        async def generate_and_validate():
            token = generate_csrf_token(session_id)
            return validate_csrf_token_signature(token, session_id)
        
        # Generate multiple tokens concurrently
        async def run_concurrent():
            tasks = [generate_and_validate() for _ in range(50)]
            results = await asyncio.gather(*tasks)
            return results
        
        results = asyncio.run(run_concurrent())
        
        # All tokens should be valid
        assert all(results), "All concurrently generated tokens should be valid"

    def test_token_expiry_with_different_timezones(self):
        """Test that token expiry works correctly regardless of timezone."""
        session_id = "test-session-timezone"
        
        # Generate token
        token = generate_csrf_token(session_id)
        
        # Token should be valid immediately (regardless of timezone)
        assert validate_csrf_token_signature(token, session_id) is True
        
        # Mock time in the future (past expiry)
        future_time = int(time.time()) + (settings.CSRF_TOKEN_EXPIRY_HOURS * 3600 + 60)
        
        with patch('time.time', return_value=future_time):
            # Token should be expired
            assert validate_csrf_token_signature(token, session_id) is False


class TestCSRFTokenExpiryIntegration:
    """Integration tests for CSRF token expiry with middleware."""

    @pytest.mark.asyncio
    async def test_expired_token_rejected_by_middleware(self, async_client):
        """Test that expired tokens are rejected by CSRF middleware."""
        from app.middleware.security import generate_csrf_token
        
        # Generate expired token
        past_time = int(time.time()) - (settings.CSRF_TOKEN_EXPIRY_HOURS * 3600 + 60)
        
        with patch('time.time', return_value=past_time):
            expired_token = generate_csrf_token("test-session")
        
        # Try to use expired token
        original_csrf = async_client.headers.get("X-CSRF-Token")
        original_cookie = async_client.cookies.get(settings.CSRF_COOKIE_NAME)
        
        try:
            async_client.headers["X-CSRF-Token"] = expired_token
            async_client.cookies.set(settings.CSRF_COOKIE_NAME, expired_token)
            
            response = await async_client.post(
                "/api/v1/tasks/",
                json={"title": "Test Task", "priority": 5, "assigned_to": "user"},
            )
            
            # Should be rejected
            assert response.status_code == 403
            assert "CSRF" in response.json().get("detail", "")
        finally:
            if original_csrf:
                async_client.headers["X-CSRF-Token"] = original_csrf
            if original_cookie:
                async_client.cookies.set(settings.CSRF_COOKIE_NAME, original_cookie)

    @pytest.mark.asyncio
    async def test_valid_token_accepted_by_middleware(self, async_client):
        """Test that valid tokens are accepted by CSRF middleware."""
        # Use the token from async_client (should be valid)
        response = await async_client.post(
            "/api/v1/tasks/",
            json={"title": "Valid Token Test", "priority": 5, "assigned_to": "user"},
        )
        
        # Should succeed or fail for reasons other than CSRF
        assert response.status_code != 403 or "CSRF" not in response.json().get("detail", "")

    @pytest.mark.asyncio
    async def test_legacy_token_accepted_by_middleware(self, async_client):
        """Test that legacy tokens are accepted by CSRF middleware."""
        import base64
        import hashlib
        import hmac
        import secrets
        
        # Generate legacy token
        session_id = getattr(async_client, '_session_id', 'test-session')
        secret = settings.CSRF_SIGNING_SECRET.encode("utf-8")
        random_part = secrets.token_bytes(32)
        message = random_part + session_id.encode("utf-8")
        signature = hmac.new(secret, message, hashlib.sha256).digest()
        legacy_token = f"{base64.urlsafe_b64encode(random_part).decode()}.{base64.urlsafe_b64encode(signature).decode()}"
        
        # Try to use legacy token
        original_csrf = async_client.headers.get("X-CSRF-Token")
        original_cookie = async_client.cookies.get(settings.CSRF_COOKIE_NAME)
        
        try:
            async_client.headers["X-CSRF-Token"] = legacy_token
            async_client.cookies.set(settings.CSRF_COOKIE_NAME, legacy_token)
            
            response = await async_client.post(
                "/api/v1/tasks/",
                json={"title": "Legacy Token Test", "priority": 5, "assigned_to": "user"},
            )
            
            # Should succeed or fail for reasons other than CSRF
            # (Legacy tokens are supported during grace period)
            assert response.status_code != 403 or "CSRF" not in response.json().get("detail", "")
        finally:
            if original_csrf:
                async_client.headers["X-CSRF-Token"] = original_csrf
            if original_cookie:
                async_client.cookies.set(settings.CSRF_COOKIE_NAME, original_cookie)


class TestCSRFTokenExpiryEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_long_session_id(self):
        """Test token generation with very long session ID."""
        session_id = "x" * 1000
        token = generate_csrf_token(session_id)
        
        # Should work correctly
        assert validate_csrf_token_signature(token, session_id) is True

    def test_special_characters_in_session_id(self):
        """Test token generation with special characters in session ID."""
        session_id = "session-with-special-chars-!@#$%^&*()"
        token = generate_csrf_token(session_id)
        
        # Should work correctly
        assert validate_csrf_token_signature(token, session_id) is True

    def test_unicode_in_session_id(self):
        """Test token generation with Unicode characters in session ID."""
        session_id = "session-with-unicode-你好-🚀"
        token = generate_csrf_token(session_id)
        
        # Should work correctly
        assert validate_csrf_token_signature(token, session_id) is True

    def test_token_with_custom_secret(self):
        """Test token generation with custom secret."""
        session_id = "test-session-custom-secret"
        custom_secret = "my-custom-secret-key-for-testing"
        
        token = generate_csrf_token(session_id, secret=custom_secret)
        
        # Should validate with same secret
        assert validate_csrf_token_signature(token, session_id, secret=custom_secret) is True
        
        # Should fail with different secret
        assert validate_csrf_token_signature(token, session_id, secret="wrong-secret") is False

    def test_timestamp_overflow(self):
        """Test token generation with very large timestamp."""
        session_id = "test-session-overflow"
        
        # Mock time with very large value (year 2100)
        future_time = 4102444800  # 2100-01-01
        
        with patch('time.time', return_value=future_time):
            token = generate_csrf_token(session_id)
            
            # Should work correctly
            assert validate_csrf_token_signature(token, session_id) is True

    def test_zero_expiry_time(self):
        """Test behavior with zero expiry time."""
        session_id = "test-session-zero-expiry"
        
        with patch.object(settings, 'CSRF_TOKEN_EXPIRY_HOURS', 0):
            token = generate_csrf_token(session_id)
            
            # Token should be immediately expired
            assert validate_csrf_token_signature(token, session_id) is False

    def test_negative_expiry_time(self):
        """Test behavior with negative expiry time."""
        session_id = "test-session-negative-expiry"
        
        with patch.object(settings, 'CSRF_TOKEN_EXPIRY_HOURS', -1):
            token = generate_csrf_token(session_id)
            
            # Token should be immediately expired
            assert validate_csrf_token_signature(token, session_id) is False
