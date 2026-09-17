"""S3-compatible presigned URLs for private digital fulfillment.

The resolver signs a GET request locally and performs no provider I/O.  It is
compatible with S3-style endpoints, including S3-compatible object stores.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping
from urllib.parse import quote, urlsplit

from .private_fulfillment import (
    MissingPrivateObjectResolver,
    PrivateFulfillmentError,
    PrivateObjectResolver,
    validate_private_object_key,
)


class PrivateObjectStorageError(PrivateFulfillmentError):
    """Raised when private storage configuration cannot sign a download."""


_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{0,255}$")
_MAX_PRESIGN_SECONDS = 7 * 24 * 60 * 60


def _hmac(key: bytes, value: str) -> bytes:
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).digest()


def _aws_encode(value: str) -> str:
    return quote(value, safe="-_.~")


@dataclass(frozen=True)
class S3PresignedPrivateObjectResolver:
    """Generate short-lived private GET URLs without contacting storage."""

    endpoint_url: str
    bucket: str
    access_key_id: str
    secret_access_key: str
    region: str = "auto"
    max_expires_seconds: int = 15 * 60

    def __post_init__(self) -> None:
        parsed = urlsplit(self.endpoint_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise PrivateObjectStorageError("private storage endpoint must use HTTPS")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise PrivateObjectStorageError("private storage endpoint is invalid")
        if not _SAFE_COMPONENT.fullmatch(self.bucket or ""):
            raise PrivateObjectStorageError("private storage bucket is invalid")
        if not _SAFE_COMPONENT.fullmatch(self.region or ""):
            raise PrivateObjectStorageError("private storage region is invalid")
        if not self.access_key_id or not self.secret_access_key:
            raise PrivateObjectStorageError("private storage credentials are not configured")
        if not 1 <= self.max_expires_seconds <= _MAX_PRESIGN_SECONDS:
            raise PrivateObjectStorageError("private storage expiry is invalid")

    def resolve(self, object_key: str, *, expires_at: int) -> str:
        key = validate_private_object_key(object_key)
        now = int(time.time())
        remaining = int(expires_at) - now
        if remaining < 1:
            raise PrivateObjectStorageError("private download has expired")
        return self._presign(key, min(remaining, self.max_expires_seconds), now=now)

    def _presign(self, object_key: str, expires: int, *, now: int) -> str:
        endpoint = urlsplit(self.endpoint_url)
        request_time = datetime.fromtimestamp(now, tz=timezone.utc)
        short_date = request_time.strftime("%Y%m%d")
        amz_date = request_time.strftime("%Y%m%dT%H%M%SZ")
        host = endpoint.netloc
        base_path = endpoint.path.rstrip("/")
        canonical_uri = (
            f"{base_path}/{_aws_encode(self.bucket)}/"
            f"{quote(object_key, safe='/-_.~')}" if base_path else
            f"/{_aws_encode(self.bucket)}/{quote(object_key, safe='/-_.~')}"
        )
        credential = (
            f"{self.access_key_id}/{short_date}/{self.region}/s3/aws4_request"
        )
        query: Mapping[str, str] = {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
            "X-Amz-Credential": credential,
            "X-Amz-Date": amz_date,
            "X-Amz-Expires": str(expires),
            "X-Amz-SignedHeaders": "host",
        }
        canonical_query = "&".join(
            f"{_aws_encode(key)}={_aws_encode(query[key])}"
            for key in sorted(query)
        )
        canonical_headers = f"host:{host}\n"
        canonical_request = "\n".join(
            [
                "GET",
                canonical_uri,
                canonical_query,
                canonical_headers,
                "host",
                "UNSIGNED-PAYLOAD",
            ]
        )
        scope = f"{short_date}/{self.region}/s3/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        date_key = _hmac(("AWS4" + self.secret_access_key).encode("utf-8"), short_date)
        region_key = _hmac(date_key, self.region)
        service_key = _hmac(region_key, "s3")
        signing_key = _hmac(service_key, "aws4_request")
        signature = hmac.new(
            signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return f"{self.endpoint_url.rstrip('/')}{canonical_uri}?{canonical_query}&X-Amz-Signature={signature}"


def private_object_resolver_from_environment(
    env: Mapping[str, str] | None = None,
) -> PrivateObjectResolver:
    """Build a resolver or return the fail-closed resolver when incomplete."""

    values = env if env is not None else os.environ
    endpoint = values.get("REVENUE_OS_PRIVATE_STORAGE_ENDPOINT", "")
    bucket = values.get("REVENUE_OS_PRIVATE_STORAGE_BUCKET", "")
    access_key = values.get("REVENUE_OS_PRIVATE_STORAGE_ACCESS_KEY", "")
    secret_key = values.get("REVENUE_OS_PRIVATE_STORAGE_SECRET_KEY", "")
    region = values.get("REVENUE_OS_PRIVATE_STORAGE_REGION", "auto")
    if not all((endpoint, bucket, access_key, secret_key)):
        return MissingPrivateObjectResolver()
    return S3PresignedPrivateObjectResolver(
        endpoint_url=endpoint,
        bucket=bucket,
        access_key_id=access_key,
        secret_access_key=secret_key,
        region=region,
    )
