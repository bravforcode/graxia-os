"""Celery tasks for the content engine pipeline."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.content_engine import ContentArticle, ContentKeyword
from app.services.content_engine_service import (
    compute_content_hash,
    generate_full_article,
    generate_keyword_batch,
)
from app.tasks.base import execute_managed_async_task
from app.tasks.celery_app import celery_app
from app.tasks.queues import DEFAULT_QUEUE

logger = logging.getLogger(__name__)


# =============================================================================
# Async helpers (run inside DB session)
# =============================================================================
async def _generate_article(keyword_id: str) -> dict[str, Any]:
    """Fetch keyword, generate article with AI, save as draft.
    
    Guards:
    - Redis distributed lock: prevents duplicate generation across workers
    - pgvector semantic duplicate check: skips if near-identical article exists
    - Status flow: pending → processing → draft (success) | failed (error)
    """
    # ── Redis Lock: prevent duplicate generation across Celery workers ──────
    try:
        from app.core.redis import redis_client as _redis_factory
        _redis = await _redis_factory.get_client()
        lock_key = f"lock:content:generate:{keyword_id}"
        acquired = await _redis.set(lock_key, "1", nx=True, ex=600)  # 10 min TTL
        if not acquired:
            logger.info("Skipping %s — already processing (Redis lock held)", keyword_id)
            return {"status": "skipped", "reason": "already_processing", "keyword_id": keyword_id}
    except Exception as redis_err:
        # Redis unavailable — log and continue without lock (degraded mode)
        logger.warning("Redis lock unavailable for %s: %s — continuing without lock", keyword_id, redis_err)
        _redis = None
        lock_key = None

    try:
        async with AsyncSessionLocal() as db:
            kw = await db.get(ContentKeyword, keyword_id)
            if kw is None:
                raise ValueError(f"Keyword {keyword_id} not found")

            # ── Bug Fix #3: set 'processing' BEFORE generate, not 'draft' ──
            kw.status = "processing"
            kw.processed_at = datetime.now(UTC)  # Bug Fix #1: was asyncio float
            await db.commit()

            # ── pgvector Duplicate Detection ────────────────────────────────
            try:
                from app.services.vector_search import is_duplicate_article
                is_dup = await is_duplicate_article(kw.keyword, kw.site)
                if is_dup:
                    kw.status = "archived"
                    kw.error_message = "Semantic duplicate detected via pgvector"
                    await db.commit()
                    logger.info("Skipping duplicate keyword: %s (site=%s)", kw.keyword, kw.site)
                    return {"status": "skipped", "reason": "duplicate", "keyword_id": keyword_id}
            except ImportError:
                logger.debug("vector_search service not available — skipping duplicate check")
            except Exception as dup_err:
                logger.warning("Duplicate check failed (non-fatal): %s", dup_err)

            # ── AI Generation ────────────────────────────────────────────────
            try:
                article_data = await generate_full_article(
                    keyword=kw.keyword,
                    site=kw.site,
                    language=kw.language,
                    content_type=kw.content_type or "article",
                )
            except Exception as exc:
                kw.status = "failed"
                kw.error_message = str(exc)
                kw.retry_count += 1
                await db.commit()
                raise

            # ── Persist Draft Article ────────────────────────────────────────
            article = ContentArticle(
                site=kw.site,
                slug=article_data["slug"],
                title=article_data["title"],
                title_th=article_data.get("title_th"),
                language=kw.language,
                content_type=kw.content_type or "article",
                meta_title=article_data.get("meta_title"),
                meta_description=article_data.get("meta_description"),
                target_keyword=kw.keyword,
                secondary_keywords=article_data.get("lsi_keywords", []),
                schema_type=article_data.get("schema_type", "Article"),
                body=article_data["content"],
                word_count=article_data.get("word_count"),
                affiliate_programs_used=article_data.get("affiliate_programs_used", []),
                status="draft",
                content_hash=compute_content_hash(article_data["content"]),
                generation_model="auto",
            )
            db.add(article)
            await db.flush()

            # Bug Fix #3 (cont.): only set 'draft' AFTER successful generation
            kw.article_id = article.id
            kw.status = "draft"
            kw.error_message = None
            await db.commit()

            logger.info(
                "Article draft generated: %s (%s words) for site=%s",
                article.title,
                article.word_count,
                article.site,
            )

            return {
                "status": "draft_created",
                "keyword_id": keyword_id,
                "article_id": str(article.id),
                "title": article.title,
                "word_count": article.word_count,
            }
    finally:
        # Always release the Redis lock, even on exception
        if _redis and lock_key:
            try:
                await _redis.delete(lock_key)
            except Exception:
                pass


async def _publish_article(article_id: str) -> dict[str, Any]:
    """Mark article as published and trigger external site rebuild."""
    async with AsyncSessionLocal() as db:
        article = await db.get(ContentArticle, article_id)
        if article is None:
            raise ValueError(f"Article {article_id} not found")

        if article.status not in ("approved", "published"):
            raise ValueError(f"Cannot publish article in status '{article.status}'")

        article.status = "published"
        from datetime import UTC, datetime
        article.published_at = datetime.now(UTC)

        # Update linked keyword
        if article.target_keyword:
            from sqlalchemy import select
            result = await db.execute(
                select(ContentKeyword).where(
                    ContentKeyword.keyword == article.target_keyword,
                    ContentKeyword.site == article.site,
                )
            )
            linked_kw = result.scalar_one_or_none()
            if linked_kw:
                linked_kw.status = "published"
                linked_kw.published_at = article.published_at
                linked_kw.article_url = article.published_url

        await db.commit()

        # ── Trigger static site rebuild via configured webhook ────────────────
        # Uses settings.SITE_REBUILD_WEBHOOK_MAP (parses SITE_REBUILD_WEBHOOKS env)
        # Set in .env: SITE_REBUILD_WEBHOOKS=site_a=https://...,site_b=https://...
        target_webhook = settings.SITE_REBUILD_WEBHOOK_MAP.get(article.site)
        if target_webhook:
            import httpx
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        target_webhook,
                        timeout=5.0,
                        json={"event": "rebuild", "site": article.site, "article_id": article_id},
                    )
                    logger.info("Rebuild webhook fired for %s → %s", article.site, resp.status_code)
            except Exception as e:
                logger.error("Rebuild webhook failed for %s: %s", article.site, e)
        else:
            logger.debug("No rebuild webhook configured for site=%s (set SITE_REBUILD_WEBHOOKS)", article.site)

        logger.info(
            "Article published: %s (site=%s, lang=%s)",
            article.title,
            article.site,
            article.language,
        )

        return {
            "status": "published",
            "article_id": article_id,
            "title": article.title,
            "site": article.site,
        }


async def _seed_keywords(site: str) -> dict[str, Any]:
    """Generate and insert keyword templates for a site."""
    keywords = generate_keyword_batch(site)
    if not keywords:
        return {"status": "no_keywords", "site": site, "count": 0}

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        existing_q = await db.execute(
            select(ContentKeyword.keyword, ContentKeyword.site)
        )
        existing = {(k.lower(), s) for k, s in existing_q.all()}

        added = 0
        for kw_data in keywords:
            key = (kw_data["keyword"].lower(), kw_data["site"])
            if key in existing:
                continue
            kw = ContentKeyword(
                keyword=kw_data["keyword"],
                site=kw_data["site"],
                language=kw_data.get("language", "en"),
                content_type=kw_data.get("content_type", "article"),
                priority=kw_data.get("priority", 5),
                status="pending",
            )
            db.add(kw)
            added += 1

        await db.commit()

    logger.info("Seeded %d new keywords for site=%s", added, site)
    return {"status": "seeded", "site": site, "count": added}


# =============================================================================
# Celery task definitions
# =============================================================================
@celery_app.task(
    name="tasks.content_engine.generate_article",
    queue=DEFAULT_QUEUE,
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def generate_article_task(self, keyword_id: str) -> dict[str, Any]:
    """Queue an AI article generation from a keyword."""
    try:
        return execute_managed_async_task(
            task_name="content_engine.generate_article",
            queue=DEFAULT_QUEUE,
            coroutine_factory=lambda: _generate_article(keyword_id),
        )
    except Exception as exc:
        logger.warning("Article generation failed for %s: %s", keyword_id, exc)
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@celery_app.task(
    name="tasks.content_engine.publish_article",
    queue=DEFAULT_QUEUE,
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def publish_article_task(self, article_id: str) -> dict[str, Any]:
    """Publish an approved article and trigger site rebuild."""
    try:
        return execute_managed_async_task(
            task_name="content_engine.publish_article",
            queue=DEFAULT_QUEUE,
            coroutine_factory=lambda: _publish_article(article_id),
        )
    except Exception as exc:
        logger.warning("Article publish failed for %s: %s", article_id, exc)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(
    name="tasks.content_engine.seed_keywords",
    queue=DEFAULT_QUEUE,
)
def seed_keywords_task(site: str) -> dict[str, Any]:
    """Batch seed keyword templates for a site."""
    return execute_managed_async_task(
        task_name="content_engine.seed_keywords",
        queue=DEFAULT_QUEUE,
        coroutine_factory=lambda: _seed_keywords(site),
    )
