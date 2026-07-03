import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID as UUIDType

from sqlalchemy import (
    UUID as SQLUUID,
)
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TenantMixin


class DigitalProduct(Base, TenantMixin):
    __tablename__ = "digital_products"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_product_status",
        ),
        CheckConstraint(
            "product_type IN ('ebook', 'template', 'prompt_pack', 'course', 'kit', 'other')",
            name="ck_product_type",
        ),
        CheckConstraint("price_amount >= 0", name="ck_product_price_non_negative"),
        Index("ix_digital_products_org_slug", "organization_id", "slug", unique=True),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    short_description: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    product_type: Mapped[str] = mapped_column(
        String(50), default="other", nullable=False
    )
    price_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=0, nullable=False
    )
    currency: Mapped[str] = mapped_column(String(10), default="THB", nullable=False)
    stripe_price_id: Mapped[str | None] = mapped_column(String(100))
    stripe_product_id: Mapped[str | None] = mapped_column(String(100))
    cover_image_url: Mapped[str | None] = mapped_column(Text)
    sales_page_content: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    assets: Mapped[list["DeliveryAsset"]] = relationship(
        "DeliveryAsset",
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    order_items: Mapped[list["FunnelOrderItem"]] = relationship(
        "FunnelOrderItem", back_populates="product"
    )


class DeliveryAsset(Base, TenantMixin):
    __tablename__ = "delivery_assets"
    __table_args__ = (
        CheckConstraint(
            "asset_type IN ('file', 'external_link', 'text', 'private_page')",
            name="ck_asset_type",
        ),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("digital_products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    storage_path: Mapped[str | None] = mapped_column(Text)
    external_url: Mapped[str | None] = mapped_column(Text)
    content_body: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product: Mapped["DigitalProduct"] = relationship(
        "DigitalProduct", back_populates="assets"
    )
    delivery_accesses: Mapped[list["DeliveryAccess"]] = relationship(
        "DeliveryAccess", back_populates="asset"
    )


class FunnelCheckoutSession(Base, TenantMixin):
    __tablename__ = "funnel_checkout_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('created', 'pending', 'completed', 'expired', 'failed', 'cancelled')",
            name="ck_checkout_status",
        ),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("digital_products.id"),
        nullable=False,
        index=True,
    )
    contact_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("contacts.id"), index=True
    )
    user_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    stripe_session_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(50), default="created", nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="THB", nullable=False)
    customer_email: Mapped[str | None] = mapped_column(String(255))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    abandoned_email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FunnelOrder(Base, TenantMixin):
    __tablename__ = "funnel_orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'paid', 'failed', 'refunded', 'cancelled')",
            name="ck_order_status",
        ),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contact_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("contacts.id"), index=True
    )
    user_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    checkout_session_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("funnel_checkout_sessions.id"), index=True
    )
    stripe_session_id: Mapped[str | None] = mapped_column(String(255), index=True)
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(
        String(255), index=True
    )
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="THB", nullable=False)
    customer_email: Mapped[str | None] = mapped_column(String(255))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list["FunnelOrderItem"]] = relationship(
        "FunnelOrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    delivery_accesses: Mapped[list["DeliveryAccess"]] = relationship(
        "DeliveryAccess", back_populates="order", lazy="selectin"
    )


class FunnelOrderItem(Base, TenantMixin):
    __tablename__ = "funnel_order_items"
    __table_args__ = (
        CheckConstraint("quantity >= 1", name="ck_order_item_quantity_positive"),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("funnel_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("digital_products.id"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="THB", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    order: Mapped["FunnelOrder"] = relationship("FunnelOrder", back_populates="items")
    product: Mapped["DigitalProduct"] = relationship(
        "DigitalProduct", back_populates="order_items"
    )


class DeliveryAccess(Base, TenantMixin):
    __tablename__ = "delivery_accesses"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'expired', 'revoked')",
            name="ck_delivery_access_status",
        ),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("funnel_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("digital_products.id"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("delivery_assets.id"), index=True
    )
    contact_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("contacts.id"), index=True
    )
    access_token_hash: Mapped[str | None] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_downloads: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    order: Mapped["FunnelOrder"] = relationship(
        "FunnelOrder", back_populates="delivery_accesses"
    )
    asset: Mapped["DeliveryAsset"] = relationship(
        "DeliveryAsset", back_populates="delivery_accesses"
    )


