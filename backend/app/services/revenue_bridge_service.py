from __future__ import annotations

import hashlib
import hmac
from datetime import UTC
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.funnel import ConversionEvent
from app.models.revenue_bridge import RevenueBridgeEvent
from app.schemas.revenue_bridge import RevenueBridgeEventEnvelope
from app.config import settings


class InvalidRevenueBridgeSignature(ValueError):
    """Raised when provider evidence cannot be authenticated."""


class RevenueBridgeConflictError(ValueError):
    """Raised when an event ID is reused for different provider evidence."""


class RevenueBridgeDisabled(ValueError):
    """Raised when the verified bridge is paused by its feature flag."""


def canonical_event_payload(envelope: RevenueBridgeEventEnvelope) -> str:
    """Return the exact field order used for the bridge HMAC."""

    occurred_at = envelope.occurred_at.astimezone(UTC).isoformat(
        timespec="microseconds"
    )
    return "|".join(
        (
            envelope.provider,
            envelope.provider_event_id,
            str(envelope.organization_id),
            envelope.event_kind,
            envelope.plan,
            format(envelope.amount, "f"),
            envelope.currency,
            occurred_at,
        )
    )


def verify_hmac_signature(
    envelope: RevenueBridgeEventEnvelope, secret: str
) -> bool:
    """Verify a hex SHA-256 HMAC without accepting unauthenticated evidence."""

    if not secret:
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        canonical_event_payload(envelope).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    provided = envelope.signature.strip()
    if provided.startswith("sha256="):
        provided = provided.removeprefix("sha256=")
    return hmac.compare_digest(provided, expected)


def normalized_status_for_event(event_kind: str) -> str:
    return {
        "subscription_activated": "active",
        "subscription_cancelled": "canceled",
        "payment_failed": "past_due",
        "refund": "refunded",
    }[event_kind]


def _purchase_idempotency_key(envelope: RevenueBridgeEventEnvelope) -> str:
    digest = hashlib.sha256(
        f"{envelope.provider}:{envelope.provider_event_id}".encode("utf-8")
    ).hexdigest()
    return f"revenue-bridge-purchase:{digest}"


def _same_provider_event(
    existing: RevenueBridgeEvent, envelope: RevenueBridgeEventEnvelope
) -> bool:
    existing_occurred_at = existing.occurred_at
    if existing_occurred_at.tzinfo is None:
        existing_occurred_at = existing_occurred_at.replace(tzinfo=UTC)
    return (
        existing.organization_id == envelope.organization_id
        and existing.event_kind == envelope.event_kind
        and existing.plan == envelope.plan
        and existing.amount == envelope.amount
        and existing.currency == envelope.currency
        and existing_occurred_at == envelope.occurred_at.astimezone(UTC)
    )


async def _existing_purchase_event(
    db: AsyncSession, envelope: RevenueBridgeEventEnvelope
) -> ConversionEvent | None:
    if envelope.event_kind != "subscription_activated":
        return None
    return await db.scalar(
        select(ConversionEvent).where(
            ConversionEvent.organization_id == envelope.organization_id,
            ConversionEvent.idempotency_key == _purchase_idempotency_key(envelope),
        )
    )


class RevenueBridgeService:
    def __init__(self, hmac_secret: str | None = None) -> None:
        self._hmac_secret = hmac_secret

    def _secret(self) -> str:
        return (
            self._hmac_secret
            if self._hmac_secret is not None
            else settings.REVENUE_BRIDGE_HMAC_SECRET
        )

    def verify(self, envelope: RevenueBridgeEventEnvelope) -> bool:
        return verify_hmac_signature(envelope, self._secret())

    async def ingest(
        self,
        envelope: RevenueBridgeEventEnvelope,
        db: AsyncSession,
    ) -> dict[str, Any]:
        """Verify, persist idempotently, and record activation attribution."""

        if not settings.REVENUE_BRIDGE_ENABLED:
            raise RevenueBridgeDisabled("Revenue bridge is disabled")
        if not self.verify(envelope):
            raise InvalidRevenueBridgeSignature("Invalid revenue bridge signature")

        existing = await db.scalar(
            select(RevenueBridgeEvent).where(
                RevenueBridgeEvent.provider == envelope.provider,
                RevenueBridgeEvent.provider_event_id == envelope.provider_event_id,
            )
        )
        if existing is not None:
            if not _same_provider_event(existing, envelope):
                raise RevenueBridgeConflictError(
                    "Provider event ID is already bound to different evidence"
                )
            purchase = await _existing_purchase_event(db, envelope)
            return {
                "event_id": existing.id,
                "verified": True,
                "duplicate": True,
                "purchase_event_id": purchase.id if purchase else None,
            }

        bridge_event = RevenueBridgeEvent(
            provider=envelope.provider,
            provider_event_id=envelope.provider_event_id,
            organization_id=envelope.organization_id,
            event_kind=envelope.event_kind,
            plan=envelope.plan,
            amount=envelope.amount,
            currency=envelope.currency,
            occurred_at=envelope.occurred_at,
            signature=envelope.signature,
            signature_verified=True,
            normalized_status=normalized_status_for_event(envelope.event_kind),
        )
        db.add(bridge_event)

        purchase_event: ConversionEvent | None = None
        if envelope.event_kind == "subscription_activated":
            purchase_event = ConversionEvent(
                organization_id=envelope.organization_id,
                event_type="purchase",
                source=envelope.provider,
                metadata_json={
                    "provider": envelope.provider,
                    "provider_event_id": envelope.provider_event_id,
                    "event_kind": envelope.event_kind,
                    "plan": envelope.plan,
                    "verified_amount": str(envelope.amount),
                    "currency": envelope.currency,
                    "verified": True,
                    "verified_provider_event": True,
                },
                occurred_at=envelope.occurred_at,
                idempotency_key=_purchase_idempotency_key(envelope),
            )
            db.add(purchase_event)

        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = await db.scalar(
                select(RevenueBridgeEvent).where(
                    RevenueBridgeEvent.provider == envelope.provider,
                    RevenueBridgeEvent.provider_event_id == envelope.provider_event_id,
                )
            )
            if existing is None:
                raise
            if not _same_provider_event(existing, envelope):
                raise RevenueBridgeConflictError(
                    "Provider event ID is already bound to different evidence"
                )
            purchase = await _existing_purchase_event(db, envelope)
            return {
                "event_id": existing.id,
                "verified": True,
                "duplicate": True,
                "purchase_event_id": purchase.id if purchase else None,
            }

        await db.refresh(bridge_event)
        return {
            "event_id": bridge_event.id,
            "verified": True,
            "duplicate": False,
            "purchase_event_id": purchase_event.id if purchase_event else None,
        }
