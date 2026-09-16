"""Short-lived signed references for private digital fulfillment objects."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any


class SignedDownloadError(ValueError):
    """Raised for invalid or unsafe download references."""


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}$")


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _private_object_key(value: str) -> str:
    value = value.strip()
    if (
        not value
        or value.startswith("/")
        or "://" in value
        or ".." in value.split("/")
        or any(ord(char) < 32 for char in value)
    ):
        raise SignedDownloadError("object_key must be a relative private-storage key")
    return value


def _secret(value: str | None) -> bytes:
    candidate = (value or os.getenv("REVENUE_OS_DOWNLOAD_SIGNING_SECRET", "")).encode()
    if len(candidate) < 32:
        raise SignedDownloadError("download signing secret is not configured")
    return candidate


@dataclass(frozen=True)
class SignedDownloadService:
    """Issue and verify opaque, expiring references without provider calls."""

    signing_secret: str
    max_ttl_seconds: int = 7 * 24 * 60 * 60

    def __post_init__(self) -> None:
        _secret(self.signing_secret)
        if not 1 <= self.max_ttl_seconds <= 30 * 24 * 60 * 60:
            raise SignedDownloadError("max_ttl_seconds is outside the safe range")

    def issue(
        self,
        *,
        entitlement_id: str,
        product_key: str,
        object_key: str,
        ttl_seconds: int = 24 * 60 * 60,
        now: int | None = None,
    ) -> str:
        if not _SAFE_ID.fullmatch(entitlement_id) or not _SAFE_ID.fullmatch(product_key):
            raise SignedDownloadError("entitlement_id and product_key must be safe identifiers")
        if not 1 <= ttl_seconds <= self.max_ttl_seconds:
            raise SignedDownloadError("ttl_seconds is outside the safe range")
        issued_at = int(time.time() if now is None else now)
        payload = {
            "v": 1,
            "entitlement_id": entitlement_id,
            "product_key": product_key,
            "object_key": _private_object_key(object_key),
            "iat": issued_at,
            "exp": issued_at + ttl_seconds,
        }
        encoded = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
        signature = hmac.new(_secret(self.signing_secret), encoded.encode(), hashlib.sha256).digest()
        return encoded + "." + _b64(signature)

    def verify(self, token: str, *, now: int | None = None) -> dict[str, Any]:
        if not isinstance(token, str) or token.count(".") != 1:
            raise SignedDownloadError("invalid signed download token")
        encoded, supplied_signature = token.split(".", 1)
        expected_signature = hmac.new(
            _secret(self.signing_secret), encoded.encode(), hashlib.sha256
        ).digest()
        try:
            valid_signature = hmac.compare_digest(_unb64(supplied_signature), expected_signature)
            payload = json.loads(_unb64(encoded))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise SignedDownloadError("invalid signed download token") from exc
        if not valid_signature or not isinstance(payload, dict) or payload.get("v") != 1:
            raise SignedDownloadError("invalid signed download token")
        current = int(time.time() if now is None else now)
        if not isinstance(payload.get("exp"), int) or payload["exp"] < current:
            raise SignedDownloadError("signed download token expired")
        if not _SAFE_ID.fullmatch(str(payload.get("entitlement_id", ""))):
            raise SignedDownloadError("invalid entitlement reference")
        if not _SAFE_ID.fullmatch(str(payload.get("product_key", ""))):
            raise SignedDownloadError("invalid product reference")
        _private_object_key(str(payload.get("object_key", "")))
        return payload
