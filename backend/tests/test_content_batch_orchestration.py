from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.auth.context import AuthContext
from app.models.approval_request import ApprovalRequest
from app.models.content_batch import ContentBatch, ContentBatchItem
from app.models.content_engine import ContentArticle
from app.schemas.content_batch import ContentBatchCreate


def _auth(organization_id):
    return AuthContext(
        organization_id=organization_id,
        permissions=["runtime:write"],
        is_authenticated=True,
    )


def _valid_batch_payload(**overrides):
    values = {
        "topic": "AI workflow systems for small businesses",
        "canonical_url": "https://graxia-os-funnel.vercel.app/guides/ai-workflow-systems",
        "claim_reviewed": True,
        "utm_source": "organic",
        "utm_medium": "content",
        "utm_campaign": "ai-workflow-systems",
        "canary_passed": True,
    }
    values.update(overrides)
    return ContentBatchCreate(**values)


@pytest.mark.asyncio
async def test_batch_api_queues_without_processing(db_session, default_org, monkeypatch):
    from app.api.content_batches import create_content_batch, router

    route = next(route for route in router.routes if route.path == "/content-batches")
    assert route.status_code == 202

    queued = []
    monkeypatch.setattr(
        "app.api.content_batches.enqueue_content_batch",
        lambda batch_id: queued.append(batch_id) or "queue-1",
    )

    result = await create_content_batch(
        _valid_batch_payload(),
        db_session,
        _auth(default_org.id),
        idempotency_key="api-batch-1",
    )

    assert result.status == "queued"
    assert result.queue_id == "queue-1"
    assert result.item_count == 9
    assert len(queued) == 1


def test_batch_composition_is_one_pillar_three_supporting_and_five_shorts():
    from app.services.content_batch_service import compose_batch_items

    items = compose_batch_items(
        topic="AI workflow systems",
        canonical_url="https://graxia-os-funnel.vercel.app/guides/ai-workflow-systems",
        utm_source="organic",
        utm_medium="content",
        utm_campaign="ai-workflow-systems",
    )

    assert len(items) == 9
    assert [item.role for item in items].count("pillar") == 1
    assert [item.role for item in items].count("supporting") == 3
    assert [item.role for item in items].count("short") == 5
    assert len({item.item_key for item in items}) == 9


@pytest.mark.asyncio
async def test_worker_is_idempotent_for_batch_items_and_articles(db_session, default_org):
    from app.services.content_batch_service import process_content_batch

    batch = ContentBatch(
        organization_id=default_org.id,
        idempotency_key="worker-batch-1",
        topic="AI workflow systems",
        canonical_url="https://graxia-os-funnel.vercel.app/guides/ai-workflow-systems",
        claim_reviewed=True,
        utm_source="organic",
        utm_medium="content",
        utm_campaign="ai-workflow-systems",
        canary_passed=True,
    )
    db_session.add(batch)
    await db_session.commit()

    first = await process_content_batch(db_session, batch.id)
    second = await process_content_batch(db_session, batch.id)

    item_count = await db_session.scalar(
        select(func.count()).select_from(ContentBatchItem).where(ContentBatchItem.batch_id == batch.id)
    )
    article_count = await db_session.scalar(select(func.count()).select_from(ContentArticle))
    assert first.batch_id == second.batch_id == str(batch.id)
    assert item_count == 9
    assert article_count == 9


def test_claim_utm_and_canonical_gates_fail_closed():
    from app.services.content_batch_service import evaluate_publish_gates

    result = evaluate_publish_gates(
        claim_reviewed=False,
        canonical_url="http://untrusted.example/guide",
        utm_source="",
        utm_medium="content",
        utm_campaign="",
    )

    assert result.allowed is False
    assert {"claim_review_required", "utm_invalid", "canonical_invalid"} <= set(result.codes)


@pytest.mark.asyncio
async def test_expired_approval_and_missing_provider_consent_block_live(db_session, default_org):
    from app.services.content_batch_service import evaluate_live_publish

    approval = ApprovalRequest(
        organization_id=default_org.id,
        title="Organic content batch",
        action_type="organic_content_batch",
        status="approved",
        policy_class="content_publish",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    db_session.add(approval)
    await db_session.commit()

    expired = await evaluate_live_publish(
        db_session,
        organization_id=default_org.id,
        approval_id=approval.id,
        claim_reviewed=True,
        canonical_url="https://graxia-os-funnel.vercel.app/guides/ai-workflow-systems",
        utm_source="organic",
        utm_medium="content",
        utm_campaign="ai-workflow-systems",
        provider_consent=False,
        provider_credentials_available=True,
        canary_passed=True,
    )

    assert expired.allowed is False
    assert "approval_expired" in expired.codes
    assert "provider_consent_required" in expired.codes


@pytest.mark.asyncio
async def test_default_worker_uses_dry_run_fallback_without_provider(db_session, default_org):
    from app.services.content_batch_service import process_content_batch

    batch = ContentBatch(
        organization_id=default_org.id,
        idempotency_key="fallback-batch-1",
        topic="AI workflow systems",
        canonical_url="https://graxia-os-funnel.vercel.app/guides/ai-workflow-systems",
        claim_reviewed=True,
        utm_source="organic",
        utm_medium="content",
        utm_campaign="ai-workflow-systems",
        canary_passed=True,
        live=True,
        dry_run=False,
    )
    db_session.add(batch)
    await db_session.commit()

    result = await process_content_batch(db_session, batch.id)
    await db_session.refresh(batch)

    assert result.mode == "blocked"
    assert batch.status == "blocked"
    assert batch.fallback_used is True
    assert all(item.status == "blocked" for item in batch.items)


@pytest.mark.asyncio
async def test_public_content_resolver_only_returns_published_articles(
    db_session, public_async_client
):
    db_session.add_all([
        ContentArticle(
            site="site_a",
            slug="published-growth-guide",
            title="Growth guide",
            language="en",
            content_type="article",
            body="Published body",
            status="published",
            published_at=datetime.now(UTC),
        ),
        ContentArticle(
            site="site_a",
            slug="draft-growth-guide",
            title="Draft guide",
            language="en",
            content_type="article",
            body="Draft body",
            status="draft",
        ),
    ])
    await db_session.commit()

    published = await public_async_client.get(
        "/api/v1/public/content/articles/published-growth-guide"
    )
    draft = await public_async_client.get(
        "/api/v1/public/content/articles/draft-growth-guide"
    )

    assert published.status_code == 200
    assert published.json()["body"] == "Published body"
    assert draft.status_code == 404
