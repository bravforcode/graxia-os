from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from pydantic import Field

from .base import ActorType, RiskLevel, RuntimeBase


class AuditEvent(RuntimeBase):
    audit_event_id: UUID = Field(default_factory=uuid4, alias="auditEventId")
    event_type: str = Field(alias="eventType")
    actor_type: ActorType = Field(alias="actorType")
    actor_id: str | None = Field(default=None, alias="actorId")
    subject_type: str = Field(alias="subjectType")
    subject_id: str = Field(alias="subjectId")
    risk_level: RiskLevel = Field(alias="riskLevel")
    redacted_payload: dict[str, Any] = Field(default_factory=dict, alias="redactedPayload")
