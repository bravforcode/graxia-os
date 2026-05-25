from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

CURRENT_RUNTIME_SCHEMA_VERSION = "2026-04-21"


class ActorType(StrEnum):
    SYSTEM = "system"
    USER = "user"
    AGENT = "agent"
    CUSTOMER = "customer"
    SERVICE = "service"


class RiskLevel(StrEnum):
    READ_ONLY = "READ_ONLY"
    LOW_WRITE = "LOW_WRITE"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    DANGEROUS_BLOCKED = "DANGEROUS_BLOCKED"


def utcnow() -> datetime:
    return datetime.now(UTC)


class RuntimeBase(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        from_attributes=True,
        use_enum_values=True,
    )

    schema_version: str = Field(
        default=CURRENT_RUNTIME_SCHEMA_VERSION,
        alias="schemaVersion",
    )
    organization_id: UUID = Field(alias="organizationId")
    correlation_id: str = Field(alias="correlationId")
    created_at: datetime = Field(default_factory=utcnow, alias="createdAt")
    source: str

