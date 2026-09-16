import pytest

from ..services.signed_download_service import SignedDownloadError, SignedDownloadService


SECRET = "test-download-signing-secret-0123456789"


def test_issue_and_verify_signed_private_reference():
    service = SignedDownloadService(SECRET)

    token = service.issue(
        entitlement_id="entitlement-1",
        product_key="01-prompt-pack-th",
        object_key="aifactory/01-prompt-pack-th/v1.zip",
        ttl_seconds=60,
        now=100,
    )

    payload = service.verify(token, now=120)
    assert payload["entitlement_id"] == "entitlement-1"
    assert payload["object_key"] == "aifactory/01-prompt-pack-th/v1.zip"


def test_expired_or_tampered_token_is_rejected():
    service = SignedDownloadService(SECRET)
    token = service.issue(
        entitlement_id="entitlement-1",
        product_key="product-1",
        object_key="private/product-1.zip",
        ttl_seconds=10,
        now=100,
    )

    with pytest.raises(SignedDownloadError, match="expired"):
        service.verify(token, now=111)
    with pytest.raises(SignedDownloadError, match="invalid"):
        service.verify(token[:-1] + ("A" if token[-1] != "A" else "B"), now=101)


def test_public_url_and_weak_secret_are_rejected():
    with pytest.raises(SignedDownloadError, match="secret"):
        SignedDownloadService("too-short")

    service = SignedDownloadService(SECRET)
    with pytest.raises(SignedDownloadError, match="private-storage"):
        service.issue(
            entitlement_id="entitlement-1",
            product_key="product-1",
            object_key="https://public.example/download.zip",
        )
