from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


ReferralSourceType = Literal[
    "captured_lead", "verified_delivery", "approved_partner"
]


class ReferralIssueRequest(BaseModel):
    source_type: ReferralSourceType
    source_id: UUID
    redirect_path: str = Field(..., min_length=1, max_length=500)
    bonus_asset_path: str | None = Field(None, max_length=500)


class ReferralIssueResponse(BaseModel):
    code: str
    referral_url: str
    source_type: ReferralSourceType
    audience: Literal["regular_user", "partner"]
    redirect_path: str
    bonus_asset_path: str | None = None
    commission_rate: Decimal
    hold_days: int


class ReferralAnalyticsRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code_id: UUID
    source_type: ReferralSourceType
    audience: Literal["regular_user", "partner"]
    redirect_path: str
    is_active: bool
    valid_referrals: int
    conversions: int
    commission_held: float
