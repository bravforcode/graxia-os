from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import Field

from .base import RiskLevel, RuntimeBase


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalContract(RuntimeBase):
    approval_request_id: UUID = Field(default_factory=uuid4, alias="approvalRequestId")
    action_type: str = Field(alias="actionType")
    subject_type: str = Field(alias="subjectType")
    subject_id: str = Field(alias="subjectId")
    status: ApprovalStatus = ApprovalStatus.PENDING
    risk_level: RiskLevel = Field(
        default=RiskLevel.APPROVAL_REQUIRED,
        alias="riskLevel",
    )
    requested_by: str = Field(alias="requestedBy")
    preview: dict[str, Any] = Field(default_factory=dict)
    policy_reason: str = Field(alias="policyReason")
    expires_at: datetime | None = Field(default=None, alias="expiresAt")
    execution_plan: dict[str, Any] | None = Field(default=None, alias="executionPlan")

