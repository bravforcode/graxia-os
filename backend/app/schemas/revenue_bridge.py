from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


RevenueBridgeEventKind = Literal[
    "subscription_activated",
    "subscription_cancelled",
    "payment_failed",
    "refund",
]
RevenueBridgePlan = Literal["starter", "growth", "scale"]


class RevenueBridgeEventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=100)
    provider_event_id: str = Field(min_length=1, max_length=255)
    organization_id: UUID
    event_kind: RevenueBridgeEventKind
    plan: RevenueBridgePlan
    amount: Decimal = Field(ge=0)
    currency: Literal["THB"]
    occurred_at: datetime
    signature: str = Field(min_length=1, max_length=128)

    @field_validator("provider", "provider_event_id")
    @classmethod
    def require_non_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include an ISO-8601 timezone")
        return value.astimezone(UTC)


class RevenueBridgeIngestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    verified: bool
    duplicate: bool
    purchase_event_id: UUID | None = None
