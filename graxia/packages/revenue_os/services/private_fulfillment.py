"""Pure contracts for private digital fulfillment.

This module deliberately performs no database or provider I/O.  It turns a
validated private object reference into an expiring application URL and keeps
the storage resolver behind an explicit fail-closed boundary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Protocol
from urllib.parse import urlsplit

from .signed_download_service import SignedDownloadError, SignedDownloadService


class PrivateFulfillmentError(ValueError):
    """Raised when a private fulfillment reference is unsafe or unavailable."""


_TOKEN = re.compile(r"^[A-Za-z0-9._~-]{1,4096}$")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


def validate_private_object_key(value: str) -> str:
    """Validate and return a relative object-storage key.

    The key is never treated as a URL or filesystem path by this module.  The
    stricter checks prevent path confusion when an adapter later maps it to a
    provider-specific object reference.
    """

    if not isinstance(value, str) or not value or value != value.strip():
        raise PrivateFulfillmentError("private object key is invalid")
    if len(value) > 1024 or value.startswith(("/", "\\")):
        raise PrivateFulfillmentError("private object key is invalid")
    if _WINDOWS_DRIVE.match(value) or "://" in value or "\\" in value:
        raise PrivateFulfillmentError("private object key is invalid")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise PrivateFulfillmentError("private object key is invalid")
    if any(segment in {"", ".", ".."} for segment in value.split("/")):
        raise PrivateFulfillmentError("private object key is invalid")
    if re.search(r"%2e|%2f|%5c", value, flags=re.IGNORECASE):
        raise PrivateFulfillmentError("private object key is invalid")
    return value


def private_object_key_from_metadata(metadata: object) -> str:
    """Read the only supported private object reference from product metadata."""

    if not isinstance(metadata, Mapping):
        raise PrivateFulfillmentError("private object key is not configured")
    value = metadata.get("private_object_key")
    if not isinstance(value, str):
        raise PrivateFulfillmentError("private object key is not configured")
    return validate_private_object_key(value)


def build_download_url(public_base_url: str, token: str, *, app_env: str = "development") -> str:
    """Build an application download URL without accepting provider URLs."""

    if not isinstance(public_base_url, str):
        raise PrivateFulfillmentError("public app base URL is invalid")
    parsed = urlsplit(public_base_url.strip())
    environment = (app_env or "development").lower()
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PrivateFulfillmentError("public app base URL is invalid")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise PrivateFulfillmentError("public app base URL is invalid")
    if environment in {"staging", "production"} and parsed.scheme != "https":
        raise PrivateFulfillmentError("public app base URL must use HTTPS")
    if not isinstance(token, str) or not _TOKEN.fullmatch(token):
        raise PrivateFulfillmentError("download token is invalid")
    base = public_base_url.strip().rstrip("/")
    return f"{base}/api/v1/delivery/download/{token}"


def issue_download_token(
    signer: SignedDownloadService,
    *,
    entitlement_id: str,
    product_key: str,
    metadata: object,
    ttl_seconds: int = 24 * 60 * 60,
    now: int | None = None,
) -> str:
    """Issue an opaque token after validating the private object reference."""

    object_key = private_object_key_from_metadata(metadata)
    try:
        return signer.issue(
            entitlement_id=entitlement_id,
            product_key=product_key,
            object_key=object_key,
            ttl_seconds=ttl_seconds,
            now=now,
        )
    except SignedDownloadError as exc:
        raise PrivateFulfillmentError("private download token could not be issued") from exc


def build_private_fulfillment_url(
    signer: SignedDownloadService,
    *,
    public_base_url: str,
    app_env: str,
    entitlement_id: str,
    product_key: str,
    metadata: object,
    ttl_seconds: int = 24 * 60 * 60,
    now: int | None = None,
) -> str:
    """Issue a token and bind it to the application download route."""

    token = issue_download_token(
        signer,
        entitlement_id=entitlement_id,
        product_key=product_key,
        metadata=metadata,
        ttl_seconds=ttl_seconds,
        now=now,
    )
    return build_download_url(public_base_url, token, app_env=app_env)


class PrivateObjectResolver(Protocol):
    """Provider boundary; implementations must not expose object keys."""

    def resolve(self, object_key: str, *, expires_at: int) -> str:
        """Return an opaque provider handle or URL for the validated object."""


@dataclass(frozen=True)
class MissingPrivateObjectResolver:
    """Default resolver used until a private storage adapter is configured."""

    def resolve(self, object_key: str, *, expires_at: int) -> str:
        validate_private_object_key(object_key)
        raise PrivateFulfillmentError("private object storage is not configured")


@dataclass(frozen=True)
class StaticPrivateObjectResolver:
    """Deterministic non-I/O resolver for unit tests only."""

    handles: Mapping[str, str]

    def resolve(self, object_key: str, *, expires_at: int) -> str:
        key = validate_private_object_key(object_key)
        handle = self.handles.get(key)
        if not isinstance(handle, str) or not handle:
            raise PrivateFulfillmentError("private object is unavailable")
        return handle
