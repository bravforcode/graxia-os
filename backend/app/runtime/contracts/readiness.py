from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .base import RuntimeBase


class ReadinessLevel(StrEnum):
    BASELINE_CLEAN = "BASELINE_CLEAN"
    CONTRACT_READY = "CONTRACT_READY"
    ADAPTER_READY = "ADAPTER_READY"
    CONTEXT_SAFE = "CONTEXT_SAFE"
    EVENT_READY = "EVENT_READY"
    RUNTIME_READY = "RUNTIME_READY"
    MCP_READY = "MCP_READY"
    UI_READY = "UI_READY"
    STAGING_READY = "STAGING_READY"
    PROD_DRY_RUN_READY = "PROD_DRY_RUN_READY"
    GLOBAL_OPS_READY = "GLOBAL_OPS_READY"


class ReadinessCheck(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str
    ready: bool
    detail: str | None = None
    evidence: list[str] = Field(default_factory=list)


class ReadinessStatus(RuntimeBase):
    name: str
    ready: bool
    level: ReadinessLevel
    checks: list[ReadinessCheck] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