class ConversionEvent(Base, TenantMixin):
    __tablename__ = "conversion_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('page_view', 'lead_capture', 'checkout_start', 'checkout_success', 'purchase', 'delivery_opened')",
            name="ck_conversion_event_type",
        ),
        Index("ix_conversion_events_occurred_at", "occurred_at"),
        Index(
            "ix_conversion_events_org_type_occurred",
            "organization_id",
            "event_type",
            "occurred_at",
        ),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    product_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("digital_products.id"), index=True
    )
    contact_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("contacts.id"), index=True
    )
    order_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("funnel_orders.id"), index=True
    )
    session_id: Mapped[str | None] = mapped_column(String(255), index=True)
    source: Mapped[str | None] = mapped_column(String(100))
    medium: Mapped[str | None] = mapped_column(String(100))
    campaign: Mapped[str | None] = mapped_column(String(100))
    referrer: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LeadMagnet(Base, TenantMixin):
    __tablename__ = "funnel_lead_magnets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_lead_magnet_status",
        ),
        CheckConstraint(
            "opt_in_count >= 0", name="ck_lead_magnet_opt_in_count_non_negative"
        ),
        Index(
            "ix_funnel_lead_magnets_org_slug", "organization_id", "slug", unique=True
        ),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    target_product_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("digital_products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    promise: Mapped[str | None] = mapped_column(Text)
    file_url: Mapped[str | None] = mapped_column(String(500))
    landing_page_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    opt_in_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    target_product: Mapped["DigitalProduct"] = relationship(
        "DigitalProduct", lazy="selectin"
    )


class Coupon(Base, TenantMixin):
    """Automated discount coupons — percentage or fixed amount."""

    __tablename__ = "funnel_coupons"
    __table_args__ = (
        CheckConstraint(
            "coupon_type IN ('percentage', 'fixed')",
            name="ck_coupon_type",
        ),
        CheckConstraint(
            "status IN ('active', 'expired', 'disabled')",
            name="ck_coupon_status",
        ),
        CheckConstraint("discount_value > 0", name="ck_coupon_discount_positive"),
        Index("ix_funnel_coupons_code", "code", unique=True),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    coupon_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # percentage | fixed
    discount_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="THB", nullable=False)
    min_order_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=0, nullable=False
    )
    max_uses: Mapped[int | None] = mapped_column(Integer)
    used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    product_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("digital_products.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    description: Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProductReview(Base, TenantMixin):
    """Customer reviews — collected automatically after purchase."""

    __tablename__ = "funnel_reviews"
    __table_args__ = (
        CheckConstraint(
            "rating >= 1 AND rating <= 5",
            name="ck_review_rating_range",
        ),
        CheckConstraint(
            "status IN ('pending', 'published', 'hidden')",
            name="ck_review_status",
        ),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("digital_products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("funnel_orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    contact_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
    )
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="published", nullable=False)
    is_verified_purchase: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EmailSequence(Base, TenantMixin):
    """Automated email sequences — welcome, abandoned cart, post-purchase."""

    __tablename__ = "funnel_email_sequences"
    __table_args__ = (
        CheckConstraint(
            "trigger_type IN ('welcome', 'abandoned_cart', 'post_purchase', 'review_request', 'cross_sell', 'win_back')",
            name="ck_email_trigger_type",
        ),
        CheckConstraint(
            "status IN ('active', 'paused', 'draft')",
            name="ck_email_seq_status",
        ),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    delay_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    subject_template: Mapped[str] = mapped_column(String(500), nullable=False)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    product_id: Mapped[UUIDType | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("digital_products.id", ondelete="SET NULL"),
        nullable=True,
    )
    total_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_opened: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_clicked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BundleDeal(Base, TenantMixin):
    """Product bundles — auto-suggested bundles with discount."""

    __tablename__ = "funnel_bundles"
    __table_args__ = (
        CheckConstraint(
            "discount_type IN ('percentage', 'fixed')",
            name="ck_bundle_discount_type",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive')",
            name="ck_bundle_status",
        ),
    )

    id: Mapped[UUIDType] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    discount_type: Mapped[str] = mapped_column(String(20), nullable=False)
    discount_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    cover_image_url: Mapped[str | None] = mapped_column(Text)
    product_ids: Mapped[list | None] = mapped_column(JSONB, default=list)
    sales_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    badge: Mapped[str | None] = mapped_column(String(50))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
