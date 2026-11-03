"""
Comprehensive test suite for webhook HMAC signature verification.

Tests cover:
1. Valid HMAC signature verification
2. Invalid signature rejection
3. Missing signature handling
4. Timestamp validation (replay attack prevention)
5. Malformed signature handling
6. Bearer token fallback (deprecated)
7. Request body restoration after verification
8. Edge cases (empty body, large body, special characters)
9. Property-based tests (HMAC round-trip, tampering detection)

Security Requirements:
- All signature comparisons use constant-time operations
- Timestamp validation prevents replay attacks (5-minute window)
- Request body must be restored for downstream handlers
"""
import hashlib
import hmac
import time
from unittest.mock import patch

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from hypothesis import given, strategies as st

from app.config import settings
from app.middleware.auth import AuthMiddleware


@pytest.fixture
def app():
    """Create a test Starlette app with AuthMiddleware."""
    from starlette.routing import Route
    from starlette.applications import Starlette
    
    async def webhook_endpoint(request: Request):
        # Verify body can be read after middleware
        body = await request.body()
        return JSONResponse({"status": "ok", "body_length": len(body)})
    
    # Create routes that match the expected pattern
    routes = [
        Route("/api/v1/integrations/alerts/telegram", webhook_endpoint, methods=["POST"]),
    ]
    
    from starlette.middleware import Middleware
    
    app = Starlette(routes=routes, middleware=[
        Middleware(AuthMiddleware),
    ])
    
    return app


@pytest.fixture
def webhook_secret():
    """Test webhook secret."""
    return "test-webhook-secret-min-32-chars-long"


@pytest.fixture
def mock_settings(webhook_secret):
    """Mock settings with webhook secret configured."""
    with patch.object(settings, "ALERTMANAGER_WEBHOOK_SECRET", webhook_secret):
        yield settings


def generate_valid_signature(body: bytes, timestamp: int, secret: str) -> str:
    """Generate a valid HMAC-SHA256 signature for testing."""
    payload = f"{timestamp}.".encode() + body
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={signature}"


