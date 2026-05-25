from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Digital Product ───────────────────────────────────────────────────────

class DigitalProductBase(BaseModel):
    name: str = Field(..., max_length=255)
    slug: str = Field(..., max_length=255)
    description: str | None = None
    short_description: str | None = Field(None, max_length=500)
    product_type: str = "other"
    price_amount: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="THB", max_length=10)
    cover_image_url: str | None = None
    sales_page_content: str | None = None

class DigitalProductCreate(DigitalProductBase):
    organization_id: UUID

class DigitalProductUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None
    short_description: str | None = None
    status: str | None = None
    product_type: str | None = None
    price_amount: Decimal | None = None
    currency: str | None = None
    cover_image_url: str | None = None
    sales_page_content: str | None = None

class DigitalProductRead(DigitalProductBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    organization_id: UUID
    status: str
    stripe_price_id: str | None = None
    stripe_product_id: str | None = None
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ── Delivery Asset ────────────────────────────────────────────────────────

class DeliveryAssetBase(BaseModel):
    asset_type: str
    title: str = Field(..., max_length=255)
    description: str | None = None
    storage_path: str | None = None
    external_url: str | None = None
    content_body: str | None = None
    is_active: bool = True

class DeliveryAssetCreate(DeliveryAssetBase):
    product_id: UUID
    organization_id: UUID

class DeliveryAssetRead(DeliveryAssetBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    product_id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: datetime


# ── Checkout Session ──────────────────────────────────────────────────────

class FunnelCheckoutSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    organization_id: UUID
    product_id: UUID
    contact_id: UUID | None = None
    user_id: UUID | None = None
    stripe_session_id: str | None = None
    status: str
    amount: Decimal
    currency: str
    customer_email: str | None = None
    metadata_json: dict[str, Any] | None = None
    expires_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ── Order ─────────────────────────────────────────────────────────────────

class FunnelOrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    product_id: UUID
    quantity: int
    unit_amount: Decimal
    total_amount: Decimal
    currency: str
    created_at: datetime

class FunnelOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    organization_id: UUID
    contact_id: UUID | None = None
    user_id: UUID | None = None
    status: str
    subtotal_amount: Decimal
    total_amount: Decimal
    currency: str
    customer_email: str | None = None
    paid_at: datetime | None = None
    created_at: datetime
    items: list[FunnelOrderItemRead]


# ── Delivery Access ───────────────────────────────────────────────────────

class DeliveryAccessBase(BaseModel):
    order_id: UUID
    product_id: UUID
    delivery_asset_id: UUID | None = None
    expires_at: datetime | None = None

class DeliveryAccessGrant(DeliveryAccessBase):
    organization_id: UUID

class DeliveryAccessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    order_id: UUID
    product_id: UUID
    delivery_asset_id: UUID | None = None
    status: str
    expires_at: datetime | None = None
    first_opened_at: datetime | None = None
    last_opened_at: datetime | None = None
    open_count: int = 0
    download_count: int = 0
    max_downloads: int | None = None
    created_at: datetime

class DeliveryAccessPublic(BaseModel):
    """Safe public response - no internal data leaked"""
    product_name: str
    asset_title: str | None = None
    status: str
    is_opened: bool = False
    opened_at: datetime | None = None


# ── Delivery Email Event ────────────────────────────────────────────────

class DeliveryEmailEventCreate(BaseModel):
    order_id: UUID
    delivery_access_id: UUID | None = None
    customer_email: str
    provider: str = "mock"
    idempotency_key: str
    metadata_json: dict[str, Any] | None = None

class DeliveryEmailEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    delivery_access_id: UUID | None = None
    customer_email: str
    status: str
    provider: str
    error_code: str | None = None
    error_message_redacted: str | None = None
    sent_at: datetime | None = None
    created_at: datetime


# ── Lead Magnet ──────────────────────────────────────────────────────────

class LeadMagnetBase(BaseModel):
    slug: str = Field(..., max_length=255)
    title: str = Field(..., max_length=255)
    description: str | None = None
    product_id: UUID | None = None
    asset_id: UUID | None = None

class LeadMagnetCreate(LeadMagnetBase):
    organization_id: UUID

class LeadMagnetUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None

class LeadMagnetRead(LeadMagnetBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    status: str
    created_at: datetime
    updated_at: datetime

class LeadMagnetPublic(BaseModel):
    """Public lead magnet info - no internal data"""
    slug: str
    title: str
    description: str | None = None


# ── Lead Capture ─────────────────────────────────────────────────────────

class LeadCaptureCreate(BaseModel):
    email: str
    source: str | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    metadata_json: dict[str, Any] | None = None

class LeadCaptureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lead_magnet_id: UUID
    email: str
    source: str | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    created_at: datetime


# ── Funnel Recommendation ───────────────────────────────────────────────

class FunnelRecommendationCreate(BaseModel):
    product_id: UUID
    recommendation_type: str
    bottleneck: str | None = None
    recommended_action: str
    expected_impact: str | None = None
    confidence: str | None = None
    effort: str | None = None
    risk: str | None = None
    reasoning: str | None = None
    draft_content: str | None = None
    metadata_json: dict[str, Any] | None = None

class FunnelRecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    organization_id: UUID
    recommendation_type: str
    bottleneck: str | None = None
    recommended_action: str
    expected_impact: str | None = None
    confidence: str | None = None
    effort: str | None = None
    risk: str | None = None
    reasoning: str | None = None
    draft_content: str | None = None
    rollback_note: str | None = None
    approval_request_id: UUID | None = None
    status: str
    created_at: datetime
    updated_at: datetime


# ── Analytics ────────────────────────────────────────────────────────────

class FunnelAnalyticsSummary(BaseModel):
    total_products: int = 0
    published_products: int = 0
    total_orders: int = 0
    paid_orders: int = 0
    total_revenue: str = "0"
    total_checkouts: int = 0
    checkout_abandonment_rate: float = 0
    total_delivery_accesses: int = 0
    delivery_open_rate: float = 0
    total_lead_captures: int = 0


# ── Conversion Event ──────────────────────────────────────────────────────

class ConversionEventCreate(BaseModel):
    event_type: str
    product_id: UUID | None = None
    contact_id: UUID | None = None
    order_id: UUID | None = None
    session_id: str | None = None
    source: str | None = None
    medium: str | None = None
    campaign: str | None = None
    referrer: str | None = None
    metadata_json: dict[str, Any] | None = None

class ConversionEventRead(ConversionEventCreate):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    organization_id: UUID
    occurred_at: datetime
    created_at: datetime
