"""
Tests for JWT Authentication module.

Covers token creation, verification, expiration, role-based access,
and FastAPI dependency behaviour. Uses a test-only secret key.
"""

from __future__ import annotations

import os
import time

# Set test secret BEFORE any imports that touch the auth module
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-do-not-use-in-production"
os.environ["SKIP_AUTH"] = "false"  # Ensure auth is active for these tests

import jwt
import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from graxia.packages.quant_os.api.auth import (
    ALGORITHM,
    DEFAULT_EXPIRY_SECONDS,
    TokenPayload,
    create_access_token,
    get_current_user,
    require_admin,
    verify_token,
)

TEST_SECRET = "test-jwt-secret-do-not-use-in-production"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_app():
    """Build a minimal FastAPI app with protected and admin-only routes."""
    app = FastAPI()

    @app.get("/public")
    async def public_route():
        return {"status": "ok"}

    @app.get("/protected")
    async def protected_route(user: TokenPayload = Depends(get_current_user)):
        return {"sub": user.sub, "role": user.role}

    @app.get("/admin-only")
    async def admin_route(user: TokenPayload = Depends(require_admin)):
        return {"sub": user.sub, "role": user.role}

    return app


@pytest.fixture
def client(auth_app):
    """TestClient with auth enabled (SKIP_AUTH=false)."""
    return TestClient(auth_app)


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------


class TestTokenCreation:
    def test_create_user_token(self):
        token = create_access_token(sub="alice", role="user", secret_key=TEST_SECRET)
        assert isinstance(token, str)
        assert len(token) > 20

    def test_create_admin_token(self):
        token = create_access_token(sub="admin1", role="admin", secret_key=TEST_SECRET)
        payload = jwt.decode(token, TEST_SECRET, algorithms=[ALGORITHM])
        assert payload["role"] == "admin"
        assert payload["sub"] == "admin1"

    def test_token_contains_required_claims(self):
        token = create_access_token(sub="bob", role="user", secret_key=TEST_SECRET)
        payload = jwt.decode(token, TEST_SECRET, algorithms=[ALGORITHM])
        assert "sub" in payload
        assert "role" in payload
        assert "iat" in payload
        assert "exp" in payload

    def test_custom_expiry(self):
        token = create_access_token(sub="carol", role="user", expires_in=300, secret_key=TEST_SECRET)
        payload = jwt.decode(token, TEST_SECRET, algorithms=[ALGORITHM])
        assert payload["exp"] - payload["iat"] == 300

    def test_default_expiry_is_24h(self):
        token = create_access_token(sub="dave", secret_key=TEST_SECRET)
        payload = jwt.decode(token, TEST_SECRET, algorithms=[ALGORITHM])
        assert payload["exp"] - payload["iat"] == DEFAULT_EXPIRY_SECONDS


# ---------------------------------------------------------------------------
# Token verification
# ---------------------------------------------------------------------------


