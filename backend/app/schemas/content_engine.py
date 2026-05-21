"""Pydantic schemas for the content engine module."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# ContentKeyword schemas
# ---------------------------------------------------------------------------
class ContentKeywordBase(BaseModel):
    keyword: str = Field(..., max_length=500)
    keyword_th: str | None = Field(None, max_length=500)
    site: str = Field(..., pattern="^(site_a|site_b)$")
    language: str = Field("en", pattern="^(en|th)$")
    content_type: str = Field("article", pattern="^(article|review|comparison|listicle|how_to|faq)$")
    search_volume: int | None = None
    keyword_difficulty: int | None = Field(None, ge=0, le=100)
    cpc_usd: Decimal | None = None
    search_intent: str | None = Field(None, max_length=50)
    priority: int = Field(5, ge=1, le=10)


class ContentKeywordCreate(ContentKeywordBase):
    pass


class ContentKeywordOut(ContentKeywordBase):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: UUID
    status: str = "pending"
    retry_count: int = 0
    error_message: str | None = None
    article_id: UUID | None = None
    article_url: str | None = None
    created_at: datetime | None = None
    processed_at: datetime | None = None
    published_at: datetime | None = None


class ContentKeywordList(BaseModel):
    total: int
    items: list[ContentKeywordOut]


class ContentKeywordPatch(BaseModel):
    status: str | None = None
    priority: int | None = Field(None, ge=1, le=10)
    error_message: str | None = None
    article_id: UUID | None = None
    article_url: str | None = None


# ---------------------------------------------------------------------------
# ContentArticle schemas
# ---------------------------------------------------------------------------
class ContentArticleBase(BaseModel):
    site: str = Field(..., pattern="^(site_a|site_b)$")
    slug: str = Field(..., max_length=500)
    title: str = Field(..., max_length=500)
    title_th: str | None = Field(None, max_length=500)
    language: str = Field("en", pattern="^(en|th)$")
    content_type: str = Field("article", pattern="^(article|review|comparison|listicle|how_to|faq)$")
    meta_title: str | None = Field(None, max_length=120)
    meta_description: str | None = Field(None, max_length=300)
    target_keyword: str | None = Field(None, max_length=500)
    secondary_keywords: list[str] | None = None
    schema_type: str | None = Field(None, max_length=50)
    body: str
    hero_image_url: str | None = Field(None, max_length=1024)
    word_count: int | None = None
    reading_time: int | None = None
    affiliate_programs_used: list[str] | None = None


class ContentArticleCreate(ContentArticleBase):
    pass


class ContentArticleOut(ContentArticleBase):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: UUID
    status: str = "draft"
    views_total: int = 0
    views_30d: int = 0
    unique_visitors: int = 0
    avg_time_on_page: Decimal | None = None
    bounce_rate: Decimal | None = None
    search_impressions_30d: int = 0
    search_clicks_30d: int = 0
    avg_search_position: Decimal | None = None
    ctr: Decimal | None = None
    affiliate_clicks: int = 0
    affiliate_revenue: Decimal = Decimal("0.00")
    needs_refresh: bool = False
    reviewed_by: str | None = None
    review_notes: str | None = None
    published_url: str | None = None
    generation_model: str | None = None
    generation_tokens: int | None = None
    generation_cost_usd: Decimal | None = None
    created_at: datetime | None = None
    published_at: datetime | None = None
    last_updated: datetime | None = None


class ContentArticleList(BaseModel):
    total: int
    items: list[ContentArticleOut]


class ContentArticlePatch(BaseModel):
    status: str | None = Field(None, pattern="^(pending|draft|review|approved|published|archived|failed)$")
    title: str | None = Field(None, max_length=500)
    body: str | None = None
    meta_title: str | None = Field(None, max_length=120)
    meta_description: str | None = Field(None, max_length=300)
    hero_image_url: str | None = Field(None, max_length=1024)
    review_notes: str | None = None
    published_url: str | None = Field(None, max_length=1024)
    needs_refresh: bool | None = None


class ApproveArticlePayload(BaseModel):
    review_notes: str | None = None


# ---------------------------------------------------------------------------
# AffiliateProgram schemas
# ---------------------------------------------------------------------------
class AffiliateProgramBase(BaseModel):
    slug: str = Field(..., max_length=100)
    name: str = Field(..., max_length=255)
    network: str | None = Field(None, max_length=100)
    category: str | None = Field(None, max_length=100)
    commission_type: str | None = Field(None, max_length=50)
    commission_value: Decimal | None = None
    cookie_days: int | None = None
    base_url: str = Field(..., max_length=2048)
    dashboard_url: str | None = Field(None, max_length=2048)
    cloaked_path: str | None = Field(None, max_length=500)
    site: str | None = Field(None, pattern="^(site_a|site_b)$")
    trigger_keywords: list[str] | None = None
    cta_text: str | None = Field(None, max_length=500)
    cta_text_th: str | None = Field(None, max_length=500)


class AffiliateProgramCreate(AffiliateProgramBase):
    pass


class AffiliateProgramOut(AffiliateProgramBase):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: UUID
    status: str = "active"
    last_checked: datetime | None = None
    clicks_30d: int = 0
    conversions_30d: int = 0
    revenue_30d: Decimal = Decimal("0.00")
    created_at: datetime | None = None


class AffiliateProgramList(BaseModel):
    total: int
    items: list[AffiliateProgramOut]


class AffiliateProgramPatch(BaseModel):
    status: str | None = Field(None, pattern="^(active|paused|broken)$")
    base_url: str | None = Field(None, max_length=2048)
    commission_value: Decimal | None = None
    trigger_keywords: list[str] | None = None


# ---------------------------------------------------------------------------
# AffiliateClick schemas
# ---------------------------------------------------------------------------
class AffiliateClickOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: UUID
    program_id: UUID | None = None
    program_slug: str
    article_id: UUID | None = None
    article_slug: str | None = None
    site: str | None = None
    country_code: str | None = None
    device_type: str | None = None
    referrer: str | None = None
    clicked_at: datetime | None = None


class AffiliateClickList(BaseModel):
    total: int
    items: list[AffiliateClickOut]


# ---------------------------------------------------------------------------
# RevenueSnapshot schemas
# ---------------------------------------------------------------------------
class RevenueSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: UUID
    date: datetime
    affiliate_revenue: Decimal = Decimal("0.00")
    digital_revenue: Decimal = Decimal("0.00")
    ad_revenue: Decimal = Decimal("0.00")
    store_revenue: Decimal = Decimal("0.00")
    total_revenue: Decimal = Decimal("0.00")
    site_a_revenue: Decimal = Decimal("0.00")
    site_b_revenue: Decimal = Decimal("0.00")
    total_pageviews: int = 0
    total_sessions: int = 0
    new_visitors: int = 0
    new_leads: int = 0
    total_orders: int = 0
    avg_order_value: Decimal | None = None
    articles_published: int = 0
    created_at: datetime | None = None


class RevenueSnapshotList(BaseModel):
    total: int
    items: list[RevenueSnapshotOut]


# ---------------------------------------------------------------------------
# Dashboard / aggregated stats
# ---------------------------------------------------------------------------
class ContentEngineStats(BaseModel):
    total_keywords: int
    pending_keywords: int
    draft_articles: int
    review_articles: int
    approved_articles: int
    published_articles: int
    total_affiliate_programs: int
    active_affiliate_programs: int
    clicks_30d: int
    revenue_30d: Decimal
    articles_today: int
