"""Create and verify scoped proofs for marketing unsubscribe requests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlsplit
from uuid import UUID

import jwt
from jwt.exceptions import PyJWTError

from app.config import settings
from app.core.email_identity import normalize_email

UNSUBSCRIBE_TTL = timedelta(days=365)
UNSUBSCRIBE_PURPOSE = "marketing_unsubscribe"
UNSUBSCRIBE_ROUTE = "/api/v1/public/funnel/unsubscribe"


class UnsubscribeProofUnavailable(RuntimeError):
    """The configured signing keys cannot safely issue or verify a proof."""


class InvalidUnsubscribeProof(ValueError):
    """The proof is malformed, expired, or does not represent opt-out scope."""


def _configuration() -> tuple[str, str, dict[str, str]]:
    kid = (settings.JWT_ACTIVE_KID or "").strip()
    issuer = (settings.JWT_ISSUER or "").strip()
    audience = (settings.JWT_AUDIENCE or "").strip()
    if not kid or not issuer or not audience:
        raise UnsubscribeProofUnavailable("JWT signing configuration is incomplete")
    try:
        keyset = settings.JWT_KEYSET
    except (RuntimeError, TypeError, ValueError) as exc:
        raise UnsubscribeProofUnavailable("JWT signing keys are unavailable") from exc
    if not isinstance(keyset, dict) or not keyset:
        raise UnsubscribeProofUnavailable("JWT signing keys are unavailable")
    return kid, issuer, keyset


def _signing_key(kid: str) -> str:
    active_kid, _issuer, keyset = _configuration()
    if kid not in keyset:
        if kid == active_kid:
            raise UnsubscribeProofUnavailable("The active JWT signing key is missing")
        raise InvalidUnsubscribeProof("Unknown signing key")
    key = keyset[kid]
    if not isinstance(key, str) or len(key.encode("utf-8")) < 32:
        raise UnsubscribeProofUnavailable("The JWT signing key is not usable")
    return key


def create_unsubscribe_token(organization_id: UUID, email: str) -> str:
    kid, issuer, _keyset = _configuration()
    key = _signing_key(kid)
    try:
        normalized_email = normalize_email(email)
        organization_id = UUID(str(organization_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise InvalidUnsubscribeProof("Invalid unsubscribe scope") from exc
    if "@" not in normalized_email:
        raise InvalidUnsubscribeProof("Invalid unsubscribe email")

    now = datetime.now(UTC)
    payload = {
        "type": "unsubscribe",
        "purpose": UNSUBSCRIBE_PURPOSE,
        "organization_id": str(organization_id),
        "email": normalized_email,
        "iat": now,
        "exp": now + UNSUBSCRIBE_TTL,
        "iss": issuer,
        "aud": settings.JWT_AUDIENCE,
    }
    return jwt.encode(payload, key, algorithm="HS256", headers={"kid": kid})


def create_unsubscribe_url(organization_id: UUID, email: str) -> str:
    base_url = (settings.APP_BASE_URL or "").strip().rstrip("/")
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or (settings.APP_ENV.lower() == "production" and parsed.scheme != "https")
    ):
        raise UnsubscribeProofUnavailable("APP_BASE_URL is not a valid public URL")
    token = create_unsubscribe_token(organization_id, email)
    return f"{base_url}{UNSUBSCRIBE_ROUTE}?{urlencode({'token': token})}"


def verify_unsubscribe_token(token: str) -> tuple[UUID, str]:
    if not isinstance(token, str) or not token or len(token) > 4096:
        raise InvalidUnsubscribeProof("Invalid unsubscribe proof")
    try:
        header = jwt.get_unverified_header(token)
    except PyJWTError as exc:
        raise InvalidUnsubscribeProof("Invalid unsubscribe proof") from exc
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid or header.get("alg") != "HS256":
        raise InvalidUnsubscribeProof("Invalid unsubscribe proof")

    _active_kid, issuer, _keyset = _configuration()
    key = _signing_key(kid)
    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=["HS256"],
            audience=settings.JWT_AUDIENCE,
            issuer=issuer,
        )
    except PyJWTError as exc:
        raise InvalidUnsubscribeProof("Invalid or expired unsubscribe proof") from exc

    if (
        payload.get("type") != "unsubscribe"
        or payload.get("purpose") != UNSUBSCRIBE_PURPOSE
        or not payload.get("exp")
        or not payload.get("iat")
    ):
        raise InvalidUnsubscribeProof("Invalid unsubscribe proof scope")
    try:
        organization_id = UUID(str(payload["organization_id"]))
        email = normalize_email(payload["email"])
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise InvalidUnsubscribeProof("Invalid unsubscribe proof scope") from exc
    if "@" not in email:
        raise InvalidUnsubscribeProof("Invalid unsubscribe proof scope")
    return organization_id, email
