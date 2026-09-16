import re

import pytest

from ..services.private_fulfillment import PrivateFulfillmentError
from ..services.private_object_storage import (
    MissingPrivateObjectResolver,
    PrivateObjectStorageError,
    S3PresignedPrivateObjectResolver,
    private_object_resolver_from_environment,
)


def _resolver():
    return S3PresignedPrivateObjectResolver(
        endpoint_url="https://objects.example.test",
        bucket="private-assets",
        access_key_id="access-key",
        secret_access_key="secret-key-for-test-only",
        region="auto",
    )


def test_presigner_builds_s3_compatible_url_without_network():
    url = _resolver()._presign(
        "products/prompt-pack.zip", expires=300, now=1700000000
    )
    assert url.startswith("https://objects.example.test/private-assets/products/prompt-pack.zip?")
    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in url
    assert "X-Amz-Signature=" in url
    assert re.search(r"X-Amz-Signature=[0-9a-f]{64}", url)


def test_resolve_never_extends_token_expiry():
    resolver = _resolver()
    with pytest.raises(PrivateFulfillmentError, match="expired"):
        resolver.resolve("products/file.zip", expires_at=99)


def test_storage_configuration_is_fail_closed_when_incomplete():
    resolver = private_object_resolver_from_environment(
        {"REVENUE_OS_PRIVATE_STORAGE_ENDPOINT": "https://objects.example.test"}
    )
    assert isinstance(resolver, MissingPrivateObjectResolver)
    with pytest.raises(PrivateFulfillmentError, match="not configured"):
        resolver.resolve("products/file.zip", expires_at=200)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"endpoint_url": "http://objects.example.test"},
        {"endpoint_url": "https://objects.example.test", "bucket": "../bad"},
    ],
)
def test_storage_configuration_rejects_unsafe_values(kwargs):
    values = {
        "endpoint_url": "https://objects.example.test",
        "bucket": "private-assets",
        "access_key_id": "access-key",
        "secret_access_key": "secret-key-for-test-only",
        "region": "auto",
    }
    values.update(kwargs)
    with pytest.raises(PrivateObjectStorageError):
        S3PresignedPrivateObjectResolver(**values)

