import base64
import hashlib
import hmac
import json
from typing import Any

from app.config import settings


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def _b64decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8"))


def _secret_bytes() -> bytes:
    secret = (settings.TRACKING_SIGNING_SECRET or settings.CSRF_SIGNING_SECRET or "").encode("utf-8")
    return secret


def sign_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str).encode("utf-8")
    body = _b64encode(raw)
    sig = hmac.new(_secret_bytes(), body.encode("utf-8"), hashlib.sha256).digest()
    return f"{body}.{_b64encode(sig)}"


def verify_token(token: str) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    body, sig = token.split(".", 1)
    expected = hmac.new(_secret_bytes(), body.encode("utf-8"), hashlib.sha256).digest()
    try:
        provided = _b64decode(sig)
    except Exception:
        return None
    if not hmac.compare_digest(expected, provided):
        return None
    try:
        payload = json.loads(_b64decode(body))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None

