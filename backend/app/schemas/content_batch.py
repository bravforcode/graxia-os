"""API contracts for tenant-scoped organic content batches."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContentBatchCreate(BaseModel):
    """Queue intent; it contains no provider credential material."""

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1, max_length=500)
    site: str = Field(default="site_a", pattern="^(site_a|site_b)$")
    language: str = Field(default="en", pattern="^(en|th)$")
    canonical_url: str = Field(min_length=1, max_length=2048)
    provider: str = Field(default="organic", min_length=2, max_length=32)
    idempotency_key: str = Field(default_factory=lambda: f"batch-{uuid4()}", max_length=256)
    approval_id: UUID | None = None
    claim_reviewed: bool = False
    claim_ids: list[str] = Field(default_factory=list, max_length=100)
    canary_passed: bool = False
    provider_consent: bool = False
    provider_credentials_available: bool = False
    utm_source: str | None = Field(default=None, max_length=100)
    utm_medium: str | None = Field(default=None, max_length=100)
    utm_campaign: str | None = Field(default=None, max_length=255)
    live: bool = False
    dry_run: bool = True

    @field_validator("topic", "canonical_url", "provider", "idempotency_key")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("utm_source", "utm_medium", "utm_campaign")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("claim_ids")
    @classmethod
    def validate_claim_ids(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("claim_ids must be unique")
        return cleaned


class ContentBatchQueued(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    item_count: int = 9
    queue_id: str | None = None
    idempotency_key: str
    created_at: datetime | None = None


class ContentBatchItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    item_key: str
    idempotency_key: str
    position: int
    role: str
    channel: str
    title: str
    slug: str
    body: str
    canonical_url: str
    utm_params: dict[str, str] | None = None
    status: str
    fallback_used: bool
    provider_status: str | None = None
    block_codes: list[str] | None = None


class ContentBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    item_count: int
    live: bool
    dry_run: bool
    fallback_used: bool
    block_codes: list[str] | None = None
    items: list[ContentBatchItemOut] = Field(default_factory=list)


class ContentBatchProcessOut(BaseModel):
    batch_id: str
    status: str
    mode: str
    item_count: int
    fallback_used: bool
    block_codes: list[str] = Field(default_factory=list)