class TestTokenVerification:
    def test_valid_token(self):
        token = create_access_token(sub="alice", role="user", secret_key=TEST_SECRET)
        result = verify_token(token, secret_key=TEST_SECRET)
        assert result.sub == "alice"
        assert result.role == "user"

    def test_expired_token_rejected(self):
        # Create a token that expired 10 seconds ago
        now = int(time.time())
        payload = {
            "sub": "eve",
            "role": "user",
            "iat": now - 200,
            "exp": now - 10,
        }
        token = jwt.encode(payload, TEST_SECRET, algorithm=ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            verify_token(token, secret_key=TEST_SECRET)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_wrong_secret_rejected(self):
        token = create_access_token(sub="alice", role="user", secret_key=TEST_SECRET)
        with pytest.raises(HTTPException) as exc_info:
            verify_token(token, secret_key="wrong-secret-key")
        assert exc_info.value.status_code == 401
        assert "invalid" in exc_info.value.detail.lower()

    def test_tampered_payload_rejected(self):
        token = create_access_token(sub="alice", role="user", secret_key=TEST_SECRET)
        # Tamper with the token by changing a character
        parts = token.split(".")
        # Flip a byte in the payload
        payload_bytes = parts[1].encode()
        tampered = payload_bytes[:-1] + (b"A" if payload_bytes[-1:] != b"A" else b"B")
        tampered_token = parts[0] + "." + tampered.decode() + "." + parts[2]

        with pytest.raises(HTTPException) as exc_info:
            verify_token(tampered_token, secret_key=TEST_SECRET)
        assert exc_info.value.status_code == 401

    def test_empty_token_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            verify_token("", secret_key=TEST_SECRET)
        assert exc_info.value.status_code == 401

    def test_missing_sub_claim(self):
        now = int(time.time())
        payload = {"role": "user", "iat": now, "exp": now + 3600}
        token = jwt.encode(payload, TEST_SECRET, algorithm=ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            verify_token(token, secret_key=TEST_SECRET)
        assert exc_info.value.status_code == 401
        assert "claims" in exc_info.value.detail.lower()

    def test_missing_role_claim(self):
        now = int(time.time())
        payload = {"sub": "alice", "iat": now, "exp": now + 3600}
        token = jwt.encode(payload, TEST_SECRET, algorithm=ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            verify_token(token, secret_key=TEST_SECRET)
        assert exc_info.value.status_code == 401
        assert "claims" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# FastAPI dependency — protected routes
# ---------------------------------------------------------------------------


class TestProtectedRoutes:
    def test_no_token_returns_401(self, client):
        resp = client.get("/protected")
        assert resp.status_code == 401

    def test_valid_user_token(self, client):
        token = create_access_token(sub="alice", role="user", secret_key=TEST_SECRET)
        resp = client.get("/protected", headers=_auth_header(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["sub"] == "alice"
        assert data["role"] == "user"

    def test_expired_token_returns_401(self, client):
        now = int(time.time())
        payload = {"sub": "bob", "role": "user", "iat": now - 200, "exp": now - 10}
        token = jwt.encode(payload, TEST_SECRET, algorithm=ALGORITHM)
        resp = client.get("/protected", headers=_auth_header(token))
        assert resp.status_code == 401

    def test_wrong_secret_returns_401(self, client):
        token = create_access_token(sub="alice", role="user", secret_key="wrong-key")
        resp = client.get("/protected", headers=_auth_header(token))
        assert resp.status_code == 401

    def test_malformed_header_returns_401(self, client):
        resp = client.get("/protected", headers={"Authorization": "NotBearer xyz"})
        assert resp.status_code == 401

    def test_public_route_no_auth_needed(self, client):
        resp = client.get("/public")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# FastAPI dependency — admin routes
# ---------------------------------------------------------------------------


class TestAdminRoutes:
    def test_no_token_returns_401(self, client):
        resp = client.get("/admin-only")
        assert resp.status_code == 401

    def test_user_role_returns_403(self, client):
        token = create_access_token(sub="alice", role="user", secret_key=TEST_SECRET)
        resp = client.get("/admin-only", headers=_auth_header(token))
        assert resp.status_code == 403
        assert "admin" in resp.json()["detail"].lower()

    def test_admin_role_allowed(self, client):
        token = create_access_token(sub="admin1", role="admin", secret_key=TEST_SECRET)
        resp = client.get("/admin-only", headers=_auth_header(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["sub"] == "admin1"
        assert data["role"] == "admin"

    def test_expired_admin_token_returns_401(self, client):
        now = int(time.time())
        payload = {"sub": "admin1", "role": "admin", "iat": now - 200, "exp": now - 10}
        token = jwt.encode(payload, TEST_SECRET, algorithm=ALGORITHM)
        resp = client.get("/admin-only", headers=_auth_header(token))
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Token payload model
# ---------------------------------------------------------------------------


class TestTokenPayload:
    def test_payload_fields(self):
        payload = TokenPayload(sub="alice", role="user", iat=1000, exp=2000)
        assert payload.sub == "alice"
        assert payload.role == "user"
        assert payload.iat == 1000
        assert payload.exp == 2000

    def test_payload_dict_roundtrip(self):
        payload = TokenPayload(sub="bob", role="admin", iat=100, exp=200)
        d = payload.model_dump()
        restored = TokenPayload(**d)
        assert restored == payload


# ---------------------------------------------------------------------------
# Role-based access edge cases
# ---------------------------------------------------------------------------


class TestRoleEdgeCases:
    def test_unknown_role_rejected_by_admin(self, client):
        token = create_access_token(sub="hacker", role="superadmin", secret_key=TEST_SECRET)
        resp = client.get("/admin-only", headers=_auth_header(token))
        assert resp.status_code == 403

    def test_empty_role_rejected(self, client):
        now = int(time.time())
        payload = {"sub": "alice", "role": "", "iat": now, "exp": now + 3600}
        token = jwt.encode(payload, TEST_SECRET, algorithm=ALGORITHM)
        resp = client.get("/protected", headers=_auth_header(token))
        # Empty role fails the "required claims" check
        assert resp.status_code == 401
