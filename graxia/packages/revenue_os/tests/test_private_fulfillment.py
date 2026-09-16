import pytest

from ..services.private_fulfillment import (
    MissingPrivateObjectResolver,
    PrivateFulfillmentError,
    StaticPrivateObjectResolver,
    build_download_url,
    issue_download_token,
    private_object_key_from_metadata,
    validate_private_object_key,
)
from ..services.signed_download_service import SignedDownloadService


SECRET = "x" * 48


@pytest.mark.parametrize(
    "value",
    [
        "products/prompt-pack.zip",
        "products/v1/readme.pdf",
    ],
)
def test_private_object_key_accepts_relative_keys(value):
    assert validate_private_object_key(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "/products/file.zip",
        "C:/products/file.zip",
        "products/../file.zip",
        "products//file.zip",
        "https://storage.example/file.zip",
        "products/%2e%2e/file.zip",
        "products/file.zip\n",
    ],
)
def test_private_object_key_rejects_unsafe_values(value):
    with pytest.raises(PrivateFulfillmentError, match="invalid"):
        validate_private_object_key(value)


def test_metadata_requires_private_object_key_without_leaking_value():
    with pytest.raises(PrivateFulfillmentError) as error:
        private_object_key_from_metadata({"fulfillment_url": "https://public.example/file"})
    assert "public.example" not in str(error.value)


def test_download_url_requires_https_for_staging():
    with pytest.raises(PrivateFulfillmentError, match="HTTPS"):
        build_download_url("http://staging.example", "abc.def", app_env="staging")
    assert build_download_url(
        "https://staging.example/", "abc.def", app_env="staging"
    ) == "https://staging.example/api/v1/delivery/download/abc.def"


def test_issue_download_token_reuses_signed_service():
    signer = SignedDownloadService(SECRET)
    token = issue_download_token(
        signer,
        entitlement_id="entitlement-1",
        product_key="prompt-pack",
        metadata={"private_object_key": "products/prompt-pack.zip"},
        now=100,
    )
    payload = signer.verify(token, now=100)
    assert payload["object_key"] == "products/prompt-pack.zip"
    assert payload["entitlement_id"] == "entitlement-1"


def test_missing_resolver_fails_closed_without_disclosing_key():
    with pytest.raises(PrivateFulfillmentError, match="not configured") as error:
        MissingPrivateObjectResolver().resolve(
            "products/prompt-pack.zip", expires_at=200
        )
    assert "prompt-pack" not in str(error.value)


def test_static_resolver_is_deterministic_without_io():
    resolver = StaticPrivateObjectResolver(
        {"products/prompt-pack.zip": "provider-handle-for-test"}
    )
    assert resolver.resolve("products/prompt-pack.zip", expires_at=200) == (
        "provider-handle-for-test"
    )

