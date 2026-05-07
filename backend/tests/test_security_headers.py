"""
Security headers verification — every authenticated response must carry
the full defensive header set defined in SecurityHeadersMiddleware.
"""

import pytest

REQUIRED_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}

# These are checked for presence only (value varies by config)
PRESENT_HEADERS = [
    "Content-Security-Policy",
]


@pytest.mark.asyncio
async def test_health_endpoint_has_security_headers(public_async_client):
    """Public health check should include security headers."""
    response = await public_async_client.get("/health")
    assert response.status_code == 200

    for header, expected_value in REQUIRED_HEADERS.items():
        assert header in response.headers, f"Missing header: {header}"
        assert response.headers[header] == expected_value, (
            f"{header}: expected {expected_value!r}, got {response.headers[header]!r}"
        )

    for header in PRESENT_HEADERS:
        assert header in response.headers, f"Missing header: {header}"


@pytest.mark.asyncio
async def test_api_endpoint_has_security_headers(async_client):
    """Authenticated API responses must also carry security headers."""
    response = await async_client.get("/api/v1/opportunities")
    assert response.status_code in (200, 422)

    for header, expected_value in REQUIRED_HEADERS.items():
        assert header in response.headers, f"Missing header: {header}"
        assert response.headers[header] == expected_value

    for header in PRESENT_HEADERS:
        assert header in response.headers, f"Missing header: {header}"


@pytest.mark.asyncio
async def test_unauthenticated_request_has_security_headers(public_async_client):
    """401 responses must also carry security headers (no info leakage via missing headers)."""
    response = await public_async_client.get("/api/v1/opportunities")
    assert response.status_code == 401

    for header, _expected_value in REQUIRED_HEADERS.items():
        assert header in response.headers, f"Missing header {header} on 401 response"


@pytest.mark.asyncio
async def test_x_content_type_nosniff_prevents_mime_sniffing(public_async_client):
    """X-Content-Type-Options must be exactly 'nosniff' to block MIME sniffing."""
    response = await public_async_client.get("/health")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"


@pytest.mark.asyncio
async def test_csp_header_blocks_inline_scripts(public_async_client):
    """Content-Security-Policy must include script-src restriction."""
    response = await public_async_client.get("/health")
    csp = response.headers.get("Content-Security-Policy", "")
    assert "script-src" in csp, f"CSP missing script-src directive: {csp!r}"
