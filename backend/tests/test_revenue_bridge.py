from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models.funnel import ConversionEvent

try:
    from app.api.revenue_bridge import ingest_revenue_event
    from app.models.revenue_bridge import RevenueBridgeEvent
    from app.schemas.revenue_bridge import RevenueBridgeEventEnvelope
    from app.services.revenue_bridge_service import (
        RevenueBridgeService,
        canonical_event_payload,
    )
    _BRIDGE_IMPORT_ERROR: Exception | None = None
except ImportError as exc:  # Keep RED phase as an assertion failure, not collection error.
    ingest_revenue_event = None
    RevenueBridgeEvent = None
    RevenueBridgeEventEnvelope = None
    RevenueBridgeService = None
    canonical_event_payload = None
    _BRIDGE_IMPORT_ERROR = exc


SECRET = "revenue-bridge-test-secret"


def _require_bridge():
    if _BRIDGE_IMPORT_ERROR is not None:
        pytest.fail(f"Revenue bridge is not implemented: {_BRIDGE_IMPORT_ERROR}")


def _envelope(
    *,
    event_kind: str = "subscription_activated",
    event_id: str | None = None,
    organization_id=None,
):
    _require_bridge()
    unsigned = RevenueBridgeEventEnvelope(
        provider="test-provider",
        provider_event_id=event_id or f"evt_{uuid4().hex}",
        organization_id=organization_id or uuid4(),
        event_kind=event_kind,
        plan="growth",
        amount=Decimal("990.00"),
        currency="THB",
        occurred_at=datetime(2026, 9, 19, 7, 0, tzinfo=UTC),
        signature="pending",
    )
    signature = hmac.new(
        SECRET.encode(),
        canonical_event_payload(unsigned).encode(),
        hashlib.sha256,
    ).hexdigest()
    return unsigned.model_copy(update={"signature": signature})


@pytest.mark.asyncio
async def test_valid_hmac_is_verified_before_event_persisted(db_session, default_org):
    _require_bridge()
    event = _envelope(organization_id=default_org.id)

    result = await RevenueBridgeService(hmac_secret=SECRET).ingest(event, db_session)

    assert result["verified"] is True
    persisted = await db_session.scalar(
        select(RevenueBridgeEvent).where(
            RevenueBridgeEvent.provider_event_id == event.provider_event_id
        )
    )
    assert persisted is not None
    assert persisted.signature_verified is True


@pytest.mark.asyncio
async def test_duplicate_provider_event_is_a_noop(db_session, default_org):
    _require_bridge()
    event = _envelope(event_id="evt_duplicate", organization_id=default_org.id)
    service = RevenueBridgeService(hmac_secret=SECRET)

    first = await service.ingest(event, db_session)
    second = await service.ingest(event, db_session)

    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert await db_session.scalar(select(func.count(RevenueBridgeEvent.id))) == 1


@pytest.mark.asyncio
async def test_invalid_signature_is_rejected_by_api_before_persist(db_session, default_org):
    _require_bridge()
    event = _envelope(
        organization_id=default_org.id,
    ).model_copy(update={"signature": "invalid"})

    with pytest.raises(HTTPException) as exc_info:
        await ingest_revenue_event(event, db_session)

    assert exc_info.value.status_code == 401
    assert await db_session.scalar(select(func.count(RevenueBridgeEvent.id))) == 0


@pytest.mark.asyncio
async def test_only_verified_subscription_activation_emits_purchase_event(
    db_session, default_org
):
    _require_bridge()
    service = RevenueBridgeService(hmac_secret=SECRET)

    for event_kind in (
        "subscription_activated",
        "subscription_cancelled",
        "payment_failed",
        "refund",
    ):
        event = _envelope(
            event_kind=event_kind,
            organization_id=default_org.id,
        )
        await service.ingest(event, db_session)

    purchases = await db_session.scalars(
        select(ConversionEvent).where(ConversionEvent.event_type == "purchase")
    )
    purchase_rows = list(purchases)
    assert len(purchase_rows) == 1
    assert purchase_rows[0].metadata_json["provider_event_id"]

    statuses = await db_session.scalars(select(RevenueBridgeEvent.normalized_status))
    assert sorted(statuses.all()) == ["active", "canceled", "past_due", "refunded"]