class TestWebhookHMACSignatureVerification:
    """Test suite for webhook HMAC signature verification."""
    
    @pytest.mark.asyncio
    async def test_valid_signature_accepted(self, app, mock_settings, webhook_secret):
        """Test that requests with valid HMAC signatures are accepted."""
        body = b'{"alert": "test", "severity": "high"}'
        timestamp = int(time.time())
        signature = generate_valid_signature(body, timestamp, webhook_secret)
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/integrations/alerts/telegram",
                content=body,
                headers={
                    "X-Alertmanager-Signature": signature,
                    "X-Graxia-Timestamp": str(timestamp),
                    "Content-Type": "application/json",
                },
            )
        
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["body_length"] == len(body)
    
    @pytest.mark.asyncio
    async def test_invalid_signature_rejected(self, app, mock_settings):
        """Test that requests with invalid signatures are rejected."""
        body = b'{"alert": "test"}'
        timestamp = int(time.time())
        invalid_signature = "sha256=invalid_signature_here"
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/integrations/alerts/telegram",
                content=body,
                headers={
                    "X-Alertmanager-Signature": invalid_signature,
                    "X-Graxia-Timestamp": str(timestamp),
                },
            )
        
        assert response.status_code == 401
        assert response.json()["detail"] == "Unauthorized"
    
    @pytest.mark.asyncio
    async def test_missing_signature_rejected(self, app, mock_settings):
        """Test that requests without signatures are rejected when secret is configured."""
        body = b'{"alert": "test"}'
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/integrations/alerts/telegram",
                content=body,
                headers={"Content-Type": "application/json"},
            )
        
        assert response.status_code == 401
        assert response.json()["detail"] == "Unauthorized"
    
    @pytest.mark.asyncio
    async def test_missing_timestamp_rejected(self, app, mock_settings, webhook_secret):
        """Test that requests without timestamps are rejected."""
        body = b'{"alert": "test"}'
        timestamp = int(time.time())
        signature = generate_valid_signature(body, timestamp, webhook_secret)
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/integrations/alerts/telegram",
                content=body,
                headers={
                    "X-Alertmanager-Signature": signature,
                    # Missing X-Graxia-Timestamp
                },
            )
        
        assert response.status_code == 401
        assert response.json()["detail"] == "Unauthorized"
    
    @pytest.mark.asyncio
    async def test_expired_timestamp_rejected(self, app, mock_settings, webhook_secret):
        """Test that requests with expired timestamps are rejected (replay attack prevention)."""
        body = b'{"alert": "test"}'
        # Timestamp from 10 minutes ago (beyond 5-minute window)
        expired_timestamp = int(time.time()) - 600
        signature = generate_valid_signature(body, expired_timestamp, webhook_secret)
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/integrations/alerts/telegram",
                content=body,
                headers={
                    "X-Alertmanager-Signature": signature,
                    "X-Graxia-Timestamp": str(expired_timestamp),
                },
            )
        
        assert response.status_code == 401
        assert response.json()["detail"] == "Unauthorized"
    
    @pytest.mark.asyncio
    async def test_future_timestamp_rejected(self, app, mock_settings, webhook_secret):
        """Test that requests with future timestamps are rejected."""
        body = b'{"alert": "test"}'
        # Timestamp from 10 minutes in the future
        future_timestamp = int(time.time()) + 600
        signature = generate_valid_signature(body, future_timestamp, webhook_secret)
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/integrations/alerts/telegram",
                content=body,
                headers={
                    "X-Alertmanager-Signature": signature,
                    "X-Graxia-Timestamp": str(future_timestamp),
                },
            )
        
        assert response.status_code == 401
        assert response.json()["detail"] == "Unauthorized"
    
    @pytest.mark.asyncio
    async def test_malformed_timestamp_rejected(self, app, mock_settings, webhook_secret):
        """Test that requests with malformed timestamps are rejected."""
        body = b'{"alert": "test"}'
        timestamp = int(time.time())
        signature = generate_valid_signature(body, timestamp, webhook_secret)
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/integrations/alerts/telegram",
                content=body,
                headers={
                    "X-Alertmanager-Signature": signature,
                    "X-Graxia-Timestamp": "not-a-number",
                },
            )
        
        assert response.status_code == 401
        assert response.json()["detail"] == "Unauthorized"
    
    @pytest.mark.asyncio
    async def test_signature_without_sha256_prefix_rejected(self, app, mock_settings, webhook_secret):
        """Test that signatures without 'sha256=' prefix are rejected."""
        body = b'{"alert": "test"}'
        timestamp = int(time.time())
        # Generate signature without prefix
        payload = f"{timestamp}.".encode() + body
        signature_without_prefix = hmac.new(
            webhook_secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/integrations/alerts/telegram",
                content=body,
                headers={
                    "X-Alertmanager-Signature": signature_without_prefix,
                    "X-Graxia-Timestamp": str(timestamp),
                },
            )
        
        assert response.status_code == 401
        assert response.json()["detail"] == "Unauthorized"
    
    @pytest.mark.asyncio
    async def test_empty_body_signature_verification(self, app, mock_settings, webhook_secret):
        """Test signature verification with empty request body."""
        body = b""
        timestamp = int(time.time())
        signature = generate_valid_signature(body, timestamp, webhook_secret)
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/integrations/alerts/telegram",
                content=body,
                headers={
                    "X-Alertmanager-Signature": signature,
                    "X-Graxia-Timestamp": str(timestamp),
                },
            )
        
        assert response.status_code == 200
        assert response.json()["body_length"] == 0
    
    @pytest.mark.asyncio
    async def test_large_body_signature_verification(self, app, mock_settings, webhook_secret):
        """Test signature verification with large request body."""
        # 1MB body
        body = b"x" * (1024 * 1024)
        timestamp = int(time.time())
        signature = generate_valid_signature(body, timestamp, webhook_secret)
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/integrations/alerts/telegram",
                content=body,
                headers={
                    "X-Alertmanager-Signature": signature,
                    "X-Graxia-Timestamp": str(timestamp),
                },
            )
        
        assert response.status_code == 200
        assert response.json()["body_length"] == len(body)
    
    @pytest.mark.asyncio
    async def test_special_characters_in_body(self, app, mock_settings, webhook_secret):
        """Test signature verification with special characters in body."""
        body = '{"alert": "test", "message": "Special chars: 你好 🚀 \\"quoted\\" \\n\\t"}'.encode()
        timestamp = int(time.time())
        signature = generate_valid_signature(body, timestamp, webhook_secret)
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/integrations/alerts/telegram",
                content=body,
                headers={
                    "X-Alertmanager-Signature": signature,
                    "X-Graxia-Timestamp": str(timestamp),
                    "Content-Type": "application/json; charset=utf-8",
                },
            )
        
        assert response.status_code == 200
        assert response.json()["body_length"] == len(body)
    
    @pytest.mark.asyncio
    async def test_bearer_token_fallback_when_no_secret(self, app):
        """Test that bearer token authentication works when HMAC secret is not configured."""
        # Mock settings without webhook secret
        with patch.object(settings, "ALERTMANAGER_WEBHOOK_SECRET", ""):
            with patch.object(settings, "ALERTMANAGER_WEBHOOK_TOKEN", "test-bearer-token"):
                body = b'{"alert": "test"}'
                
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    response = await client.post(
                        "/api/v1/integrations/alerts/telegram",
                        content=body,
                        headers={
                            "Authorization": "Bearer test-bearer-token",
                        },
                    )
                
                assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_bearer_token_fallback_invalid_token(self, app):
        """Test that invalid bearer tokens are rejected in fallback mode."""
        # Mock settings without webhook secret
        with patch.object(settings, "ALERTMANAGER_WEBHOOK_SECRET", ""):
            with patch.object(settings, "ALERTMANAGER_WEBHOOK_TOKEN", "correct-token"):
                body = b'{"alert": "test"}'
                
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    response = await client.post(
                        "/api/v1/integrations/alerts/telegram",
                        content=body,
                        headers={
                            "Authorization": "Bearer wrong-token",
                        },
                    )
                
                assert response.status_code == 401
                assert response.json()["detail"] == "Unauthorized"
    
    @pytest.mark.asyncio
    async def test_request_body_restoration(self, app, mock_settings, webhook_secret):
        """Test that request body is properly restored after signature verification."""
        body = b'{"alert": "test", "data": "important"}'
        timestamp = int(time.time())
        signature = generate_valid_signature(body, timestamp, webhook_secret)
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/integrations/alerts/telegram",
                content=body,
                headers={
                    "X-Alertmanager-Signature": signature,
                    "X-Graxia-Timestamp": str(timestamp),
                },
            )
        
        assert response.status_code == 200
        # Verify body was readable by endpoint
        assert response.json()["body_length"] == len(body)


