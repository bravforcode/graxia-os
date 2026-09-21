from datetime import datetime
from decimal import Decimal
from typing import Any, Optional, List
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Digital Product ───────────────────────────────────────────────────────


class DigitalProductBase(BaseModel):
    name: str = Field(..., max_length=255)
    slug: str = Field(..., max_length=255)
    description: Optional[str] = None
    short_description: Optional[str] = Field(None, max_length=500)
    product_type: str = "other"
    price_amount: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="THB", max_length=10)
    cover_image_url: Optional[str] = None
    sales_page_content: Optional[str] = None


class DigitalProductCreate(DigitalProductBase):
    organization_id: Optional[UUID] = None


class DigitalProductUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    short_description: Optional[str] = None
    status: Optional[str] = None
    product_type: Optional[str] = None
    price_amount: Optional[Decimal] = None
    currency: Optional[str] = None
    cover_image_url: Optional[str] = None
    sales_page_content: Optional[str] = None


class DigitalProductRead(DigitalProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    status: str
    stripe_price_id: Optional[str] = None
    stripe_product_id: Optional[str] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# ── Delivery Asset ────────────────────────────────────────────────────────


class DeliveryAssetBase(BaseModel):
    asset_type: str
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    storage_path: Optional[str] = None
    external_url: Optional[str] = None
    content_body: Optional[str] = None
    is_active: bool = True


class DeliveryAssetCreate(DeliveryAssetBase):
    product_id: Optional[UUID] = None
    organization_id: Optional[UUID] = None


class DeliveryAssetUpdate(BaseModel):
    asset_type: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    storage_path: Optional[str] = None
    external_url: Optional[str] = None
    content_body: Optional[str] = None
    is_active: Optional[bool] = None


class DeliveryAssetRead(DeliveryAssetBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: datetime


# ── Checkout Session ──────────────────────────────────────────────────────


class FunnelCheckoutCreate(BaseModel):
    contact_id: Optional[UUID] = None
    customer_email: Optional[str] = None
    success_url: str
    cancel_url: str
    metadata: Optional[dict[str, Any]] = None


class FunnelCheckoutCreatePublic(FunnelCheckoutCreate):
    organization_id: UUID


class FunnelCheckoutRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    organization_id: UUID
    product_id: UUID
    status: str
    stripe_session_id: Optional[str] = None
    checkout_url: Optional[str] = Field(None, validation_alias="stripe_checkout_url")
    amount: Decimal
    currency: str
    customer_email: Optional[str] = None
    created_at: datetime


class FunnelCheckoutSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    product_id: UUID
    contact_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    stripe_session_id: Optional[str] = None
    status: str
    amount: Decimal
    currency: str
    customer_email: Optional[str] = None
    metadata_json: Optional[dict[str, Any]] = None
    expires_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
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
    contact_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    status: str
    subtotal_amount: Decimal
    total_amount: Decimal
    currency: str
    customer_email: Optional[str] = None
    paid_at: Optional[datetime] = None
    created_at: datetime
    items: List[FunnelOrderItemRead] = []


# ── Delivery Access ───────────────────────────────────────────────────────


class DeliveryAccessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    order_id: UUID
    product_id: UUID
    asset_id: Optional[UUID] = None
    status: str
    download_count: int
    max_downloads: Optional[int] = None
    expires_at: Optional[datetime] = None
    first_accessed_at: Optional[datetime] = None
    last_accessed_at: Optional[datetime] = None
    created_at: datetime


class DeliveryAccessPublic(BaseModel):
    product_name: str
    asset_title: Optional[str]
    status: str
    is_opened: bool
    opened_at: Optional[datetime]


class DeliveryAccessGrantResponse(BaseModel):
    access_id: UUID
    raw_token: str  # Only returned once at creation


class DeliveryEmailEventCreate(BaseModel):
    order_id: UUID
    delivery_access_id: Optional[UUID] = None
    customer_email: str = Field(..., max_length=255)
    status: str = "pending"
    provider: str = Field(default="mock", max_length=100)
    idempotency_key: str = Field(..., max_length=255)
    error_code: Optional[str] = Field(None, max_length=100)
    error_message_redacted: Optional[str] = Field(None, max_length=500)
    sent_at: Optional[datetime] = None
    metadata_json: Optional[dict[str, Any]] = None
    organization_id: Optional[UUID] = None


class DeliveryEmailEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    order_id: UUID
    delivery_access_id: Optional[UUID] = None
    customer_email: str
    status: str
    provider: str
    idempotency_key: str
    error_code: Optional[str] = None
    error_message_redacted: Optional[str] = None
    sent_at: Optional[datetime] = None
    metadata_json: Optional[dict[str, Any]] = None
    created_at: datetime


class DeliveryPayload(BaseModel):
    product_name: str
    asset_title: str
    asset_type: str
    content_body: Optional[str] = None
    external_url: Optional[str] = None
    storage_path: Optional[str] = None
    expires_at: Optional[datetime] = None
    downloads_remaining: Optional[int] = None


# ── Conversion Event ──────────────────────────────────────────────────────


class ConversionAttributionTouch(BaseModel):
    source: Optional[str] = Field(None, max_length=100)
    medium: Optional[str] = Field(None, max_length=100)
    campaign: Optional[str] = Field(None, max_length=100)
    referrer: Optional[str] = None
    path: Optional[str] = Field(None, max_length=500)


class ConversionEventCreate(BaseModel):
    event_type: str
    product_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    order_id: Optional[UUID] = None
    session_id: Optional[str] = None
    idempotency_key: Optional[str] = Field(None, max_length=255)
    source: Optional[str] = None
    medium: Optional[str] = None
    campaign: Optional[str] = None
    referrer: Optional[str] = None
    first_touch: Optional[ConversionAttributionTouch] = None
    last_touch: Optional[ConversionAttributionTouch] = None
    landing_path: Optional[str] = Field(None, max_length=500)
    content_id: Optional[str] = Field(None, max_length=255)
    referral_code: Optional[str] = Field(None, max_length=160)
    metadata_json: Optional[dict[str, Any]] = None


class ConversionEventCreatePublic(ConversionEventCreate):
    organization_id: UUID


class ConversionEventRead(ConversionEventCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    occurred_at: datetime
    created_at: datetime


class FunnelAnalyticsSummary(BaseModel):
    views: int
    unique_visitors: int
    leads: int
    checkout_starts: int
    purchases: int
    delivery_opened: int
    lead_conversion_rate: float
    checkout_rate: float
    purchase_conversion_rate: float
    checkout_to_purchase_rate: float
    sales_count: int
    total_revenue: float
    average_order_value: float


class FunnelDailyAnalytics(BaseModel):
    date: str
    views: int
    leads: int
    purchases: int
    revenue: float


class FunnelAttributionRow(BaseModel):
    source: Optional[str] = None
    medium: Optional[str] = None
    campaign: Optional[str] = None
    product_id: Optional[UUID] = None
    product_name: Optional[str] = None
    plan: Optional[str] = None
    views: int = 0
    leads: int = 0
    checkout_starts: int = 0
    purchases: int = 0
    revenue: float = 0.0


class FunnelDashboardResponse(BaseModel):
    period: dict[str, Any]
    funnel: dict[str, Any]
    rates: dict[str, Any]
    verified_revenue: dict[str, Any]
    verified_subscriptions: dict[str, Any]
    refunds: dict[str, Any] = Field(default_factory=dict)
    by_source: list[dict[str, Any]] = Field(default_factory=list)
    by_product: list[dict[str, Any]] = Field(default_factory=list)
    by_plan: list[dict[str, Any]] = Field(default_factory=list)
    by_referral: list[dict[str, Any]] = Field(default_factory=list)
    content: dict[str, Any] = Field(default_factory=dict)
    data_quality: dict[str, Any] = Field(default_factory=dict)


# ── Lead Magnet ───────────────────────────────────────────────────────────


class LeadMagnetBase(BaseModel):
    name: str = Field(..., max_length=255)
    slug: str = Field(..., max_length=255)
    target_product_id: Optional[UUID] = None
    promise: Optional[str] = None
    file_url: Optional[str] = Field(None, max_length=500)
    landing_page_url: Optional[str] = Field(None, max_length=500)


class LeadMagnetCreate(LeadMagnetBase):
    organization_id: Optional[UUID] = None


class LeadMagnetUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    target_product_id: Optional[UUID] = None
    promise: Optional[str] = None
    file_url: Optional[str] = None
    landing_page_url: Optional[str] = None
    status: Optional[str] = None


class LeadMagnetRead(LeadMagnetBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    status: str
    opt_in_count: int
    created_at: datetime
    updated_at: datetime


class LeadMagnetPublic(BaseModel):
    slug: str
    title: str
    description: Optional[str] = None


class LeadCaptureCreate(BaseModel):
    lead_magnet_id: UUID
    email: str = Field(..., max_length=255)
    source: Optional[str] = Field(None, max_length=100)
    utm_source: Optional[str] = Field(None, max_length=255)
    utm_medium: Optional[str] = Field(None, max_length=255)
    utm_campaign: Optional[str] = Field(None, max_length=255)
    metadata_json: Optional[dict[str, Any]] = None
    organization_id: Optional[UUID] = None


class LeadCaptureRead(LeadCaptureCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    created_at: datetime


class LeadCaptureRequest(BaseModel):
    organization_id: UUID
    email: str = Field(..., max_length=300)
    name: Optional[str] = Field(None, max_length=300)
    marketing_consent: bool = False
    consent_version: Optional[str] = Field(None, max_length=100)
    session_id: Optional[str] = Field(None, max_length=255)
    source: Optional[str] = None
    medium: Optional[str] = None
    campaign: Optional[str] = None
    referrer: Optional[str] = None

class LeadCaptureResponse(BaseModel):
    contact_id: UUID
    raw_token: Optional[str] = None
    delivery_url: Optional[str] = None


class UnsubscribeRequest(BaseModel):
    organization_id: UUID
    email: str = Field(..., max_length=300)


class UnsubscribeResponse(BaseModel):
    ok: bool = True


# ── Recommendation ────────────────────────────────────────────────────────


class FunnelRecommendationCreate(BaseModel):
    recommendation_type: str = Field(..., max_length=50)
    recommended_action: str
    bottleneck: Optional[str] = Field(None, max_length=255)
    expected_impact: Optional[str] = Field(None, max_length=255)
    confidence: Optional[str] = Field(None, max_length=50)
    effort: Optional[str] = Field(None, max_length=50)
    risk: Optional[str] = Field(None, max_length=50)
    reasoning: Optional[str] = None
    draft_content: Optional[str] = None
    metadata_json: Optional[dict[str, Any]] = None


class FunnelRecommendationRead(FunnelRecommendationCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    product_id: UUID
    rollback_note: Optional[str] = None
    approval_request_id: Optional[UUID] = None
    status: str
    created_at: datetime
    updated_at: datetime


# ── Coupon ────────────────────────────────────────────────────────────────


class CouponCreate(BaseModel):
    code: str = Field(..., max_length=50)
    coupon_type: str  # percentage | fixed
    discount_value: Decimal
    currency: Optional[str] = "THB"
    min_order_amount: Optional[Decimal] = Decimal("0")
    max_uses: Optional[int] = None
    product_id: Optional[UUID] = None
    expires_at: Optional[datetime] = None
    description: Optional[str] = None


class CouponUpdate(BaseModel):
    code: Optional[str] = None
    coupon_type: Optional[str] = None
    discount_value: Optional[Decimal] = None
    min_order_amount: Optional[Decimal] = None
    max_uses: Optional[int] = None
    status: Optional[str] = None
    expires_at: Optional[datetime] = None
    description: Optional[str] = None


class CouponRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    code: str
    coupon_type: str
    discount_value: Decimal
    currency: str
    min_order_amount: Decimal
    max_uses: Optional[int]
    used_count: int
    product_id: Optional[UUID]
    status: str
    expires_at: Optional[datetime]
    description: Optional[str]
    created_at: datetime
    updated_at: datetime


class CouponValidateRequest(BaseModel):
    code: str
    order_amount: Decimal
    product_id: Optional[UUID] = None


class CouponValidateResponse(BaseModel):
    is_valid: bool
    message: str
    discount_amount: Optional[Decimal] = None
    final_amount: Optional[Decimal] = None


# ── Review ────────────────────────────────────────────────────────────────


class ReviewCreate(BaseModel):
    product_id: UUID
    order_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    customer_name: str = Field(..., max_length=255)
    customer_email: str = Field(..., max_length=255)
    rating: int = Field(..., ge=1, le=5)
    title: Optional[str] = Field(None, max_length=255)
    body: Optional[str] = None


class ReviewUpdate(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    title: Optional[str] = None
    body: Optional[str] = None
    status: Optional[str] = None


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    product_id: UUID
    order_id: Optional[UUID]
    customer_name: str
    customer_email: str
    rating: int
    title: Optional[str]
    body: Optional[str]
    status: str
    is_verified_purchase: bool
    created_at: datetime
    updated_at: datetime


class ReviewStats(BaseModel):
    total_reviews: int
    average_rating: float
    rating_distribution: dict[str, int]


# ── Bundle ────────────────────────────────────────────────────────────────


class BundleCreate(BaseModel):
    name: str = Field(..., max_length=255)
    slug: str = Field(..., max_length=255)
    description: Optional[str] = None
    discount_type: str  # percentage | fixed
    discount_value: Decimal
    product_ids: Optional[List[UUID]] = None
    cover_image_url: Optional[str] = None
    badge: Optional[str] = None


class BundleUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[Decimal] = None
    product_ids: Optional[List[UUID]] = None
    status: Optional[str] = None
    cover_image_url: Optional[str] = None
    badge: Optional[str] = None


class BundleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    slug: str
    description: Optional[str]
    discount_type: str
    discount_value: Decimal
    status: str
    cover_image_url: Optional[str]
    product_ids: Optional[List[str]]
    sales_count: int
    badge: Optional[str]
    created_at: datetime
    updated_at: datetime


# ── Email Sequence ────────────────────────────────────────────────────────


class EmailSequenceCreate(BaseModel):
    name: str = Field(..., max_length=255)
    trigger_type: str  # welcome, abandoned_cart, post_purchase, etc.
    delay_hours: int = 0
    subject_template: str = Field(..., max_length=500)
    body_template: str
    product_id: Optional[UUID] = None


class EmailSequenceUpdate(BaseModel):
    name: Optional[str] = None
    trigger_type: Optional[str] = None
    delay_hours: Optional[int] = None
    subject_template: Optional[str] = None
    body_template: Optional[str] = None
    status: Optional[str] = None
    product_id: Optional[UUID] = None


class EmailSequenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    trigger_type: str
    status: str
    delay_hours: int
    subject_template: str
    body_template: str
    product_id: Optional[UUID]
    total_sent: int
    total_opened: int
    total_clicked: int
    created_at: datetime
    updated_at: datetime
