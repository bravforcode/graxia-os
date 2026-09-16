"""Small, provider-neutral contracts for the consolidated Content Ops path."""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ContentLifecycle(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"
    ARCHIVED = "archived"


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}$")
_SAFE_PROVIDER = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")
_SAFE_ERROR = re.compile(r"^[A-Z0-9][A-Z0-9_.-]{0,63}$")
_SECRET = re.compile(r"(?:sk_(?:live|test)_|rk_(?:live|test)_|whsec_|gh[pousr]_|AIza)", re.I)
_EMAIL = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")


def _required_id(value: str) -> str:
    value = value.strip()
    if not value or not _SAFE_ID.fullmatch(value):
        raise ValueError("identifier must be a non-empty safe identifier")
    if _SECRET.search(value) or _EMAIL.search(value):
        raise ValueError("identifier contains unsafe provider or PII material")
    return value


class PublishRequest(BaseModel):
    """A tenant-scoped publish intent; dry-run is the safe default."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=256)
    content_id: str = Field(min_length=1, max_length=256)
    provider: str = Field(min_length=2, max_length=32)
    scheduled_at: datetime | None = None
    approval_id: str = Field(min_length=1, max_length=256)
    idempotency_key: str = Field(min_length=1, max_length=256)
    dry_run: bool = True
    live: bool = False

    _tenant_id = field_validator("tenant_id")(_required_id)
    _content_id = field_validator("content_id")(_required_id)
    _approval_id = field_validator("approval_id")(_required_id)
    _idempotency_key = field_validator("idempotency_key")(_required_id)

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        value = value.strip().lower()
        if not _SAFE_PROVIDER.fullmatch(value):
            raise ValueError("provider must be a safe provider name")
        return value

    @model_validator(mode="after")
    def validate_live_gate(self) -> "PublishRequest":
        if self.live and self.dry_run:
            raise ValueError("live publish cannot be marked dry_run")
        return self


class PublishReceipt(BaseModel):
    """Redacted result of a publish attempt; raw provider errors are forbidden."""

    model_config = ConfigDict(extra="forbid")

    attempt_id: str = Field(min_length=1, max_length=256)
    provider_status: str = Field(min_length=1, max_length=64)
    external_id: str | None = Field(default=None, max_length=256)
    started_at: datetime
    finished_at: datetime
    retryable: bool
    redacted_error_code: str | None = Field(default=None, max_length=64)

    _attempt_id = field_validator("attempt_id")(_required_id)
    _external_id = field_validator("external_id")(_required_id)

    @field_validator("provider_status")
    @classmethod
    def validate_provider_status(cls, value: str) -> str:
        value = value.strip()
        if not value or _SECRET.search(value) or _EMAIL.search(value):
            raise ValueError("provider_status must be redacted")
        return value

    @field_validator("redacted_error_code")
    @classmethod
    def validate_error_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if not _SAFE_ERROR.fullmatch(value):
            raise ValueError("redacted_error_code must be a short safe code")
        return value

    @model_validator(mode="after")
    def validate_time_order(self) -> "PublishReceipt":
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        return self