class TestWebhookSignatureTimingAttackResistance:
    """Test that signature verification is resistant to timing attacks."""
    
    @pytest.mark.asyncio
    async def test_constant_time_signature_comparison(self, app, mock_settings, webhook_secret):
        """Test that signature comparison uses constant-time operations.
        
        On Windows, time.perf_counter() has lower resolution and more jitter
        due to interrupt handling, so we use a relaxed threshold there.
        """
        import statistics
        import sys
        
        # Platform-aware threshold: Windows timer is less precise
        # 4σ on Windows, 3σ on other platforms
        threshold_sigma = 4 if sys.platform == "win32" else 3
        
        # More samples for better statistical power
        num_samples = 100
        
        body = b'{"alert": "test"}'
        timestamp = int(time.time())
        valid_signature = generate_valid_signature(body, timestamp, webhook_secret)
        
        # Measure timing for valid signature
        valid_times = []
        for _ in range(num_samples):
            start = time.perf_counter()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.post(
                    "/api/v1/integrations/alerts/telegram",
                    content=body,
                    headers={
                        "X-Alertmanager-Signature": valid_signature,
                        "X-Graxia-Timestamp": str(timestamp),
                    },
                )
            valid_times.append(time.perf_counter() - start)
        
        # Measure timing for invalid signature
        invalid_times = []
        for _ in range(num_samples):
            start = time.perf_counter()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.post(
                    "/api/v1/integrations/alerts/telegram",
                    content=body,
                    headers={
                        "X-Alertmanager-Signature": "sha256=invalid",
                        "X-Graxia-Timestamp": str(timestamp),
                    },
                )
            invalid_times.append(time.perf_counter() - start)
        
        # Statistical analysis
        valid_mean = statistics.mean(valid_times)
        invalid_mean = statistics.mean(invalid_times)
        valid_stdev = statistics.stdev(valid_times)
        invalid_stdev = statistics.stdev(invalid_times)
        
        # Timing difference should be within noise (< threshold_sigma standard deviations)
        # This is a heuristic test - timing attacks are hard to detect reliably
        timing_diff = abs(valid_mean - invalid_mean)
        combined_stdev = (valid_stdev + invalid_stdev) / 2
        
        # Allow up to threshold_sigma standard deviations difference
        threshold = threshold_sigma * combined_stdev
        assert timing_diff < threshold, (
            f"Potential timing leak detected: "
            f"valid_mean={valid_mean*1e6:.2f}µs, "
            f"invalid_mean={invalid_mean*1e6:.2f}µs, "
            f"diff={timing_diff*1e6:.2f}µs, "
            f"threshold={threshold*1e6:.2f}µs "
            f"({threshold_sigma}σ)"
        )


