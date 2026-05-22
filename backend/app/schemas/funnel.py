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
    pass

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
    pass

class DeliveryAssetUpdate(BaseModel):
    asset_type: str | None = None
    title: str | None = None
    description: str | None = None
    storage_path: str | None = None
    external_url: str | None = None
    content_body: str | None = None
    is_active: bool | None = None

class DeliveryAssetRead(DeliveryAssetBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    product_id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: datetime


# ── Checkout Session ──────────────────────────────────────────────────────

class FunnelCheckoutCreate(BaseModel):
    customer_email: str | None = None
    success_url: str
    cancel_url: str

class FunnelCheckoutRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    stripe_session_id: str | None = None
    checkout_url: str | None = None
    status: str
    amount: Decimal
    currency: str
    customer_email: str | None = None
    created_at: datetime

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

class DeliveryAccessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    order_id: UUID
    product_id: UUID
    asset_id: UUID | None = None
    status: str
    expires_at: datetime | None = None
    first_accessed_at: datetime | None = None
    last_accessed_at: datetime | None = None
    download_count: int
    max_downloads: int | None = None
    created_at: datetime


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
