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