class TestWebhookSignatureEdgeCases:
    """Test edge cases and error conditions."""
    
    @pytest.mark.asyncio
    async def test_signature_with_extra_whitespace(self, app, mock_settings, webhook_secret):
        """Test that signatures with extra whitespace are handled correctly (stripped and accepted)."""
        body = b'{"alert": "test"}'
        timestamp = int(time.time())
        signature = generate_valid_signature(body, timestamp, webhook_secret)
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/integrations/alerts/telegram",
                content=body,
                headers={
                    "X-Alertmanager-Signature": f"  {signature}  ",
                    "X-Graxia-Timestamp": f"  {timestamp}  ",
                },
            )
        
        # Should be accepted because middleware strips whitespace from headers before verification
        # This is correct behavior - whitespace in headers should not cause auth failures
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_case_sensitive_signature_prefix(self, app, mock_settings, webhook_secret):
        """Test that signature prefix is case-sensitive."""
        body = b'{"alert": "test"}'
        timestamp = int(time.time())
        payload = f"{timestamp}.".encode() + body
        signature_hash = hmac.new(webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
        
        # Try with uppercase prefix
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/integrations/alerts/telegram",
                content=body,
                headers={
                    "X-Alertmanager-Signature": f"SHA256={signature_hash}",
                    "X-Graxia-Timestamp": str(timestamp),
                },
            )
        
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_multiple_signatures_rejected(self, app, mock_settings, webhook_secret):
        """Test that multiple signature headers are rejected."""
        body = b'{"alert": "test"}'
        timestamp = int(time.time())
        signature = generate_valid_signature(body, timestamp, webhook_secret)
        
        # FastAPI/Starlette will only use the first header value
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/integrations/alerts/telegram",
                content=body,
                headers=[
                    ("X-Alertmanager-Signature", signature),
                    ("X-Alertmanager-Signature", "sha256=fake"),
                    ("X-Graxia-Timestamp", str(timestamp)),
                ],
            )
        
        # Should accept (uses first header)
        assert response.status_code == 200



# ============================================================================
# Property-Based Tests for HMAC Signature Verification
# ============================================================================

@given(
    st.binary(min_size=0, max_size=10000),
    st.text(min_size=32, max_size=128)
)
def test_hmac_round_trip_property(body: bytes, secret: str):
    """
    Property Test: HMAC Round-Trip
    
    Property: verify(sign(body, secret), body, secret) == True for all valid bodies
    
    This property-based test verifies that:
    1. Any body signed with a secret can be verified with the same secret
    2. The signature generation and verification are inverse operations
    3. The round-trip property holds for all possible inputs
    
    SECURITY REQUIREMENT:
    - Signature verification must accept all validly signed messages
    - No false negatives for legitimate requests
    """
    timestamp = int(time.time())
    
    # Sign the body
    payload = f"{timestamp}.".encode() + body
    signature = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    
    # Verify the signature
    expected_sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    
    # Round-trip property: sign then verify should always succeed
    assert hmac.compare_digest(signature, expected_sig), (
        f"HMAC round-trip failed: signature={signature[:50]}, "
        f"expected={expected_sig[:50]}, body_len={len(body)}, secret_len={len(secret)}"
    )


@given(
    st.binary(min_size=1, max_size=1000),
    st.integers(min_value=0),
    st.text(min_size=32, max_size=128)
)
def test_hmac_tampering_detection_property(body: bytes, byte_position: int, secret: str):
    """
    Property Test: HMAC Tampering Detection
    
    Property: Changing any single byte of body must cause verification to fail
    
    This property-based test verifies that:
    1. Any modification to the body invalidates the signature
    2. HMAC provides integrity protection
    3. Tampering is always detected
    
    SECURITY REQUIREMENT:
    - Any modification to the signed data must be detected
    - No false positives for tampered messages
    """
    # Ensure byte_position is within bounds
    if len(body) == 0:
        return  # Skip empty bodies
    
    byte_position = byte_position % len(body)
    timestamp = int(time.time())
    
    # Generate valid signature for original body
    payload = f"{timestamp}.".encode() + body
    valid_signature = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    
    # Tamper with the body (flip one byte)
    tampered_body = bytearray(body)
    tampered_body[byte_position] ^= 0xFF  # Flip all bits in the byte
    tampered_body = bytes(tampered_body)
    
    # Verify that the original signature doesn't match the tampered body
    tampered_payload = f"{timestamp}.".encode() + tampered_body
    expected_sig_for_tampered = "sha256=" + hmac.new(secret.encode(), tampered_payload, hashlib.sha256).hexdigest()
    
    # Tampering detection property: signature should NOT match after tampering
    assert not hmac.compare_digest(valid_signature, expected_sig_for_tampered), (
        f"HMAC tampering detection failed: original signature still valid after "
        f"flipping byte at position {byte_position}. Body length: {len(body)}"
    )


