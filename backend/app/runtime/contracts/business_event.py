from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .base import ActorType, RiskLevel, RuntimeBase, utcnow


class BusinessEventRedaction(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    contains_secrets: Literal[False] = Field(default=False, alias="containsSecrets")
    contains_raw_tokens: Literal[False] = Field(default=False, alias="containsRawTokens")


class BusinessEvent(RuntimeBase):
    event_id: UUID = Field(default_factory=uuid4, alias="eventId")
    event_type: str = Field(alias="eventType")
    actor_type: ActorType = Field(alias="actorType")
    actor_id: str | None = Field(default=None, alias="actorId")
    occurred_at: datetime = Field(default_factory=utcnow, alias="occurredAt")
    subject_type: str = Field(alias="subjectType")
    subject_id: str = Field(alias="subjectId")
    causation_id: str | None = Field(default=None, alias="causationId")
    idempotency_key: str | None = Field(default=None, alias="idempotencyKey")
    risk_level: RiskLevel = Field(alias="riskLevel")
    payload: dict[str, Any] = Field(default_factory=dict)
    redaction: BusinessEventRedaction = Field(default_factory=BusinessEventRedaction)
