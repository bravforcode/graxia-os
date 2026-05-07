"""Canonical authentication helpers."""
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from fastapi import HTTPException, status
from jwt.exceptions import PyJWTError
from passlib.context import CryptContext

from app.config import settings

ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def hash_password(password: str) -> str:
    return get_password_hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def _token_expiry(token_type: str, expires_delta: timedelta | None = None) -> datetime:
    if expires_delta is not None:
        return datetime.now(UTC) + expires_delta
    if token_type == "refresh":
        return datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)


def extract_bearer_token(authorization_header: str | None) -> str | None:
    if not authorization_header:
        return None
    prefix = "Bearer "
    if not authorization_header.startswith(prefix):
        return None
    token = authorization_header[len(prefix) :].strip()
    return token or None


def _encode_token(data: dict[str, Any], token_type: str, expires_delta: timedelta | None = None) -> str:
    now = datetime.now(UTC)
    payload = data.copy()
    payload.update(
        {
            "iat": now,
            "exp": _token_expiry(token_type, expires_delta),
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
            "type": token_type,
        }
    )
    headers = {"kid": settings.JWT_ACTIVE_KID}
    return jwt.encode(payload, settings.ACTIVE_JWT_SIGNING_KEY, algorithm=ALGORITHM, headers=headers)


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    return _encode_token(data, "access", expires_delta)


def create_refresh_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    return _encode_token(data, "refresh", expires_delta)


def decode_token(token: str) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
    except PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    kid = header.get("kid", settings.JWT_ACTIVE_KID)
    signing_key = settings.JWT_KEYSET.get(str(kid))
    if not signing_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token signed with an unknown key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    options = {
        "verify_signature": True,
        "verify_exp": True,
        "verify_aud": bool(settings.JWT_AUDIENCE),
        "verify_iss": bool(settings.JWT_ISSUER),
    }
    kwargs: dict[str, Any] = {"algorithms": [ALGORITHM], "options": options}
    if settings.JWT_AUDIENCE:
        kwargs["audience"] = settings.JWT_AUDIENCE
    if settings.JWT_ISSUER:
        kwargs["issuer"] = settings.JWT_ISSUER

    try:
        return jwt.decode(token, signing_key, **kwargs)
    except PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def decode_access_token(token: str) -> dict[str, Any]:
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def decode_refresh_token(token: str) -> dict[str, Any]:
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def parse_subject_uuid(subject: str) -> UUID:
    try:
        return UUID(str(subject))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
