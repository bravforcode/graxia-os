"""
Revenue OS Models
All SQLAlchemy models for Revenue OS v10 integrated with Graxia OS
Enterprise-grade with idempotency, audit trails, and RLS support
"""
from datetime import datetime
from typing import Optional, List
from uuid import uuid4
from decimal import Decimal

from sqlalchemy import (
    Column, String, Integer, Numeric, Text, DateTime, Date, Boolean,
    ForeignKey, UniqueConstraint, Index, CheckConstraint, JSON, Float,
    Enum as SAEnum, func
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Import Base from existing Graxia database (single source of truth)
from graxia.database import Base

from .enums import (
    OrderStatus, DeliveryStatus, ProductStatus, ProductType,
    LeadStatus, ContentStatus, ApprovalStatus, EmailStatus,
    CampaignStatus, IncidentSeverity, RefundStatus, LedgerEntryType,
    AgentType, BWCPMessageType,
)


# ══════════════════════════════════════════════════════════════════
# FINANCIAL CORE MODELS
# ══════════════════════════════════════════════════════════════════

class Order(Base):
    """
    Order records - idempotent via (platform, platform_order_id) unique constraint
    """
    __tablename__ = "revenue_os_orders"
    __table_args__ = (
        UniqueConstraint("platform", "platform_order_id", name="uq_orders_platform_order"),
        UniqueConstraint("idempotency_key", name="uq_orders_idempotency_key"),
        Index("ix_orders_customer_email", "customer_email"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_created_at", "created_at"),
        Index("ix_orders_product_status", "product_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)  # "stripe" | "gumroad" | "manual"
    platform_order_id: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)

    customer_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_customers.id"))
    customer_email: Mapped[str] = mapped_column(String(320), nullable=False)
    customer_name: Mapped[Optional[str]] = mapped_column(String(255))

    product_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_products.id"), nullable=False)

    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="THB")

    status: Mapped[OrderStatus] = mapped_column(SAEnum(OrderStatus), default=OrderStatus.PENDING)
    saga_state: Mapped[Optional[str]] = mapped_column(String(100), default="created")

    stripe_payment_intent: Mapped[Optional[str]] = mapped_column(String(255))
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LedgerEntry(Base):
    """
    Append-only financial ledger - never UPDATE, only INSERT
    """
    __tablename__ = "revenue_os_ledger_entries"
    __table_args__ = (
        CheckConstraint("amount_cents != 0", name="ck_ledger_nonzero"),
        Index("ix_ledger_order_id", "order_id"),
        Index("ix_ledger_entry_type", "entry_type"),
        Index("ix_ledger_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_orders.id"), nullable=False)
    entry_type: Mapped[LedgerEntryType] = mapped_column(SAEnum(LedgerEntryType))
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="THB")
    description: Mapped[Optional[str]] = mapped_column(Text)
    stripe_balance_transaction_id: Mapped[Optional[str]] = mapped_column(String(255))
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Refund(Base):
    """
    Refund events
    """
    __tablename__ = "revenue_os_refunds"
    __table_args__ = (
        UniqueConstraint("platform", "platform_refund_id", name="uq_refund_platform_refund_id"),
        Index("ix_refunds_order_id", "order_id"),
        Index("ix_refund_order_status", "order_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_orders.id"), nullable=False)
    customer_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_customers.id"))

    platform: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    platform_refund_id: Mapped[Optional[str]] = mapped_column(String(255))

    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="THB")
    reason: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[RefundStatus] = mapped_column(SAEnum(RefundStatus), default=RefundStatus.PROCESSED)

    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Entitlement(Base):
    """
    Customer entitlements/access grants
    """
    __tablename__ = "revenue_os_entitlements"
    __table_args__ = (
        Index("ix_entitlements_customer_email", "customer_email"),
        Index("ix_entitlements_product_key", "product_key"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_orders.id"), nullable=False)
    customer_email: Mapped[str] = mapped_column(String(320), nullable=False)
    product_key: Mapped[str] = mapped_column(String(255), nullable=False)

    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)


# ══════════════════════════════════════════════════════════════════
# PRODUCT & CUSTOMER MODELS
# ══════════════════════════════════════════════════════════════════

class Product(Base):
    """
    Digital products and services
    """
    __tablename__ = "revenue_os_products"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_products_slug"),
        Index("ix_products_status", "status"),
        Index("ix_products_type", "type"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[ProductType] = mapped_column(SAEnum(ProductType), default=ProductType.LOW_TICKET)

    price_cents: Mapped[Optional[int]] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="THB")
    status: Mapped[ProductStatus] = mapped_column(SAEnum(ProductStatus), default=ProductStatus.IDEA)

    promise: Mapped[Optional[str]] = mapped_column(Text)
    target_audience: Mapped[Optional[str]] = mapped_column(Text)
    pain_points: Mapped[Optional[str]] = mapped_column(Text)
    deliverables: Mapped[Optional[str]] = mapped_column(Text)

    stripe_price_id: Mapped[Optional[str]] = mapped_column(String(255))
    stripe_payment_link_url: Mapped[Optional[str]] = mapped_column(String(500))
    gumroad_url: Mapped[Optional[str]] = mapped_column(String(500))

    fulfillment_url: Mapped[Optional[str]] = mapped_column(String(1000))
    fulfillment_instructions: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Customer(Base):
    """
    Customer records
    """
    __tablename__ = "revenue_os_customers"
    __table_args__ = (
        UniqueConstraint("email", name="uq_customers_email"),
        Index("ix_customers_stripe_id", "stripe_customer_id"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255))

    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(255))
    total_spent_cents: Mapped[int] = mapped_column(Integer, default=0)

    first_purchase_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_purchase_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    tags: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())



