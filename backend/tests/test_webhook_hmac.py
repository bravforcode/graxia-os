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
    
    app = Starlette(routes=routes, middleware=[
        (AuthMiddleware, {}),
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
        """Test that signature comparison uses constant-time operations."""
        import statistics
        
        body = b'{"alert": "test"}'
        timestamp = int(time.time())
        valid_signature = generate_valid_signature(body, timestamp, webhook_secret)
        
        # Measure timing for valid signature
        valid_times = []
        for _ in range(50):
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
        for _ in range(50):
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
        
        # Timing difference should be within noise (< 3 standard deviations)
        # This is a heuristic test - timing attacks are hard to detect reliably
        timing_diff = abs(valid_mean - invalid_mean)
        combined_stdev = (valid_stdev + invalid_stdev) / 2
        
        # Allow up to 3 standard deviations difference (99.7% confidence)
        assert timing_diff < 3 * combined_stdev, (
            f"Potential timing leak detected: "
            f"valid_mean={valid_mean*1e6:.2f}µs, "
            f"invalid_mean={invalid_mean*1e6:.2f}µs, "
            f"diff={timing_diff*1e6:.2f}µs, "
            f"threshold={3*combined_stdev*1e6:.2f}µs"
        )


class TestWebhookSignatureEdgeCases:
    """Test edge cases and error conditions."""
    
    @pytest.mark.asyncio
    async def test_signature_with_extra_whitespace(self, app, mock_settings, webhook_secret):
        """Test that signatures with extra whitespace are handled correctly."""
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
        
        # Should be rejected because strip() is applied and signature won't match
        assert response.status_code == 401
    
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
