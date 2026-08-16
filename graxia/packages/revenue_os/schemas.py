"""
graxia/packages/revenue_os/schemas.py
Pydantic v2 response/request schemas — fixes MED-06.

All API endpoints use these schemas as response_model to:
  1. Prevent sensitive field leakage
  2. Generate accurate OpenAPI docs
  3. Enforce consistent error response shape
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .enums import RuleType, ValueType


# ─────────────────────────────────────────────────────────────────────────────
# Shared
# ─────────────────────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str


class ErrorDetail(BaseModel):
    code: str
    detail: str
    field: Optional[str] = None


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[Any]


# ─────────────────────────────────────────────────────────────────────────────
# Order
# ─────────────────────────────────────────────────────────────────────────────

class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    platform: str
    platform_order_id: str
    customer_email: str
    customer_name: Optional[str]
    amount_cents: int
    currency: str
    status: str
    idempotency_key: str
    created_at: datetime
    updated_at: datetime


class OrderListResponse(BaseModel):
    total: int
    items: List[OrderResponse]


# ─────────────────────────────────────────────────────────────────────────────
# Ledger Entry
# ─────────────────────────────────────────────────────────────────────────────

class LedgerEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    entry_type: str
    amount_cents: int
    currency: str
    description: Optional[str]
    created_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# Refund
# ─────────────────────────────────────────────────────────────────────────────

class RefundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    platform_refund_id: str
    amount_cents: int
    reason: Optional[str]
    status: str
    processed_at: Optional[datetime]
    created_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# Entitlement
# ─────────────────────────────────────────────────────────────────────────────

class EntitlementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    customer_email: str
    product_key: str
    granted_at: datetime
    expires_at: Optional[datetime]
    revoked_at: Optional[datetime]


# ─────────────────────────────────────────────────────────────────────────────
# Revenue Campaign
# ─────────────────────────────────────────────────────────────────────────────

class CampaignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_by_agent: str
    status: str
    budget_cents: Optional[int]
    target_revenue_cents: Optional[int]
    actual_revenue_cents: int
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    paused_reason: Optional[str]
    created_at: datetime
    updated_at: datetime


class CampaignCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    created_by_agent: str = Field(..., max_length=100)
    budget_cents: Optional[int] = Field(None, gt=0)
    target_revenue_cents: Optional[int] = Field(None, gt=0)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


# ─────────────────────────────────────────────────────────────────────────────
# Lead
# ─────────────────────────────────────────────────────────────────────────────

class LeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: Optional[str]
    company: Optional[str]
    title: Optional[str]
    linkedin_url: Optional[str]
    source: str
    score: Optional[int]
    score_rationale: Optional[str]
    status: str
    campaign_id: Optional[UUID]
    contacted_at: Optional[datetime]
    converted_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class LeadCreateRequest(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None
    linkedin_url: Optional[str] = None
    source: str = Field(..., max_length=100)
    campaign_id: Optional[UUID] = None


# ─────────────────────────────────────────────────────────────────────────────
# Approval
# ─────────────────────────────────────────────────────────────────────────────

class ApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    item_type: str
    item_id: UUID
    requested_by_agent: str
    status: str
    ceo_notes: Optional[str]
    reviewed_at: Optional[datetime]
    expires_at: Optional[datetime]
    created_at: datetime


class ApprovalDecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(approved|rejected)$")
    ceo_notes: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Email Outbox
# ─────────────────────────────────────────────────────────────────────────────

class EmailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    to_email: str
    subject: str
    status: str
    retry_count: int
    scheduled_at: Optional[datetime]
    sent_at: Optional[datetime]
    created_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# Delivery Event
# ─────────────────────────────────────────────────────────────────────────────

class DeliveryEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    delivery_type: str
    status: str
    delivered_at: Optional[datetime]
    failed_at: Optional[datetime]
    failure_reason: Optional[str]
    created_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# Incident
# ─────────────────────────────────────────────────────────────────────────────

class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    severity: str
    source_agent: str
    title: str
    description: str
    affected_campaign_id: Optional[UUID]
    affected_order_id: Optional[UUID]
    resolved_at: Optional[datetime]
    resolution_notes: Optional[str]
    created_at: datetime


class IncidentCreateRequest(BaseModel):
    severity: str = Field(..., pattern="^(low|medium|high|critical)$")
    source_agent: str = Field(..., max_length=100)
    title: str = Field(..., min_length=1, max_length=500)
    description: str
    affected_campaign_id: Optional[UUID] = None
    affected_order_id: Optional[UUID] = None


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────────────────

class DashboardSummary(BaseModel):
    total_revenue_cents: int
    revenue_this_month_cents: int
    active_campaigns: int
    leads_count: int
    conversion_rate_pct: float
    pending_approvals: int
    open_incidents: int
    emails_pending: int


# ─────────────────────────────────────────────────────────────────────────────
# System / Health
# ─────────────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    db_connected: bool
    celery_ready: bool
    version: str = "1.0.0"


class CheckoutWebhookResponse(BaseModel):
    status: str
    order_id: Optional[UUID] = None
    message: str


# ─────────────────────────────────────────────────────────────────────────────
# Order creation payload (fixes HIGH-01)
# ─────────────────────────────────────────────────────────────────────────────

class CreateOrderPayload(BaseModel):
    """Validated payload for creating an order from a Stripe webhook."""
    platform: str = Field(..., pattern="^(stripe|paddle)$")
    platform_order_id: str = Field(..., min_length=1, max_length=255)
    stripe_event_id: str = Field(..., min_length=1, max_length=255)
    customer_email: EmailStr
    customer_name: Optional[str] = None
    amount_cents: int = Field(..., gt=0)
    currency: str = Field("USD", min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def currency_must_be_uppercase(cls, v: str) -> str:
        if not v.isupper():
            raise ValueError("currency must be ISO 4217 uppercase (e.g. USD, EUR)")
        return v


# ─────────────────────────────────────────────────────────────────────────────
# Policy engine schemas (autonomy guardrails — Task 1/3)
# ─────────────────────────────────────────────────────────────────────────────

class PolicyRuleCreate(BaseModel):
    action: str
    rule_type: RuleType
    value: Optional[float] = None
    value_type: ValueType = ValueType.PERCENT
    limited_multiplier: float = 0.25
    scope: str = "global"
    scope_value: Optional[str] = None
    priority: int = 100
    description: Optional[str] = None


class PolicyRuleUpdate(BaseModel):
    value: Optional[float] = None
    value_type: Optional[ValueType] = None
    limited_multiplier: Optional[float] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    description: Optional[str] = None


class PolicyRuleResponse(BaseModel):
    id: UUID
    action: str
    rule_type: RuleType
    value: Optional[float]
    value_type: ValueType
    limited_multiplier: float
    scope: str
    scope_value: Optional[str]
    enabled: bool
    priority: int
    description: Optional[str]

    class Config:
        from_attributes = True


class SupportChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    customer_email: str = Field(..., max_length=320)
    verification_code: Optional[str] = Field(default=None, max_length=6)


class SupportChatResponse(BaseModel):
    intent: str
    reply: str
    action_taken: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Affiliate (Phase 3)
# ─────────────────────────────────────────────────────────────────────────────

class AffiliateCreateRequest(BaseModel):
    email: EmailStr
    commission_percent: float = Field(..., gt=0, le=100)
    code: Optional[str] = Field(default=None, max_length=50)


class AffiliateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    email: str
    commission_percent: float
    status: str
    created_at: datetime


class AffiliateOverviewResponse(BaseModel):
    total: int
    active: int
    pending_payouts: int
    pending_payout_cents: int
    needs_review: int
    fraud_flags: int


class ChannelPnLResponse(BaseModel):
    platform: str
    orders: int
    revenue_cents: int
    est_fee_cents: int
    est_cost_cents: int
    est_margin_cents: int


class CustomerPlatformSummary(BaseModel):
    platform: str
    orders: int
    spend_cents: int


class CustomerProfileResponse(BaseModel):
    email: str
    total_orders: int
    total_spend_cents: int
    platforms: List[CustomerPlatformSummary]
    first_purchase_at: Optional[datetime]
    last_purchase_at: Optional[datetime]


class TreasuryBalanceResponse(BaseModel):
    currency: str
    cents: int
    thb_equivalent_cents: Optional[int]


class TreasuryResponse(BaseModel):
    balances: List[TreasuryBalanceResponse]
    total_thb_cents: int
    missing_rates: List[str]
