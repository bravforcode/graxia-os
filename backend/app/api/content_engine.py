"""Content Engine API routes for the APEX funnel pipeline."""
import asyncio
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.models.content_engine import (
    AffiliateClick,
    AffiliateProgram,
    ContentArticle,
    ContentKeyword,
    RevenueSnapshot,
)
from app.models.user import User
from app.schemas.content_engine import (
    AffiliateClickList,
    AffiliateClickOut,       # Fix: was missing → NameError in list_affiliate_clicks
    AffiliateProgramCreate,
    AffiliateProgramList,
    AffiliateProgramOut,
    AffiliateProgramPatch,
    ApproveArticlePayload,
    ContentArticleCreate,
    ContentArticleList,
    ContentArticleOut,
    ContentArticlePatch,
    ContentEngineStats,
    ContentKeywordCreate,
    ContentKeywordList,
    ContentKeywordOut,
    ContentKeywordPatch,
    RevenueSnapshotList,
    RevenueSnapshotOut,
)

router = APIRouter(prefix="/content", tags=["content_engine"])
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user_from_token)]


# =============================================================================
# Keywords
# =============================================================================
@router.get("/keywords", response_model=ContentKeywordList)
async def list_keywords(
    db: DbSession,
    site: str | None = Query(None, pattern="^(site_a|site_b)$"),
    status: str | None = Query(None, pattern="^(pending|draft|review|approved|published|archived|failed)$"),
    language: str | None = Query(None, pattern="^(en|th)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ContentKeywordList:
    query = select(ContentKeyword)
    if site:
        query = query.where(ContentKeyword.site == site)
    if status:
        query = query.where(ContentKeyword.status == status)
    if language:
        query = query.where(ContentKeyword.language == language)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    query = query.order_by(desc(ContentKeyword.priority), desc(ContentKeyword.created_at))
    result = await db.execute(query.limit(limit).offset(offset))
    items = [ContentKeywordOut.model_validate(row) for row in result.scalars().all()]
    return ContentKeywordList(total=int(total or 0), items=items)


@router.post("/keywords", response_model=ContentKeywordOut, status_code=201)
async def create_keyword(db: DbSession, payload: ContentKeywordCreate) -> ContentKeywordOut:
    row = ContentKeyword(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return ContentKeywordOut.model_validate(row)


@router.post("/keywords/batch", response_model=list[ContentKeywordOut], status_code=201)
async def batch_create_keywords(
    db: DbSession, payloads: list[ContentKeywordCreate]
) -> list[ContentKeywordOut]:
    rows = [ContentKeyword(**p.model_dump()) for p in payloads]
    db.add_all(rows)
    await db.commit()
    for r in rows:
        await db.refresh(r)
    return [ContentKeywordOut.model_validate(r) for r in rows]


@router.get("/keywords/{keyword_id}", response_model=ContentKeywordOut)
async def get_keyword(keyword_id: UUID, db: DbSession) -> ContentKeywordOut:
    row = await db.get(ContentKeyword, str(keyword_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Keyword not found")
    return ContentKeywordOut.model_validate(row)


@router.patch("/keywords/{keyword_id}", response_model=ContentKeywordOut)
async def patch_keyword(keyword_id: UUID, db: DbSession, payload: ContentKeywordPatch) -> ContentKeywordOut:
    row = await db.get(ContentKeyword, str(keyword_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Keyword not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return ContentKeywordOut.model_validate(row)


@router.delete("/keywords/{keyword_id}", status_code=204)
async def delete_keyword(keyword_id: UUID, db: DbSession) -> None:
    row = await db.get(ContentKeyword, str(keyword_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Keyword not found")
    await db.delete(row)
    await db.commit()


# =============================================================================
# Articles
# =============================================================================
@router.get("/articles", response_model=ContentArticleList)
async def list_articles(
    db: DbSession,
    site: str | None = Query(None, pattern="^(site_a|site_b)$"),
    # Fix: added 'processing' to match new STATUS_CHOICES in model
    status: str | None = Query(None, pattern="^(pending|processing|draft|review|approved|published|archived|failed)$"),
    language: str | None = Query(None, pattern="^(en|th)$"),
    # Fix: 'since' param for incremental sync (used by sync_articles.mjs)
    since: datetime | None = Query(None, description="ISO 8601 — return articles updated after this time"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ContentArticleList:
    query = select(ContentArticle)
    if site:
        query = query.where(ContentArticle.site == site)
    if status:
        query = query.where(ContentArticle.status == status)
    if language:
        query = query.where(ContentArticle.language == language)
    if since:
        query = query.where(ContentArticle.last_updated >= since)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    query = query.order_by(desc(ContentArticle.created_at))
    result = await db.execute(query.limit(limit).offset(offset))
    items = [ContentArticleOut.model_validate(row) for row in result.scalars().all()]
    return ContentArticleList(total=int(total or 0), items=items)


@router.post("/articles", response_model=ContentArticleOut, status_code=201)
async def create_article(db: DbSession, payload: ContentArticleCreate) -> ContentArticleOut:
    row = ContentArticle(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return ContentArticleOut.model_validate(row)


@router.get("/articles/{article_id}", response_model=ContentArticleOut)
async def get_article(article_id: UUID, db: DbSession) -> ContentArticleOut:
    row = await db.get(ContentArticle, str(article_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return ContentArticleOut.model_validate(row)


@router.patch("/articles/{article_id}", response_model=ContentArticleOut)
async def patch_article(article_id: UUID, db: DbSession, payload: ContentArticlePatch) -> ContentArticleOut:
    row = await db.get(ContentArticle, str(article_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.last_updated = datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    return ContentArticleOut.model_validate(row)


@router.patch("/articles/{article_id}/approve", response_model=ContentArticleOut)
async def approve_article(
    article_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
    payload: ApproveArticlePayload | None = None,
) -> ContentArticleOut:
    row = await db.get(ContentArticle, str(article_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    row.status = "approved"
    row.reviewed_by = current_user.email  # Fixed: was hardcoded "system"
    if payload and payload.review_notes:
        row.review_notes = payload.review_notes
    await db.commit()
    await db.refresh(row)
    return ContentArticleOut.model_validate(row)


@router.patch("/articles/{article_id}/reject", response_model=ContentArticleOut)
async def reject_article(
    article_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
    payload: ApproveArticlePayload | None = None,
) -> ContentArticleOut:
    row = await db.get(ContentArticle, str(article_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    row.status = "archived"
    row.reviewed_by = current_user.email  # Fixed: was hardcoded "system"
    if payload and payload.review_notes:
        row.review_notes = f"Rejected: {payload.review_notes}"
    await db.commit()
    await db.refresh(row)
    return ContentArticleOut.model_validate(row)


@router.post("/articles/{article_id}/publish", response_model=ContentArticleOut)
async def publish_article(article_id: UUID, db: DbSession) -> ContentArticleOut:
    row = await db.get(ContentArticle, str(article_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    # Security Fix: removed 'draft' — article MUST be approved first to prevent bypass
    if row.status != "approved":
        raise HTTPException(
            status_code=409,
            detail=f"Article must be approved before publishing (current: '{row.status}')",
        )
    row.status = "published"
    row.published_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    return ContentArticleOut.model_validate(row)


# =============================================================================
# Affiliate Programs
# =============================================================================
@router.get("/affiliate-programs", response_model=AffiliateProgramList)
async def list_affiliate_programs(
    db: DbSession,
    site: str | None = Query(None, pattern="^(site_a|site_b)$"),
    status: str | None = Query(None, pattern="^(active|paused|broken)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> AffiliateProgramList:
    query = select(AffiliateProgram)
    if site:
        query = query.where(AffiliateProgram.site == site)
    if status:
        query = query.where(AffiliateProgram.status == status)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(query.order_by(AffiliateProgram.name).limit(limit).offset(offset))
    items = [AffiliateProgramOut.model_validate(row) for row in result.scalars().all()]
    return AffiliateProgramList(total=int(total or 0), items=items)


@router.post("/affiliate-programs", response_model=AffiliateProgramOut, status_code=201)
async def create_affiliate_program(
    db: DbSession, payload: AffiliateProgramCreate
) -> AffiliateProgramOut:
    row = AffiliateProgram(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return AffiliateProgramOut.model_validate(row)


@router.get("/affiliate-programs/{program_id}", response_model=AffiliateProgramOut)
async def get_affiliate_program(program_id: UUID, db: DbSession) -> AffiliateProgramOut:
    row = await db.get(AffiliateProgram, str(program_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Affiliate program not found")
    return AffiliateProgramOut.model_validate(row)


@router.patch("/affiliate-programs/{program_id}", response_model=AffiliateProgramOut)
async def patch_affiliate_program(
    program_id: UUID, db: DbSession, payload: AffiliateProgramPatch
) -> AffiliateProgramOut:
    row = await db.get(AffiliateProgram, str(program_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Affiliate program not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return AffiliateProgramOut.model_validate(row)


@router.delete("/affiliate-programs/{program_id}", status_code=204)
async def delete_affiliate_program(program_id: UUID, db: DbSession) -> None:
    row = await db.get(AffiliateProgram, str(program_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Affiliate program not found")
    await db.delete(row)
    await db.commit()


# =============================================================================
# Affiliate Clicks
# =============================================================================
@router.get("/affiliate-clicks", response_model=AffiliateClickList)
async def list_affiliate_clicks(
    db: DbSession,
    site: str | None = Query(None, pattern="^(site_a|site_b)$"),
    program_slug: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> AffiliateClickList:
    query = select(AffiliateClick)
    if site:
        query = query.where(AffiliateClick.site == site)
    if program_slug:
        query = query.where(AffiliateClick.program_slug == program_slug)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(query.order_by(desc(AffiliateClick.clicked_at)).limit(limit).offset(offset))
    items = [AffiliateClickOut.model_validate(row) for row in result.scalars().all()]
    return AffiliateClickList(total=int(total or 0), items=items)


# =============================================================================
# Revenue Snapshots
# =============================================================================
@router.get("/revenue", response_model=RevenueSnapshotList)
async def list_revenue_snapshots(
    db: DbSession,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=365),
    offset: int = Query(0, ge=0),
) -> RevenueSnapshotList:
    since = datetime.now(UTC) - timedelta(days=days)
    query = select(RevenueSnapshot).where(RevenueSnapshot.date >= since)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(query.order_by(desc(RevenueSnapshot.date)).limit(limit).offset(offset))
    items = [RevenueSnapshotOut.model_validate(row) for row in result.scalars().all()]
    return RevenueSnapshotList(total=int(total or 0), items=items)


# =============================================================================
# Unified Stats — serves both ContentEngine.tsx (flat dict) and internal callers
# Fix: merged duplicate @router.get("/stats") — FastAPI silently dropped the 2nd
# =============================================================================
@router.get("/stats")
async def get_stats(db: DbSession) -> dict:
    """Unified stats endpoint. All DB queries run in parallel via asyncio.gather."""
    now = datetime.now(UTC)
    thirty_days_ago = now - timedelta(days=30)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    (
        total_keywords,
        pending_keywords,
        draft_articles,
        approved_articles,
        published_articles,
        articles_today,
        active_programs,
        clicks_30d,
        revenue_30d,
    ) = await asyncio.gather(
        db.scalar(select(func.count(ContentKeyword.id))),
        db.scalar(select(func.count(ContentKeyword.id)).where(ContentKeyword.status == "pending")),
        db.scalar(select(func.count(ContentArticle.id)).where(ContentArticle.status == "draft")),
        db.scalar(select(func.count(ContentArticle.id)).where(ContentArticle.status == "approved")),
        db.scalar(select(func.count(ContentArticle.id)).where(ContentArticle.status == "published")),
        db.scalar(select(func.count(ContentArticle.id)).where(ContentArticle.created_at >= today_start)),
        db.scalar(select(func.count(AffiliateProgram.id)).where(AffiliateProgram.status == "active")),
        db.scalar(select(func.count(AffiliateClick.id)).where(AffiliateClick.clicked_at >= thirty_days_ago)),
        db.scalar(select(func.sum(RevenueSnapshot.total_revenue)).where(RevenueSnapshot.date >= thirty_days_ago)),
    )

    return {
        # Flat shape for ContentEngine.tsx
        "published_articles":      int(published_articles or 0),
        "pending_review":          int(draft_articles or 0),
        "traffic_30d":             0,   # wire to PostHog/GA later
        "clicks_30d":              int(clicks_30d or 0),
        "revenue_30d":             float(revenue_30d or 0),
        # Extended fields for internal/admin callers
        "total_keywords":          int(total_keywords or 0),
        "pending_keywords":        int(pending_keywords or 0),
        "approved_articles":       int(approved_articles or 0),
        "articles_today":          int(articles_today or 0),
        "active_affiliate_programs": int(active_programs or 0),
    }


# =============================================================================
# Generation & Publish Triggers
# =============================================================================
class GenerateRequest(BaseModel):
    keyword_id: UUID | None = None
    keyword: str | None = None
    site: str = "site_a"
    language: str = "en"


class PublishRequest(BaseModel):
    article_id: UUID


@router.post("/generate", status_code=202)
async def trigger_generation(db: DbSession, req: GenerateRequest) -> dict:
    """Queue an article generation job. Returns immediately (async Celery).

    Fix: status set to 'pending' (not 'draft') before dispatch so the Celery
    task's own status flow (pending → processing → draft/failed) is correct.
    Setting 'draft' here would make the Redis lock check in the task see an
    unexpected state and behave unpredictably.
    """
    from app.tasks.content_engine_tasks import generate_article_task

    if req.keyword_id:
        kw = await db.get(ContentKeyword, str(req.keyword_id))
        if kw is None:
            raise HTTPException(status_code=404, detail="Keyword not found")
        kw.status = "pending"  # Fix: was "draft" — let the task own the status transition
        await db.commit()
        generate_article_task.delay(keyword_id=str(req.keyword_id))
        return {"status": "queued", "keyword_id": str(req.keyword_id)}

    # Create ad-hoc keyword if no ID provided
    kw = ContentKeyword(
        keyword=req.keyword or "untitled",
        site=req.site,
        language=req.language,
        status="pending",  # Fix: was "draft"
    )
    db.add(kw)
    await db.commit()
    await db.refresh(kw)
    generate_article_task.delay(keyword_id=str(kw.id))
    return {"status": "queued", "keyword_id": str(kw.id)}


@router.post("/publish", status_code=202)
async def trigger_publish(db: DbSession, req: PublishRequest) -> dict:
    """Queue a publish job for an approved article."""
    from app.tasks.content_engine_tasks import publish_article_task

    article = await db.get(ContentArticle, str(req.article_id))
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    if article.status not in ("approved", "published"):
        raise HTTPException(status_code=409, detail="Article must be approved or already published")

    publish_article_task.delay(article_id=str(req.article_id))
    return {"status": "queued", "article_id": str(req.article_id)}
