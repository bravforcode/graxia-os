"""Composition, safety gates, and idempotent worker processing for content batches."""

from __future__ import annotations

import inspect
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.content_ops.contracts import PublishRequest
from app.content_ops.service import configured_runtime_policy, execute_publish
from app.models.approval_request import ApprovalRequest
from app.models.content_batch import ContentBatch, ContentBatchItem
from app.models.content_engine import ContentArticle
from app.schemas.content_batch import ContentBatchProcessOut


CANONICAL_DOMAIN = os.getenv(
    "PUBLIC_SITE_URL",
    "https://bravforcode.github.io/graxia",
).rstrip("/")
ITEM_COUNT = 9
_SAFE_UTM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_SLUG_PART = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class BatchItemPlan:
    item_key: str
    position: int
    role: str
    channel: str
    title: str
    slug: str
    body: str
    canonical_url: str
    utm_params: dict[str, str]


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class BatchProcessResult:
    batch_id: str
    status: str
    mode: str
    item_count: int
    fallback_used: bool
    block_codes: tuple[str, ...] = ()

    def to_schema(self) -> ContentBatchProcessOut:
        return ContentBatchProcessOut(
            batch_id=self.batch_id,
            status=self.status,
            mode=self.mode,
            item_count=self.item_count,
            fallback_used=self.fallback_used,
            block_codes=list(self.block_codes),
        )


ContentGenerator = Callable[[BatchItemPlan], str | dict[str, str] | Awaitable[str | dict[str, str]]]


def _slugify(value: str) -> str:
    slug = _SLUG_PART.sub("-", value.lower()).strip("-")
    if slug:
        return slug[:180]
    return f"topic-{sha256(value.encode()).hexdigest()[:12]}"


def _fallback_body(topic: str, role: str, channel: str) -> str:
    return (
        f"# {topic}\n\n"
        f"Draft fallback for the {role} {channel} format. "
        "Claims require evidence review before publication."
    )


def compose_batch_items(
    *,
    topic: str,
    canonical_url: str,
    utm_source: str,
    utm_medium: str,
    utm_campaign: str,
) -> list[BatchItemPlan]:
    """Create the fixed 1 + 3 + 5 organic content composition."""

    base_slug = _slugify(topic)
    shared_utm = {
        "utm_source": utm_source,
        "utm_medium": utm_medium,
        "utm_campaign": utm_campaign,
    }
    plans: list[BatchItemPlan] = [
        BatchItemPlan(
            item_key="pillar-1",
            position=1,
            role="pillar",
            channel="seo",
            title=topic,
            slug=base_slug,
            body=_fallback_body(topic, "pillar", "seo"),
            canonical_url=canonical_url,
            utm_params={**shared_utm, "utm_content": "pillar-1"},
        )
    ]
    for position in range(2, 5):
        item_key = f"supporting-{position - 1}"
        plans.append(
            BatchItemPlan(
                item_key=item_key,
                position=position,
                role="supporting",
                channel="seo",
                title=f"{topic}: supporting guide {position - 1}",
                slug=f"{base_slug}-{item_key}",
                body=_fallback_body(topic, "supporting", "seo"),
                canonical_url=canonical_url,
                utm_params={**shared_utm, "utm_content": item_key},
            )
        )
    channels = ("tiktok", "instagram", "youtube_shorts", "facebook", "x")
    for position, channel in enumerate(channels, start=5):
        item_key = f"short-{position - 4}"
        plans.append(
            BatchItemPlan(
                item_key=item_key,
                position=position,
                role="short",
                channel=channel,
                title=f"{topic}: {channel} short",
                slug=f"{base_slug}-{item_key}",
                body=_fallback_body(topic, "short", channel),
                canonical_url=canonical_url,
                utm_params={**shared_utm, "utm_content": item_key},
            )
        )
    return plans


def _valid_utm_value(value: str | None) -> bool:
    return bool(value and _SAFE_UTM.fullmatch(value.strip()))


def _canonical_is_valid(url: str | None, *, canonical_domain: str = CANONICAL_DOMAIN) -> bool:
    if not url:
        return False
    parsed = urlsplit(url.strip())
    return bool(
        parsed.scheme == "https"
        and parsed.hostname == canonical_domain
        and parsed.path
        and not parsed.query
        and not parsed.fragment
        and not parsed.username
        and not parsed.password
    )


