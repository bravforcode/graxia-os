from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from graxia.services.revenue_os_api.routers.delivery import download_private_object
from ..services.private_fulfillment import issue_download_token
from ..services.private_fulfillment import MissingPrivateObjectResolver, StaticPrivateObjectResolver
from ..services.signed_download_service import SignedDownloadService


SECRET = "d" * 48


class FakeDB:
    def __init__(self, entitlement, product):
        self.entitlement = entitlement
        self.product = product

    async def get(self, model, identifier):
        return self.entitlement

    async def scalar(self, statement):
        return self.product


def _fixture(monkeypatch, *, revoked_at=None, expires_at=None, product_key="prompt-pack"):
    monkeypatch.setenv("REVENUE_OS_DOWNLOAD_SIGNING_SECRET", SECRET)
    entitlement_id = uuid4()
    product = SimpleNamespace(
        slug="prompt-pack",
        metadata_={"private_object_key": "products/prompt-pack.zip"},
    )
    entitlement = SimpleNamespace(
        id=entitlement_id,
        product_key=product_key,
        revoked_at=revoked_at,
        expires_at=expires_at,
    )
    token = issue_download_token(
        SignedDownloadService(SECRET),
        entitlement_id=str(entitlement_id),
        product_key="prompt-pack",
        metadata=product.metadata_,
    )
    return token, FakeDB(entitlement, product)


@pytest.mark.asyncio
async def test_download_route_redirects_only_to_https_provider_url(monkeypatch):
    token, db = _fixture(monkeypatch)
    response = await download_private_object(
        token,
        db=db,
        resolver=StaticPrivateObjectResolver(
            {"products/prompt-pack.zip": "https://objects.example.test/signed"}
        ),
    )
    assert response.status_code == 307
    assert response.headers["location"] == "https://objects.example.test/signed"


@pytest.mark.asyncio
async def test_download_route_fails_closed_when_storage_is_missing(monkeypatch):
    token, db = _fixture(monkeypatch)
    with pytest.raises(HTTPException) as error:
        await download_private_object(
            token,
            db=db,
            resolver=MissingPrivateObjectResolver(),
        )
    assert error.value.status_code == 503
    assert "prompt-pack.zip" not in str(error.value.detail)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"revoked_at": datetime.now(timezone.utc)},
        {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)},
        {"product_key": "different-product"},
    ],
)
async def test_download_route_hides_inactive_or_mismatched_entitlements(monkeypatch, kwargs):
    token, db = _fixture(monkeypatch, **kwargs)
    with pytest.raises(HTTPException) as error:
        await download_private_object(
            token,
            db=db,
            resolver=StaticPrivateObjectResolver(
                {"products/prompt-pack.zip": "https://objects.example.test/signed"}
            ),
        )
    assert error.value.status_code == 404
    assert error.value.detail == "Download not found"
