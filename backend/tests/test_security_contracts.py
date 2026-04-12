import pytest

from app.core.route_manifest import build_route_manifest
from app.middleware.auth import classify_route
from app.middleware.security import SECURITY_HEADERS


@pytest.mark.asyncio
async def test_protected_routes_require_authentication(public_async_client):
    response = await public_async_client.get("/api/v1/jobs")
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


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
    for header in ("Content-Security-Policy", "X-Frame-Options", "X-Content-Type-Options", "Referrer-Policy"):
        assert response.headers[header] == SECURITY_HEADERS[header]


def test_route_manifest_has_no_gaps():
    from app.main import app

    manifest = build_route_manifest(app)
    assert manifest["summary"]["gaps_found"] == 0
    assert any(route["path"] == "/api/v1/auth/login" and route["expected_auth"] == "public" for route in manifest["routes"])
    assert any(
        route["path"] == "/api/v1/system/health" and route["expected_auth"] == classify_route("GET", "/api/v1/system/health").value
        for route in manifest["routes"]
    )