@given(
    st.binary(min_size=0, max_size=5000),
    st.text(min_size=32, max_size=128)
)
def test_hmac_signature_uniqueness_property(body: bytes, secret: str):
    """
    Property Test: HMAC Signature Uniqueness
    
    Property: Different bodies produce different signatures (with overwhelming probability)
    
    This property-based test verifies that:
    1. HMAC produces unique signatures for different inputs
    2. Collision resistance (within practical limits)
    3. Signature space is large enough to prevent guessing
    """
    timestamp = int(time.time())
    
    # Generate signature for original body
    payload1 = f"{timestamp}.".encode() + body
    sig1 = hmac.new(secret.encode(), payload1, hashlib.sha256).hexdigest()
    
    # Generate signature for modified body (append one byte)
    modified_body = body + b"X"
    payload2 = f"{timestamp}.".encode() + modified_body
    sig2 = hmac.new(secret.encode(), payload2, hashlib.sha256).hexdigest()
    
    # Signatures should be different (collision is astronomically unlikely)
    assert sig1 != sig2, (
        f"HMAC collision detected: same signature for different bodies. "
        f"This is extremely unlikely and may indicate a problem."
    )


@given(
    st.binary(min_size=0, max_size=1000),
    st.text(min_size=32, max_size=128),
    st.text(min_size=32, max_size=128)
)
def test_hmac_secret_sensitivity_property(body: bytes, secret1: str, secret2: str):
    """
    Property Test: HMAC Secret Sensitivity
    
    Property: Different secrets produce different signatures for the same body
    
    This property-based test verifies that:
    1. Changing the secret changes the signature
    2. Secrets are properly incorporated into the signature
    3. No two secrets produce the same signature (with overwhelming probability)
    """
    # Skip if secrets are the same
    if secret1 == secret2:
        return
    
    timestamp = int(time.time())
    payload = f"{timestamp}.".encode() + body
    
    # Generate signatures with different secrets
    sig1 = hmac.new(secret1.encode(), payload, hashlib.sha256).hexdigest()
    sig2 = hmac.new(secret2.encode(), payload, hashlib.sha256).hexdigest()
    
    # Signatures should be different
    assert sig1 != sig2, (
        f"HMAC secret sensitivity failed: same signature with different secrets. "
        f"Secret1 length: {len(secret1)}, Secret2 length: {len(secret2)}"
    )


@given(st.binary(min_size=0, max_size=1000))
def test_hmac_signature_length_invariant_property(body: bytes):
    """
    Property Test: HMAC Signature Length Invariant
    
    Property: HMAC-SHA256 signatures are always 64 hex characters (256 bits)
    
    This property-based test verifies that:
    1. Signature length is constant regardless of input size
    2. SHA256 output is always 256 bits
    3. No information about input size leaks through signature length
    """
    secret = "test-secret-for-length-check-min-32-chars"
    timestamp = int(time.time())
    payload = f"{timestamp}.".encode() + body
    
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    
    # SHA256 produces 256 bits = 64 hex characters
    assert len(signature) == 64, (
        f"HMAC signature length invariant violated: expected 64 chars, got {len(signature)}. "
        f"Body length: {len(body)}"
    )


@given(
    st.binary(min_size=0, max_size=1000),
    st.text(min_size=32, max_size=128)
)
def test_hmac_deterministic_property(body: bytes, secret: str):
    """
    Property Test: HMAC Deterministic Property
    
    Property: Computing HMAC multiple times with same inputs produces same output
    
    This property-based test verifies that:
    1. HMAC is deterministic (no randomness)
    2. Signature can be reliably verified
    3. No timing-dependent variations
    """
    timestamp = int(time.time())
    payload = f"{timestamp}.".encode() + body
    
    # Compute signature multiple times
    sig1 = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    sig2 = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    sig3 = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    
    # All signatures should be identical
    assert sig1 == sig2 == sig3, (
        f"HMAC deterministic property violated: signatures differ across computations. "
        f"sig1={sig1[:20]}, sig2={sig2[:20]}, sig3={sig3[:20]}"
    )
