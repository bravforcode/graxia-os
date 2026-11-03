"""
Automation API — coupons, reviews, bundles, email sequences.
All endpoints are tenant-scoped via org_id.
"""
import logging
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.middleware.tenant import get_org
from app.services.coupon_service import CouponService
from app.services.review_service import ReviewService
from app.schemas.funnel import (
    CouponCreate, CouponUpdate, CouponRead, CouponValidateRequest, CouponValidateResponse,
    ReviewCreate, ReviewUpdate, ReviewRead, ReviewStats,
    BundleCreate, BundleUpdate, BundleRead,
    EmailSequenceCreate, EmailSequenceUpdate, EmailSequenceRead,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Dependency Helpers ───────────────────────────────────────────────────

async def get_coupon_service(db: AsyncSession = Depends(get_db)) -> CouponService:
    return CouponService(db)

async def get_review_service(db: AsyncSession = Depends(get_db)) -> ReviewService:
    return ReviewService(db)


# ══════════════════════════════════════════════════════════════════════════
# COUPONS
# ══════════════════════════════════════════════════════════════════════════

@router.get("/coupons", response_model=list[CouponRead])
async def list_coupons(
    org=Depends(get_org),
    svc: CouponService = Depends(get_coupon_service),
):
    return await svc.list_coupons(org.id)


@router.post("/coupons", response_model=CouponRead, status_code=201)
async def create_coupon(
    payload: CouponCreate,
    org=Depends(get_org),
    svc: CouponService = Depends(get_coupon_service),
):
    return await svc.create_coupon(org.id, payload)


@router.get("/coupons/{coupon_id}", response_model=CouponRead)
async def get_coupon(
    coupon_id: UUID,
    org=Depends(get_org),
    svc: CouponService = Depends(get_coupon_service),
):
    c = await svc.get_coupon(org.id, coupon_id)
    if not c:
        raise HTTPException(404, "Coupon not found")
    return c


@router.patch("/coupons/{coupon_id}", response_model=CouponRead)
async def update_coupon(
    coupon_id: UUID,
    payload: CouponUpdate,
    org=Depends(get_org),
    svc: CouponService = Depends(get_coupon_service),
):
    c = await svc.update_coupon(org.id, coupon_id, payload)
    if not c:
        raise HTTPException(404, "Coupon not found")
    return c


@router.delete("/coupons/{coupon_id}", status_code=204)
async def delete_coupon(
    coupon_id: UUID,
    org=Depends(get_org),
    svc: CouponService = Depends(get_coupon_service),
):
    ok = await svc.delete_coupon(org.id, coupon_id)
    if not ok:
        raise HTTPException(404, "Coupon not found")


# ── Public coupon validation ──────────────────────────────────────────

@router.post("/coupons/validate", response_model=CouponValidateResponse)
async def validate_coupon(
    payload: CouponValidateRequest,
    org=Depends(get_org),
    svc: CouponService = Depends(get_coupon_service),
):
    is_valid, message, coupon = await svc.validate_coupon(
        org.id, payload.code, payload.order_amount, payload.product_id
    )
    if not is_valid or not coupon:
        return CouponValidateResponse(is_valid=False, message=message)

    discount = svc.calculate_discount(coupon, payload.order_amount)
    final = max(payload.order_amount - discount, 0)
    return CouponValidateResponse(
        is_valid=True,
        message="Coupon applied",
        discount_amount=discount,
        final_amount=final,
    )


# ══════════════════════════════════════════════════════════════════════════
# REVIEWS
# ══════════════════════════════════════════════════════════════════════════

@router.get("/reviews", response_model=list[ReviewRead])
async def list_reviews(
    product_id: Optional[UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, le=100),
    offset: int = 0,
    org=Depends(get_org),
    svc: ReviewService = Depends(get_review_service),
):
    return await svc.list_reviews(org.id, product_id, status_filter, limit, offset)


@router.post("/reviews", response_model=ReviewRead, status_code=201)
async def create_review(
    payload: ReviewCreate,
    org=Depends(get_org),
    svc: ReviewService = Depends(get_review_service),
):
    return await svc.create_review(org.id, payload)


@router.get("/reviews/{review_id}", response_model=ReviewRead)
async def get_review(
    review_id: UUID,
    org=Depends(get_org),
    svc: ReviewService = Depends(get_review_service),
):
    r = await svc.get_review(org.id, review_id)
    if not r:
        raise HTTPException(404, "Review not found")
    return r


@router.patch("/reviews/{review_id}", response_model=ReviewRead)
async def update_review(
    review_id: UUID,
    payload: ReviewUpdate,
    org=Depends(get_org),
    svc: ReviewService = Depends(get_review_service),
):
    r = await svc.update_review(org.id, review_id, payload)
    if not r:
        raise HTTPException(404, "Review not found")
    return r


@router.delete("/reviews/{review_id}", status_code=204)
async def delete_review(
    review_id: UUID,
    org=Depends(get_org),
    svc: ReviewService = Depends(get_review_service),
):
    ok = await svc.delete_review(org.id, review_id)
    if not ok:
        raise HTTPException(404, "Review not found")


@router.get("/reviews/stats/{product_id}", response_model=ReviewStats)
async def get_review_stats(
    product_id: UUID,
    org=Depends(get_org),
    svc: ReviewService = Depends(get_review_service),
):
    return await svc.get_product_review_stats(org.id, product_id)


@router.get("/reviews/recent")
async def get_recent_reviews(
    limit: int = Query(10, le=50),
    org=Depends(get_org),
    svc: ReviewService = Depends(get_review_service),
):
    return await svc.get_recent_reviews(org.id, limit)


# ══════════════════════════════════════════════════════════════════════════
# BUNDLES (in-memory, JSON-backed via model)
# ══════════════════════════════════════════════════════════════════════════

from app.models.funnel import BundleDeal, DigitalProduct
from sqlalchemy import select, and_

@router.get("/bundles", response_model=list[BundleRead])
async def list_bundles(
    org=Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(BundleDeal)
        .where(and_(BundleDeal.organization_id == org.id, BundleDeal.status == "active"))
        .order_by(BundleDeal.sales_count.desc())
    )
    result = await db.execute(stmt)
    bundles = result.scalars().all()
    return bundles


@router.post("/bundles", response_model=BundleRead, status_code=201)
async def create_bundle(
    payload: BundleCreate,
    org=Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    bundle = BundleDeal(
        organization_id=org.id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        discount_type=payload.discount_type,
        discount_value=payload.discount_value,
        product_ids=[str(pid) for pid in (payload.product_ids or [])],
        cover_image_url=payload.cover_image_url,
        badge=payload.badge,
        status="active",
        sales_count=0,
    )
    db.add(bundle)
    await db.commit()
    await db.refresh(bundle)
    return bundle


@router.get("/bundles/{bundle_id}", response_model=BundleRead)
async def get_bundle(
    bundle_id: UUID,
    org=Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(BundleDeal).where(
        and_(BundleDeal.id == bundle_id, BundleDeal.organization_id == org.id)
    )
    result = await db.execute(stmt)
    bundle = result.scalar_one_or_none()
    if not bundle:
        raise HTTPException(404, "Bundle not found")
    return bundle


@router.patch("/bundles/{bundle_id}", response_model=BundleRead)
async def update_bundle(
    bundle_id: UUID,
    payload: BundleUpdate,
    org=Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(BundleDeal).where(
        and_(BundleDeal.id == bundle_id, BundleDeal.organization_id == org.id)
    )
    result = await db.execute(stmt)
    bundle = result.scalar_one_or_none()
    if not bundle:
        raise HTTPException(404, "Bundle not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "product_ids" and value is not None:
            value = [str(pid) for pid in value]
        setattr(bundle, field, value)
    await db.commit()
    await db.refresh(bundle)
    return bundle


@router.delete("/bundles/{bundle_id}", status_code=204)
async def delete_bundle(
    bundle_id: UUID,
    org=Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(BundleDeal).where(
        and_(BundleDeal.id == bundle_id, BundleDeal.organization_id == org.id)
    )
    result = await db.execute(stmt)
    bundle = result.scalar_one_or_none()
    if not bundle:
        raise HTTPException(404, "Bundle not found")
    await db.delete(bundle)
    await db.commit()


# ── Public bundle endpoint ─────────────────────────────────────────────

@router.get("/public/bundles", response_model=list[BundleRead])
async def get_public_bundles(
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint — returns active bundles for the storefront."""
    # For now, return bundles for the default org (single-tenant mode)
    from app.models.organization import Organization
    org_stmt = select(Organization).limit(1)
    org_result = await db.execute(org_stmt)
    org = org_result.scalar_one_or_none()
    if not org:
        return []

    stmt = (
        select(BundleDeal)
        .where(and_(BundleDeal.organization_id == org.id, BundleDeal.status == "active"))
        .order_by(BundleDeal.sales_count.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ══════════════════════════════════════════════════════════════════════════
# EMAIL SEQUENCES
# ══════════════════════════════════════════════════════════════════════════

from app.models.funnel import EmailSequence

@router.get("/email-sequences", response_model=list[EmailSequenceRead])
async def list_email_sequences(
    org=Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(EmailSequence)
        .where(EmailSequence.organization_id == org.id)
        .order_by(EmailSequence.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/email-sequences", response_model=EmailSequenceRead, status_code=201)
async def create_email_sequence(
    payload: EmailSequenceCreate,
    org=Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    seq = EmailSequence(
        organization_id=org.id,
        name=payload.name,
        trigger_type=payload.trigger_type,
        delay_hours=payload.delay_hours,
        subject_template=payload.subject_template,
        body_template=payload.body_template,
        product_id=payload.product_id,
        status="draft",
    )
    db.add(seq)
    await db.commit()
    await db.refresh(seq)
    return seq


@router.patch("/email-sequences/{seq_id}", response_model=EmailSequenceRead)
async def update_email_sequence(
    seq_id: UUID,
    payload: EmailSequenceUpdate,
    org=Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(EmailSequence).where(
        and_(EmailSequence.id == seq_id, EmailSequence.organization_id == org.id)
    )
    result = await db.execute(stmt)
    seq = result.scalar_one_or_none()
    if not seq:
        raise HTTPException(404, "Email sequence not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(seq, field, value)
    await db.commit()
    await db.refresh(seq)
    return seq


@router.delete("/email-sequences/{seq_id}", status_code=204)
async def delete_email_sequence(
    seq_id: UUID,
    org=Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(EmailSequence).where(
        and_(EmailSequence.id == seq_id, EmailSequence.organization_id == org.id)
    )
    result = await db.execute(stmt)
    seq = result.scalar_one_or_none()
    if not seq:
        raise HTTPException(404, "Email sequence not found")
    await db.delete(seq)
    await db.commit()
