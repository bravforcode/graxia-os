from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from .base import RuntimeBase


class CompressionMode(StrEnum):
    NONE = "none"
    SUMMARY = "summary"
    DIFF = "diff"
    COMPACT = "compact"


class QualityGateStatus(StrEnum):
    NOT_CHECKED = "not_checked"
    PASSED = "passed"
    FAILED = "failed"
    ESCALATED = "escalated"


class ContextPacketRef(RuntimeBase):
    context_packet_id: str = Field(alias="contextPacketId")
    task_type: str = Field(alias="taskType")
    goal: str
    estimated_tokens: int = Field(alias="estimatedTokens", ge=0)
    compression_mode: CompressionMode = Field(alias="compressionMode")
    quality_gate_status: QualityGateStatus = Field(alias="qualityGateStatus")
    file_hashes: dict[str, str] = Field(default_factory=dict, alias="fileHashes")
    policy_version: str = Field(alias="policyVersion")
    generated_at: str = Field(alias="generatedAt")