# ══════════════════════════════════════════════════════════════════
# LEAD & CAMPAIGN MODELS
# ══════════════════════════════════════════════════════════════════

class Lead(Base):
    """
    Lead records with scoring
    """
    __tablename__ = "revenue_os_leads"
    __table_args__ = (
        UniqueConstraint("email", name="uq_leads_email"),
        Index("ix_leads_status", "status"),
        Index("ix_leads_score", "score"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255))

    source: Mapped[Optional[str]] = mapped_column(String(100))
    lead_magnet_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_lead_magnets.id"))

    tags: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    score_rationale: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[LeadStatus] = mapped_column(SAEnum(LeadStatus), default=LeadStatus.NEW)

    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LeadMagnet(Base):
    """
    Lead magnets (free offers)
    """
    __tablename__ = "revenue_os_lead_magnets"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_lead_magnets_slug"),
        CheckConstraint("opt_in_count >= 0", name="ck_lead_magnets_opt_in_count_non_negative"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)

    target_product_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_products.id"))
    promise: Mapped[Optional[str]] = mapped_column(Text)
    file_url: Mapped[Optional[str]] = mapped_column(String(500))
    landing_page_url: Mapped[Optional[str]] = mapped_column(String(500))

    status: Mapped[str] = mapped_column(String(50), default="draft")
    opt_in_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LeadEvent(Base):
    """
    Lead activity tracking
    """
    __tablename__ = "revenue_os_lead_events"
    __table_args__ = (
        UniqueConstraint("event", "email", "event_id", name="uq_lead_event_public_id"),
        Index("ix_lead_events_lead_created", "lead_id", "created_at"),
        Index("ix_lead_events_email_event", "email", "event"),
        Index("ix_lead_events_event_id", "event_id"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    lead_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_leads.id", ondelete="CASCADE"))
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    event: Mapped[str] = mapped_column(String(100), nullable=False)
    event_id: Mapped[Optional[str]] = mapped_column(String(255))

    source: Mapped[Optional[str]] = mapped_column(String(100))
    content_post_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_content_posts.id"))
    product_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_products.id"))

    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RevenueCampaign(Base):
    """
    Revenue campaigns with budget tracking
    """
    __tablename__ = "revenue_os_campaigns"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_revenue_campaign_slug"),
        Index("ix_campaign_status_product", "status", "product_id"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_products.id"))

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[CampaignStatus] = mapped_column(SAEnum(CampaignStatus), default=CampaignStatus.DRAFT)

    objective: Mapped[str] = mapped_column(String(100), default="lead_to_sale")
    target_audience: Mapped[Optional[str]] = mapped_column(Text)
    offer_angle: Mapped[Optional[str]] = mapped_column(Text)
    primary_cta: Mapped[Optional[str]] = mapped_column(Text)

    utm_source: Mapped[Optional[str]] = mapped_column(String(100))
    utm_medium: Mapped[Optional[str]] = mapped_column(String(100))
    utm_campaign: Mapped[Optional[str]] = mapped_column(String(150))

    budget_cents: Mapped[int] = mapped_column(Integer, default=0)
    spend_cents: Mapped[int] = mapped_column(Integer, default=0)
    target_revenue_cents: Mapped[int] = mapped_column(Integer, default=0)
    actual_revenue_cents: Mapped[int] = mapped_column(Integer, default=0)

    guardrails: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    metrics: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    paused_reason: Mapped[Optional[str]] = mapped_column(Text)

    start_date: Mapped[Optional[datetime]] = mapped_column(Date)
    end_date: Mapped[Optional[datetime]] = mapped_column(Date)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AttributionEvent(Base):
    """
    Attribution tracking for campaigns
    """
    __tablename__ = "revenue_os_attribution_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_attribution_event_id"),
        Index("ix_attribution_campaign_event", "campaign_id", "event_type"),
        Index("ix_attribution_source_created", "source", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)

    campaign_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_campaigns.id"))
    product_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_products.id"))
    content_post_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_content_posts.id"))
    lead_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_leads.id"))
    customer_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_customers.id"))
    order_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_orders.id"))

    source: Mapped[Optional[str]] = mapped_column(String(100))
    medium: Mapped[Optional[str]] = mapped_column(String(100))
    campaign: Mapped[Optional[str]] = mapped_column(String(150))

    value_cents: Mapped[int] = mapped_column(Integer, default=0)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RevenueExperiment(Base):
    """
    A/B testing experiments
    """
    __tablename__ = "revenue_os_experiments"
    __table_args__ = (
        Index("ix_experiment_campaign_status", "campaign_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    campaign_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_campaigns.id"))
    product_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_products.id"))

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)

    variant_a: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    variant_b: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    success_metric: Mapped[str] = mapped_column(String(100), default="paid_conversion_rate")
    status: Mapped[str] = mapped_column(String(50), default="draft")
    result: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())



