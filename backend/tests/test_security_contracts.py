import json
import logging
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from app.config import settings
from app.core.auth import create_access_token
from app.core.logging_config import JSONFormatter
from app.core.route_manifest import build_route_manifest
from app.middleware.auth import classify_route
from app.middleware.security import _get_security_headers


@pytest.mark.asyncio
async def test_protected_routes_require_authentication(public_async_client):
    response = await public_async_client.get("/api/v1/jobs")
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


@pytest.mark.asyncio
async def test_protected_routes_reject_expired_access_tokens(public_async_client):
    token = create_access_token(
        {"sub": "security-user", "role": "user"},
        expires_delta=timedelta(seconds=-1),
    )

    response = await public_async_client.get(
        "/api/v1/jobs",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"


@pytest.mark.asyncio
async def test_protected_routes_reject_forged_access_tokens(public_async_client):
    now = datetime.now(UTC)
    forged = jwt.encode(
        {
            "sub": "security-user",
            "role": "user",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
            "type": "access",
        },
        "wrong-signing-key-with-enough-length-for-hs256-tests",
        algorithm="HS256",
        headers={"kid": settings.JWT_ACTIVE_KID},
    )

    response = await public_async_client.get(
        "/api/v1/jobs",
        headers={"Authorization": f"Bearer {forged}"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"


@pytest.mark.asyncio
async def test_cookie_session_and_logout_contract(public_async_client):
    register_response = await public_async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "cookie-user@example.com",
            "password": "correct-horse-battery",
            "full_name": "Cookie User",
        },
    )
    assert register_response.status_code == 201
    assert public_async_client.cookies.get("access_token")
    assert public_async_client.cookies.get("refresh_token")
    assert public_async_client.cookies.get("csrf_token")

    me_response = await public_async_client.get("/api/v1/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "cookie-user@example.com"

    logout_response = await public_async_client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 200
    set_cookie = ",".join(logout_response.headers.get_list("set-cookie"))
    assert "Max-Age=0" in set_cookie


@pytest.mark.asyncio
async def test_csrf_is_enforced_for_state_changing_requests(async_client):
    original_csrf = async_client.headers.pop("X-CSRF-Token", None)
    try:
        response = await async_client.post(
            "/api/v1/tasks/",
            json={"title": "Missing CSRF", "priority": 5, "assigned_to": "user"},
        )
    finally:
        if original_csrf is not None:
            async_client.headers["X-CSRF-Token"] = original_csrf

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF token missing"


@pytest.mark.asyncio
async def test_security_headers_are_present(public_async_client):
    response = await public_async_client.get("/health")
    assert response.status_code == 200
    security_headers = _get_security_headers()
    for header in (
        "Content-Security-Policy",
        "X-Frame-Options",
        "X-Content-Type-Options",
        "Referrer-Policy",
    ):
        assert response.headers[header] == security_headers[header]


def test_route_manifest_has_no_gaps():
    from app.main import app

    manifest = build_route_manifest(app)
    assert manifest["summary"]["gaps_found"] == 0
    assert any(
        route["path"] == "/api/v1/auth/login" and route["expected_auth"] == "public"
        for route in manifest["routes"]
    )
    assert any(
        route["path"] == "/api/v1/auth/social-login" and route["expected_auth"] == "public"
        for route in manifest["routes"]
    )
    assert any(
        route["path"] == "/api/v1/system/health"
        and route["expected_auth"] == classify_route("GET", "/api/v1/system/health").value
        for route in manifest["routes"]
    )


def test_json_logs_redact_pii_and_secrets():
    record = logging.LogRecord(
        name="security-test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Login failed for jane.doe@example.com from +1 415-555-1212 token=secret-token-value",
        args=(),
        exc_info=None,
    )
    record.extra = {
        "email": "jane.doe@example.com",
        "headers": {"Authorization": "Bearer abc.def.secret"},
        "api_key": "sk-test-secret-value",
        "safe_field": "kept",
    }

    payload = json.loads(JSONFormatter().format(record))
    serialized = json.dumps(payload)

    assert "jane.doe@example.com" not in serialized
    assert "+1 415-555-1212" not in serialized
    assert "secret-token-value" not in serialized
    assert "abc.def.secret" not in serialized
    assert "sk-test-secret-value" not in serialized
    assert "[REDACTED_EMAIL]" in serialized
    assert payload["safe_field"] == "kept"