def evaluate_publish_gates(
    *,
    claim_reviewed: bool,
    canonical_url: str | None,
    utm_source: str | None,
    utm_medium: str | None,
    utm_campaign: str | None,
    canonical_domain: str = CANONICAL_DOMAIN,
) -> GateResult:
    """Evaluate content-only gates without contacting a provider."""

    codes: list[str] = []
    if not claim_reviewed:
        codes.append("claim_review_required")
    if not all(
        _valid_utm_value(value) for value in (utm_source, utm_medium, utm_campaign)
    ):
        codes.append("utm_invalid")
    if not _canonical_is_valid(canonical_url, canonical_domain=canonical_domain):
        codes.append("canonical_invalid")
    return GateResult(allowed=not codes, codes=tuple(codes))


async def evaluate_live_publish(
    db: AsyncSession,
    *,
    organization_id: UUID,
    approval_id: UUID | None,
    claim_reviewed: bool,
    canonical_url: str | None,
    utm_source: str | None,
    utm_medium: str | None,
    utm_campaign: str | None,
    provider: str = "organic",
    provider_consent: bool,
    provider_credentials_available: bool,
    canary_passed: bool,
    now: datetime | None = None,
) -> GateResult:
    """Evaluate every gate required before a live Content Ops request."""

    approval = await db.get(ApprovalRequest, approval_id) if approval_id else None
    approval_details = dict(approval.details or {}) if approval is not None else {}
    server_gates = approval_details.get("gates", approval_details)
    result = evaluate_publish_gates(
        claim_reviewed=server_gates.get("claim_reviewed") is True,
        canonical_url=canonical_url,
        utm_source=utm_source,
        utm_medium=utm_medium,
        utm_campaign=utm_campaign,
    )
    codes = list(result.codes)
    current_time = now or datetime.now(UTC)
    if approval is None or approval.organization_id != organization_id:
        codes.append("approval_required")
    elif approval.status != "approved":
        codes.append("approval_required")
    elif approval.expires_at is not None:
        expires_at = approval.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= current_time:
            codes.append("approval_expired")
    if not server_gates.get("provider_consent") is True:
        codes.append("provider_consent_required")
    policy = configured_runtime_policy()
    if not (
        policy.external_publish_enabled
        and provider.strip() in policy.allowed_providers
    ):
        codes.append("provider_credentials_required")
    if not server_gates.get("canary_passed") is True:
        codes.append("canary_required")
    if not provider.strip():
        codes.append("provider_invalid")
    return GateResult(allowed=not codes, codes=tuple(dict.fromkeys(codes)))


def _rendered_content(plan: BatchItemPlan, rendered: str | dict[str, str] | None) -> tuple[str, str]:
    if rendered is None:
        return plan.title, plan.body
    if isinstance(rendered, str):
        return plan.title, rendered
    return rendered.get("title", plan.title), rendered.get("body", plan.body)


async def _render(plan: BatchItemPlan, generator: ContentGenerator | None) -> tuple[str, str, bool]:
    if generator is None:
        return plan.title, plan.body, True
    rendered = generator(plan)
    if inspect.isawaitable(rendered):
        rendered = await rendered
    title, body = _rendered_content(plan, rendered)
    return title, body, False


async def _existing_items(db: AsyncSession, batch_id: UUID) -> list[ContentBatchItem]:
    result = await db.execute(
        select(ContentBatchItem)
        .where(ContentBatchItem.batch_id == batch_id)
        .order_by(ContentBatchItem.position)
    )
    return list(result.scalars().all())


def _result(
    batch: ContentBatch,
    *,
    mode: str,
    block_codes: tuple[str, ...] = (),
) -> BatchProcessResult:
    return BatchProcessResult(
        batch_id=str(batch.id),
        status=batch.status,
        mode=mode,
        item_count=batch.item_count,
        fallback_used=batch.fallback_used,
        block_codes=block_codes,
    )


