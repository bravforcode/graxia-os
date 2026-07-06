"""
JWT Authentication for Quant OS API

Provides token creation, verification, and FastAPI dependencies
for route protection with role-based access control.

Route classification:
  Public:  /health, /, /status, /docs, /openapi.json, /api/metrics
  User:    all trading, portfolio, risk, TV, visual, CDP endpoints
  Admin:   /api/v1/admin/* (requires admin role in JWT)

Security:
  - Secret key from JWT_SECRET_KEY env var (never hardcoded)
  - HS256 signing algorithm
  - 24-hour token expiry (configurable)
  - Constant-time secret comparison via PyJWT internals
  - SKIP_AUTH env var for test/dev bypass (never enable in production)
"""

from __future__ import annotations

import os
import time
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ALGORITHM = "HS256"
DEFAULT_EXPIRY_SECONDS = 86400  # 24 hours

# Test/dev bypass — set SKIP_AUTH=true to disable authentication.
# MUST NOT be enabled in production deployments.
_SKIP_AUTH: bool = os.environ.get("SKIP_AUTH", "").lower() in ("1", "true", "yes")

# Reusable security scheme (auto_error=False so we handle 401 ourselves)
_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Token models
# ---------------------------------------------------------------------------


class TokenPayload(BaseModel):
    """Decoded JWT payload."""

    sub: str  # User identifier
    role: str  # "user" or "admin"
    iat: int  # Issued at (epoch seconds)
    exp: int  # Expiry (epoch seconds)


class TokenResponse(BaseModel):
    """Response from the token endpoint."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str


# ---------------------------------------------------------------------------
# Secret key resolution
# ---------------------------------------------------------------------------


def _resolve_secret_key() -> str:
    """Resolve JWT secret key from environment or QuantConfig.

    Priority: JWT_SECRET_KEY env var > config.jwt_secret_key.
    Raises RuntimeError if neither is set (fail-closed).
    Never logs or exposes the secret value.
    """
    # 1. Direct env var (fastest path, no config import needed)
    key = os.environ.get("JWT_SECRET_KEY", "")
    if key:
        return key

    # 2. Fall back to QuantConfig
    try:
        from ..core.config import get_config

        config = get_config()
        if config.jwt_secret_key:
            return config.jwt_secret_key
    except Exception:
        pass

    raise RuntimeError("JWT secret key not configured. " "Set the JWT_SECRET_KEY environment variable.")


# ---------------------------------------------------------------------------
# Token operations
# ---------------------------------------------------------------------------


def create_access_token(
    sub: str,
    role: str = "user",
    expires_in: int = DEFAULT_EXPIRY_SECONDS,
    secret_key: str | None = None,
) -> str:
    """Create a signed JWT access token.

    Args:
        sub: Subject (user identifier).
        role: User role — "user" or "admin".
        expires_in: Token lifetime in seconds (default 24h).
        secret_key: Override for testing (bypasses _resolve_secret_key).

    Returns:
        Encoded JWT string.
    """
    now = int(time.time())
    payload = {
        "sub": sub,
        "role": role,
        "iat": now,
        "exp": now + expires_in,
    }
    key = secret_key or _resolve_secret_key()
    return jwt.encode(payload, key, algorithm=ALGORITHM)


def verify_token(token: str, secret_key: str | None = None) -> TokenPayload:
    """Verify and decode a JWT token.

    Validates: signature, expiry, required claims (sub, role).
    Raises HTTPException 401 on any failure.
    """
    key = secret_key or _resolve_secret_key()

    try:
        payload_dict = jwt.decode(token, key, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate required claims
    sub = payload_dict.get("sub")
    role = payload_dict.get("role")
    if not sub or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing required claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenPayload(
        sub=sub,
        role=role,
        iat=payload_dict.get("iat", 0),
        exp=payload_dict.get("exp", 0),
    )


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)] = None,
) -> TokenPayload:
    """FastAPI dependency: extract and validate JWT from Bearer header.

    Returns TokenPayload on success, raises 401 otherwise.
    In SKIP_AUTH mode, returns a default admin user (testing only).
    """
    if _SKIP_AUTH:
        return TokenPayload(
            sub="dev_user",
            role="admin",
            iat=int(time.time()),
            exp=int(time.time()) + DEFAULT_EXPIRY_SECONDS,
        )

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return verify_token(credentials.credentials)


async def require_admin(
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> TokenPayload:
    """FastAPI dependency: require admin role.

    Chains after get_current_user. Raises 403 if role != "admin".
    """
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