# ══════════════════════════════════════════════════════════════════
# CONTENT & APPROVAL MODELS
# ══════════════════════════════════════════════════════════════════

class ContentIdea(Base):
    """
    Content ideas for marketing
    """
    __tablename__ = "revenue_os_content_ideas"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), default="tiktok")

    hook: Mapped[Optional[str]] = mapped_column(Text)
    angle: Mapped[Optional[str]] = mapped_column(Text)

    target_product_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_products.id"))
    score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[ContentStatus] = mapped_column(SAEnum(ContentStatus), default=ContentStatus.IDEA)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContentPost(Base):
    """
    Published content posts
    """
    __tablename__ = "revenue_os_content_posts"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    content_idea_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_content_ideas.id"))

    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255))
    script: Mapped[Optional[str]] = mapped_column(Text)
    caption: Mapped[Optional[str]] = mapped_column(Text)
    cta: Mapped[Optional[str]] = mapped_column(Text)
    hashtags: Mapped[Optional[str]] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(50), default="draft")
    post_url: Mapped[Optional[str]] = mapped_column(String(500))

    views: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    leads: Mapped[int] = mapped_column(Integer, default=0)
    sales: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Approval(Base):
    """
    Human approval workflow
    """
    __tablename__ = "revenue_os_approvals"
    __table_args__ = (
        Index("ix_approvals_status", "status"),
        Index("ix_approvals_item_type_id", "object_type", "object_id"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    object_type: Mapped[str] = mapped_column(String(100), nullable=False)
    object_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    product_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_products.id", ondelete="SET NULL"))
    content_post_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_content_posts.id", ondelete="SET NULL"))
    ai_draft_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_ai_drafts.id", ondelete="SET NULL"))

    title: Mapped[Optional[str]] = mapped_column(String(255))
    preview: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[ApprovalStatus] = mapped_column(SAEnum(ApprovalStatus), default=ApprovalStatus.PENDING)

    requested_by_agent: Mapped[Optional[str]] = mapped_column(String(100))
    ceo_notes: Mapped[Optional[str]] = mapped_column(Text)
    reason: Mapped[Optional[str]] = mapped_column(Text)

    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AIDraft(Base):
    """
    AI-generated drafts
    """
    __tablename__ = "revenue_os_ai_drafts"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    draft_type: Mapped[str] = mapped_column(String(100), nullable=False)

    object_type: Mapped[Optional[str]] = mapped_column(String(100))
    object_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True))

    lead_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_leads.id"))
    campaign_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_campaigns.id"))

    prompt_summary: Mapped[Optional[str]] = mapped_column(Text)
    output: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(998))

    model_used: Mapped[Optional[str]] = mapped_column(String(100))
    anthropic_model: Mapped[Optional[str]] = mapped_column(String(100))
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer)

    approval_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_approvals.id"))
    approval_status: Mapped[str] = mapped_column(String(50), default="pending_approval")

    generated_by_agent: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ══════════════════════════════════════════════════════════════════
