"""Authentication module — JWT verification + API key auth.

Replaces the previous stub `HTTPBearer()` that accepted any token without
verification.  All sensitive endpoints (orders, risk, positions, admin)
must use ``Depends(verify_jwt)`` or ``Depends(verify_admin)``.

Two auth modes:
  1. JWT (HS256) — bearer token in ``Authorization: Bearer <token>``
  2. Admin API key — ``X-Admin-Key`` header, constant-time compare

Both modes fail-closed: if the secret is not configured, reject.
"""

from __future__ import annotations

import hmac
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..core.config import get_config

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


def create_access_token(
    subject: str,
    expires_seconds: int = 3600,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Issue a signed JWT for ``subject`` (user/service id).

    Uses HS256 with ``JWT_SECRET_KEY`` from config.  Raises if the
    secret is empty (fail-closed — never issue unsigned tokens).
    """
    config = get_config()
    secret = config.jwt_secret_key
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY not configured — cannot issue token")

    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_seconds)).timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_jwt(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> dict[str, Any]:
    """Verify a Bearer JWT and return decoded claims.

    Fail-closed:
      - Missing header → 401
      - Empty JWT_SECRET_KEY → 500 (misconfiguration)
      - Expired / invalid signature / malformed → 401
    """
    config = get_config()
    secret = config.jwt_secret_key
    if not secret:
        logger.error("auth.verify_jwt: JWT_SECRET_KEY not configured — fail-closed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT secret not configured",
        )

    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        logger.warning("auth.verify_jwt: invalid token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return claims


def verify_admin_key(api_key: str, expected_key: str) -> None:
    """Constant-time API key comparison. Raises HTTPException on failure.

    Shared helper used by ``verify_admin`` and ``verify_api_key``.
    Fail-closed: empty expected → 500, missing/invalid key → 401.
    """
    if not expected_key:
        logger.error("auth.verify_admin_key: key not configured — fail-closed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key not configured",
        )
    if not api_key or not hmac.compare_digest(api_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin key",
        )


def verify_admin(
    api_key: str = Header(..., alias="X-Admin-Key"),
) -> bool:
    """Verify admin API key — constant-time comparison.

    Fail-closed: empty configured key → 500, missing/invalid header → 401.
    """
    config = get_config()
    verify_admin_key(api_key, config.admin_api_key)
    return True


def verify_api_key(
    api_key: str = Header(..., alias="X-API-Key"),
) -> bool:
    """Verify generic API key (for webhook/manual signal endpoints).

    Constant-time compare against ADMIN_API_KEY.  Fail-closed.
    """
    config = get_config()
    verify_admin_key(api_key, config.admin_api_key)
    return True
