"""
graxia/services/revenue_os_api/routers/delivery.py
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import UUID
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....packages.revenue_os.db import get_db
from ....packages.revenue_os.models import DeliveryEvent, Entitlement, Product
from ....packages.revenue_os.schemas import DeliveryEventResponse
from ....packages.revenue_os.services.private_fulfillment import (
    PrivateFulfillmentError,
    PrivateObjectResolver,
    private_object_key_from_metadata,
)
from ....packages.revenue_os.services.private_object_storage import (
    private_object_resolver_from_environment,
)
from ....packages.revenue_os.services.signed_download_service import (
    SignedDownloadError,
    SignedDownloadService,
)
from ..dependencies import require_admin_api_key

router = APIRouter()


def get_private_object_resolver() -> PrivateObjectResolver:
    """Return configured storage signing or a resolver that fails closed."""

    return private_object_resolver_from_environment()


def _download_not_found() -> HTTPException:
    """Use one indistinguishable response for invalid/private references."""

    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Download not found")


def _entitlement_is_active(entitlement: Entitlement) -> bool:
    if entitlement.revoked_at is not None:
        return False
    if entitlement.expires_at is None:
        return True
    expires_at = entitlement.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > datetime.now(timezone.utc)


def _configured_signer() -> SignedDownloadService:
    """Build the signer at request time so rotation needs no process restart."""

    return SignedDownloadService(os.getenv("REVENUE_OS_DOWNLOAD_SIGNING_SECRET", ""))


@router.get(
    "/download/{token}",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    response_class=RedirectResponse,
    summary="Resolve a private digital download",
)
async def download_private_object(
    token: str,
    db: AsyncSession = Depends(get_db),
    resolver: PrivateObjectResolver = Depends(get_private_object_resolver),
) -> RedirectResponse:
    """Resolve an entitlement-bound token to a short-lived private URL.

    The route intentionally reveals neither whether an entitlement exists nor
    whether storage is configured.  Storage adapters must return an opaque
    HTTPS URL; object keys never appear in the response.
    """

    try:
        signer = _configured_signer()
    except SignedDownloadError:
        raise HTTPException(status_code=503, detail="Private fulfillment unavailable")

    try:
        payload = signer.verify(token)
        entitlement_id = UUID(str(payload["entitlement_id"]))
        entitlement = await db.get(Entitlement, entitlement_id)
        if entitlement is None or not _entitlement_is_active(entitlement):
            raise _download_not_found()
        product_key = str(payload["product_key"])
        if entitlement.product_key != product_key:
            raise _download_not_found()
        product = await db.scalar(select(Product).where(Product.slug == product_key))
        if product is None:
            raise _download_not_found()
        object_key = private_object_key_from_metadata(product.metadata_)
    except HTTPException:
        raise
    except (ValueError, KeyError, TypeError, SignedDownloadError, PrivateFulfillmentError):
        raise _download_not_found()

    try:
        provider_url = resolver.resolve(
            object_key,
            expires_at=int(payload["exp"]),
        )
    except PrivateFulfillmentError:
        raise HTTPException(status_code=503, detail="Private fulfillment unavailable")

    if not isinstance(provider_url, str):
        raise HTTPException(status_code=503, detail="Private fulfillment unavailable")
    parsed = urlsplit(provider_url)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        raise HTTPException(status_code=503, detail="Private fulfillment unavailable")
    return RedirectResponse(url=provider_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get(
    "/",
    response_model=list[DeliveryEventResponse],
    dependencies=[Depends(require_admin_api_key)],
)
async def list_delivery_events(
    order_id: UUID | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[DeliveryEventResponse]:
    stmt = select(DeliveryEvent)
    if order_id:
        stmt = stmt.where(DeliveryEvent.order_id == order_id)
    if status_filter:
        stmt = stmt.where(DeliveryEvent.status == status_filter)
    result = await db.scalars(
        stmt.order_by(DeliveryEvent.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [DeliveryEventResponse.model_validate(d) for d in result]


@router.get(
    "/{delivery_id}",
    response_model=DeliveryEventResponse,
    dependencies=[Depends(require_admin_api_key)],
)
async def get_delivery_event(
    delivery_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> DeliveryEventResponse:
    event = await db.get(DeliveryEvent, delivery_id)
    if not event:
        raise HTTPException(status_code=404, detail="Delivery event not found")
    return DeliveryEventResponse.model_validate(event)