# EMAIL & DELIVERY MODELS
# ══════════════════════════════════════════════════════════════════

class EmailOutbox(Base):
    """
    Email queue with retry logic
    """
    __tablename__ = "revenue_os_email_outbox"
    __table_args__ = (
        Index("ix_email_outbox_status", "status"),
        UniqueConstraint("email_key", name="uq_email_outbox_email_key"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    order_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_orders.id"))
    customer_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_customers.id"))

    email_key: Mapped[Optional[str]] = mapped_column(String(255))
    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    to_name: Mapped[Optional[str]] = mapped_column(String(255))

    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    html_body: Mapped[Optional[str]] = mapped_column(Text)
    text_body: Mapped[Optional[str]] = mapped_column(Text)

    from_email: Mapped[Optional[str]] = mapped_column(String(320))
    reply_to: Mapped[Optional[str]] = mapped_column(String(320))

    approval_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_approvals.id"))
    status: Mapped[EmailStatus] = mapped_column(SAEnum(EmailStatus), default=EmailStatus.PENDING)

    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    resend_message_id: Mapped[Optional[str]] = mapped_column(String(255))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DeliveryEvent(Base):
    """
    Product delivery tracking
    """
    __tablename__ = "revenue_os_delivery_events"
    __table_args__ = (
        Index("ix_delivery_order_type", "order_id", "event_type"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_orders.id"), nullable=False)
    customer_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_customers.id"))

    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    delivery_type: Mapped[Optional[str]] = mapped_column(String(100))
    channel: Mapped[str] = mapped_column(String(50), default="delivery_page")
    status: Mapped[DeliveryStatus] = mapped_column(SAEnum(DeliveryStatus), default=DeliveryStatus.QUEUED)

    email_outbox_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_email_outbox.id"))
    message: Mapped[Optional[str]] = mapped_column(Text)

    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[Optional[str]] = mapped_column(Text)

    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())



# ══════════════════════════════════════════════════════════════════
# AUTOMATION & INCIDENT MODELS
# ══════════════════════════════════════════════════════════════════

class AutomationLock(Base):
    """
    Distributed locks for Celery tasks
    """
    __tablename__ = "revenue_os_automation_locks"
    __table_args__ = (
        Index("ix_locks_expires_at", "locked_until"),
    )

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    owner: Mapped[str] = mapped_column(String(100), nullable=False)
    locked_by_worker: Mapped[Optional[str]] = mapped_column(String(255))

    locked_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AutomationRun(Base):
    """
    Automation execution logs
    """
    __tablename__ = "revenue_os_automation_runs"
    __table_args__ = (
        Index("ix_automation_run_type_status", "run_type", "status"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    run_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="running")

    summary: Mapped[Optional[str]] = mapped_column(Text)
    metrics: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class IncidentEvent(Base):
    """
    System incidents and alerts
    """
    __tablename__ = "revenue_os_incident_events"
    __table_args__ = (
        Index("ix_incidents_severity", "severity"),
        Index("ix_incidents_created_at", "created_at"),
        Index("ix_incident_status_severity", "status", "severity"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    severity: Mapped[IncidentSeverity] = mapped_column(SAEnum(IncidentSeverity), default=IncidentSeverity.LOW)
    status: Mapped[str] = mapped_column(String(50), default="open")  # open, mitigated, resolved

    source_agent: Mapped[Optional[str]] = mapped_column(String(100))
    source: Mapped[Optional[str]] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    message: Mapped[Optional[str]] = mapped_column(Text)

    affected_campaign_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_campaigns.id"))
    affected_order_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_orders.id"))

    bwcp_message_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True))
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WebhookEvent(Base):
    """
    Webhook event log (Stripe, Gumroad, etc.)
    """
    __tablename__ = "revenue_os_webhook_events"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),
        UniqueConstraint("platform", "platform_event_id", name="uq_webhook_platform_event"),
        Index("ix_webhook_events_processed", "processed"),
        Index("ix_webhook_events_platform_event", "platform", "event_type"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    platform: Mapped[Optional[str]] = mapped_column(String(50))
    platform_event_id: Mapped[Optional[str]] = mapped_column(String(255))

    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[Optional[str]] = mapped_column(String(255))

    status: Mapped[str] = mapped_column(String(50), default="received")
    processed: Mapped[bool] = mapped_column(Boolean, default=False)

    payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    processing_error: Mapped[Optional[str]] = mapped_column(Text)

    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ══════════════════════════════════════════════════════════════════
# METRICS & ANALYTICS MODELS
# ══════════════════════════════════════════════════════════════════

class MetricDaily(Base):
    """
    Daily aggregated metrics
    """
    __tablename__ = "revenue_os_metrics_daily"
    __table_args__ = (
        UniqueConstraint("date", name="uq_metrics_daily_date"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    date: Mapped[datetime] = mapped_column(Date, nullable=False)

    visits: Mapped[int] = mapped_column(Integer, default=0)
    leads: Mapped[int] = mapped_column(Integer, default=0)
    sales: Mapped[int] = mapped_column(Integer, default=0)
    revenue_cents: Mapped[int] = mapped_column(Integer, default=0)

    content_published: Mapped[int] = mapped_column(Integer, default=0)
    email_sent: Mapped[int] = mapped_column(Integer, default=0)
    service_inquiries: Mapped[int] = mapped_column(Integer, default=0)

    conversion_rate: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class StrategyLog(Base):
    """
    Weekly strategy reviews
    """
    __tablename__ = "revenue_os_strategy_logs"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    week_start: Mapped[datetime] = mapped_column(Date, nullable=False)

    summary: Mapped[Optional[str]] = mapped_column(Text)
    what_worked: Mapped[Optional[str]] = mapped_column(Text)
    what_failed: Mapped[Optional[str]] = mapped_column(Text)
    recommendations: Mapped[Optional[str]] = mapped_column(Text)
    top_3_actions: Mapped[Optional[str]] = mapped_column(Text)
    kill_list: Mapped[Optional[str]] = mapped_column(Text)
    double_down_list: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    """
    System audit trail
    """
    __tablename__ = "revenue_os_audit_logs"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)

    object_type: Mapped[Optional[str]] = mapped_column(String(100))
    object_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True))

    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ServiceOffer(Base):
    """
    Service offerings
    """
    __tablename__ = "revenue_os_service_offers"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    price_min_cents: Mapped[Optional[int]] = mapped_column(Integer)
    price_max_cents: Mapped[Optional[int]] = mapped_column(Integer)

    promise: Mapped[Optional[str]] = mapped_column(Text)
    deliverables: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Task(Base):
    """
    Task management
    """
    __tablename__ = "revenue_os_tasks"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    priority: Mapped[int] = mapped_column(Integer, default=50)
    category: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), default="pending")

    due_date: Mapped[Optional[datetime]] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# ══════════════════════════════════════════════════════════════════
# TRANSACTIONAL OUTBOX (HR-07: Guaranteed Delivery)
# ══════════════════════════════════════════════════════════════════

class OutboxEvent(Base):
    """
    Transactional Outbox for guaranteed event delivery.
    Events are written in same DB transaction as business changes,
    then picked up by Celery workers for reliable delivery.
    """
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_processed_at", "processed_at"),
        Index("ix_outbox_aggregate", "aggregate_type", "aggregate_id"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    headers: Mapped[Optional[dict]] = mapped_column(JSONB)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(255))
    causation_id: Mapped[Optional[str]] = mapped_column(String(255))

    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ══════════════════════════════════════════════════════════════════
# AGENT MESSAGING (BWCP)
# ══════════════════════════════════════════════════════════════════

class BWCPMessage(Base):
    """
    Belief-Will-Can-Plan messages for agent choreography.
    Enables async communication between Visionary, Sales, and ChiefOfStaff agents.
    """
    __tablename__ = "bwcp_messages"
    __table_args__ = (
        Index("ix_bwcp_conversation", "conversation_id", "created_at"),
        Index("ix_bwcp_sender_type", "sender_agent", "message_type"),
        Index("ix_bwcp_delivered", "delivered"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[str] = mapped_column(String(255), nullable=False)

    sender_agent: Mapped[AgentType] = mapped_column(SAEnum(AgentType), nullable=False)
    recipient_agent: Mapped[AgentType] = mapped_column(SAEnum(AgentType), nullable=False)
    message_type: Mapped[BWCPMessageType] = mapped_column(SAEnum(BWCPMessageType), nullable=False)

    # BWCP Structure
    belief: Mapped[Optional[str]] = mapped_column(Text)
    will: Mapped[Optional[str]] = mapped_column(Text)
    can: Mapped[Optional[dict]] = mapped_column(JSONB)
    plan: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Related entities
    campaign_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_campaigns.id"))
    lead_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_leads.id"))
    approval_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_approvals.id"))
    incident_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_incidents.id"))

    # Delivery tracking
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ══════════════════════════════════════════════════════════════════
# LEAD SCORING HISTORY
# ══════════════════════════════════════════════════════════════════

class LeadScoreHistory(Base):
    """
    Immutable history of lead score calculations.
    Tracks what factors contributed to score changes.
    """
    __tablename__ = "lead_score_history"
    __table_args__ = (
        Index("ix_lead_score_history_lead_id", "lead_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    lead_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_leads.id"), nullable=False)

    score: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_score: Mapped[Optional[int]] = mapped_column(Integer)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)

    # Scoring factors
    email_domain_score: Mapped[int] = mapped_column(Integer, default=0)
    source_score: Mapped[int] = mapped_column(Integer, default=0)
    behavior_score: Mapped[int] = mapped_column(Integer, default=0)
    recency_score: Mapped[int] = mapped_column(Integer, default=0)

    # AI analysis
    ai_rationale: Mapped[Optional[str]] = mapped_column(Text)
    ai_model: Mapped[Optional[str]] = mapped_column(String(100))

    # Trigger context
    triggered_by: Mapped[str] = mapped_column(String(100), nullable=False)
    campaign_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_campaigns.id"))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ══════════════════════════════════════════════════════════════════
# PROMPT VERSIONING
# ══════════════════════════════════════════════════════════════════

class PromptVersion(Base):
    """
    Versioned prompt templates for reproducible AI interactions.
    Enables rollback and comparison of prompt effectiveness.
    """
    __tablename__ = "prompt_versions"
    __table_args__ = (
        Index("ix_prompt_version", "prompt_key", "version", unique=True),
        Index("ix_prompt_active", "prompt_key", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    prompt_key: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Content
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    user_template: Mapped[Optional[str]] = mapped_column(Text)
    example_few_shot: Mapped[Optional[list]] = mapped_column(JSONB)

    # Configuration
    model_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    expected_output_schema: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Metadata
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    deprecated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Performance tracking
    total_calls: Mapped[int] = mapped_column(Integer, default=0)
    avg_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    success_rate: Mapped[float] = mapped_column(Float, default=1.0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ══════════════════════════════════════════════════════════════════
# CAMPAIGN BUDGET SNAPSHOT
# ══════════════════════════════════════════════════════════════════

class CampaignBudgetSnapshot(Base):
    """
    Daily snapshots of campaign budget state for analytics.
    Enables budget trend analysis and alerts.
    """
    __tablename__ = "campaign_budget_snapshots"
    __table_args__ = (
        Index("ix_campaign_snapshot_date", "campaign_id", "snapshot_date", unique=True),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    campaign_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_campaigns.id"), nullable=False)
    snapshot_date: Mapped[datetime] = mapped_column(Date, nullable=False)

    # Budget state
    budget_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    spent_cents: Mapped[int] = mapped_column(Integer, default=0)
    remaining_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    # Derived metrics
    spend_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    days_remaining: Mapped[int] = mapped_column(Integer, default=0)
    projected_overrun: Mapped[bool] = mapped_column(Boolean, default=False)

    # Attribution
    attributed_revenue_cents: Mapped[int] = mapped_column(Integer, default=0)
    roas: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ══════════════════════════════════════════════════════════════════
# ATTRIBUTION SUMMARY
# ══════════════════════════════════════════════════════════════════

class AttributionSummary(Base):
    """
    Pre-computed attribution summaries for fast dashboard queries.
    Aggregates AttributionEvent data for reporting.
    """
    __tablename__ = "attribution_summaries"
    __table_args__ = (
        Index("ix_attribution_period", "period_type", "period_start"),
        Index("ix_attribution_campaign", "campaign_id", "period_start"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    period_type: Mapped[str] = mapped_column(String(20), nullable=False)  # day, week, month
    period_start: Mapped[datetime] = mapped_column(Date, nullable=False)
    period_end: Mapped[datetime] = mapped_column(Date, nullable=False)

    campaign_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_campaigns.id"))
    lead_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_os_leads.id"))

    # Attribution metrics
    touchpoints: Mapped[int] = mapped_column(Integer, default=0)
    first_touch_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_touch_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Conversion tracking
    converted: Mapped[bool] = mapped_column(Boolean, default=False)
    converted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    conversion_value_cents: Mapped[int] = mapped_column(Integer, default=0)
    attributed_revenue_cents: Mapped[int] = mapped_column(Integer, default=0)

    # Channel breakdown
    channel_breakdown: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