async def process_content_batch(
    db: AsyncSession,
    batch_id: UUID | str,
    *,
    generator: ContentGenerator | None = None,
) -> BatchProcessResult:
    """Process one batch idempotently; default mode is local dry-run fallback."""

    batch = await db.get(ContentBatch, batch_id)
    if batch is None:
        raise ValueError(f"Content batch {batch_id} not found")

    if not settings.CONTENT_BATCH_ENABLED:
        batch.status = "blocked"
        batch.block_codes = ["content_batch_disabled"]
        await db.commit()
        return _result(batch, mode="blocked", block_codes=("content_batch_disabled",))

    existing = await _existing_items(db, batch.id)
    if batch.status in {"exported", "published"} and len(existing) == ITEM_COUNT:
        mode = "live" if batch.status == "published" else "dry_run"
        return _result(batch, mode=mode, block_codes=tuple(batch.block_codes or ()))

    batch.status = "processing"
    batch.item_count = ITEM_COUNT
    await db.flush()

    live_requested = batch.live and not batch.dry_run
    live_gates = GateResult(allowed=False, codes=())
    if live_requested:
        live_gates = await evaluate_live_publish(
            db,
            organization_id=batch.organization_id,
            approval_id=batch.approval_id,
            claim_reviewed=batch.claim_reviewed,
            canonical_url=batch.canonical_url,
            utm_source=batch.utm_source,
            utm_medium=batch.utm_medium,
            utm_campaign=batch.utm_campaign,
            provider=batch.provider,
            provider_consent=batch.provider_consent,
            provider_credentials_available=False,
            canary_passed=False,
        )

    plans = compose_batch_items(
        topic=batch.topic,
        canonical_url=batch.canonical_url,
        utm_source=batch.utm_source or "",
        utm_medium=batch.utm_medium or "",
        utm_campaign=batch.utm_campaign or "",
    )
    existing_by_key = {item.item_key: item for item in existing}
    items: list[ContentBatchItem] = []
    fallback_used = False
    for plan in plans:
        item = existing_by_key.get(plan.item_key)
        if item is not None:
            items.append(item)
            continue
        title, body, used_fallback = await _render(plan, generator)
        fallback_used = fallback_used or used_fallback
        article = ContentArticle(
            site=batch.site,
            slug=plan.slug,
            title=title,
            language=batch.language,
            content_type="article",
            meta_title=title[:120],
            meta_description=f"Draft guide about {batch.topic}"[:300],
            target_keyword=batch.topic,
            secondary_keywords=[],
            schema_type="Article",
            body=body,
            word_count=len(body.split()),
            status="draft",
            generation_model="deterministic-fallback" if used_fallback else "injected-generator",
        )
        db.add(article)
        await db.flush()
        item = ContentBatchItem(
            batch=batch,
            item_key=plan.item_key,
            idempotency_key=f"{batch.idempotency_key}:{plan.item_key}",
            position=plan.position,
            role=plan.role,
            channel=plan.channel,
            title=title,
            slug=plan.slug,
            body=body,
            canonical_url=plan.canonical_url,
            utm_params=plan.utm_params,
            claim_ids=batch.claim_ids or [],
            article_id=str(article.id),
            status="draft",
            fallback_used=used_fallback,
        )
        db.add(item)
        items.append(item)

    fallback_used = fallback_used or any(item.fallback_used for item in items)
    await db.flush()

    if live_requested and fallback_used:
        live_gates = GateResult(
            allowed=False,
            codes=tuple(dict.fromkeys((*live_gates.codes, "fallback_content_not_publishable"))),
        )

    if not live_requested:
        block_codes = ()
        for item in items:
            item.status = "dry_run"
            item.provider_status = "dry_run"
            item.block_codes = list(block_codes)
            item.processed_at = datetime.now(UTC)
        batch.status = "exported"
        batch.fallback_used = fallback_used
        batch.block_codes = list(block_codes)
        batch.export_manifest = {
            "mode": "dry_run",
            "items": [item.item_key for item in items],
        }
        batch.processed_at = datetime.now(UTC)
        await db.commit()
        return _result(batch, mode="dry_run", block_codes=block_codes)

    if not live_gates.allowed:
        block_codes = live_gates.codes
        for item in items:
            item.status = "blocked"
            item.provider_status = "blocked"
            item.block_codes = list(block_codes)
            item.processed_at = datetime.now(UTC)
        batch.status = "blocked"
        batch.fallback_used = fallback_used
        batch.block_codes = list(block_codes)
        batch.export_manifest = {
            "mode": "blocked",
            "items": [item.item_key for item in items],
        }
        batch.processed_at = datetime.now(UTC)
        await db.commit()
        return _result(batch, mode="blocked", block_codes=block_codes)

    approval_id = str(batch.approval_id)
    receipts = []
    for item in items:
        request = PublishRequest(
            tenant_id=str(batch.organization_id),
            content_id=str(item.id),
            provider=batch.provider,
            approval_id=approval_id,
            idempotency_key=item.idempotency_key,
            dry_run=False,
            live=True,
        )
        receipt = await execute_publish(
            db,
            request,
            approval_granted=True,
            consent_granted=True,
        )
        item.provider_status = receipt.provider_status
        item.publish_receipt = receipt.model_dump(mode="json")
        item.status = "published" if receipt.provider_status == "published" else "blocked"
        item.processed_at = datetime.now(UTC)
        receipts.append(receipt)

    batch.status = "published" if all(receipt.provider_status == "published" for receipt in receipts) else "blocked"
    batch.fallback_used = fallback_used
    batch.processed_at = datetime.now(UTC)
    await db.commit()
    return _result(batch, mode="live", block_codes=())


process_batch = process_content_batch
