"""
Review collection service — manages customer reviews.
Supports automatic collection after purchase, moderation, and aggregation.
"""
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select, and_, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.funnel import ProductReview, FunnelOrder, DigitalProduct
from app.models.contact import Contact
from app.schemas.funnel import ReviewCreate, ReviewUpdate

logger = logging.getLogger(__name__)


class ReviewService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── CRUD ────────────────────────────────────────────────────────────

    async def create_review(
        self, organization_id: UUID, payload: ReviewCreate
    ) -> ProductReview:
        review = ProductReview(
            organization_id=organization_id,
            product_id=payload.product_id,
            order_id=payload.order_id,
            contact_id=payload.contact_id,
            customer_name=payload.customer_name,
            customer_email=payload.customer_email,
            rating=payload.rating,
            title=payload.title,
            body=payload.body,
            status="published",
            is_verified_purchase=bool(payload.order_id),
        )
        self.db.add(review)
        await self.db.commit()
        await self.db.refresh(review)
        return review

    async def get_review(
        self, organization_id: UUID, review_id: UUID
    ) -> Optional[ProductReview]:
        stmt = select(ProductReview).where(
            and_(
                ProductReview.id == review_id,
                ProductReview.organization_id == organization_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_reviews(
        self,
        organization_id: UUID,
        product_id: Optional[UUID] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ProductReview]:
        filters = [ProductReview.organization_id == organization_id]
        if product_id:
            filters.append(ProductReview.product_id == product_id)
        if status:
            filters.append(ProductReview.status == status)

        stmt = (
            select(ProductReview)
            .where(and_(*filters))
            .order_by(ProductReview.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_review(
        self, organization_id: UUID, review_id: UUID, payload: ReviewUpdate
    ) -> Optional[ProductReview]:
        review = await self.get_review(organization_id, review_id)
        if not review:
            return None
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(review, field, value)
        await self.db.commit()
        await self.db.refresh(review)
        return review

    async def delete_review(
        self, organization_id: UUID, review_id: UUID
    ) -> bool:
        review = await self.get_review(organization_id, review_id)
        if not review:
            return False
        await self.db.delete(review)
        await self.db.commit()
        return True

    # ── Aggregation ─────────────────────────────────────────────────────

    async def get_product_review_stats(
        self, organization_id: UUID, product_id: UUID
    ) -> dict:
        """Get review statistics for a product."""
        stmt = select(
            func.count(ProductReview.id).label("total_reviews"),
            func.coalesce(func.avg(ProductReview.rating), 0).label("avg_rating"),
            func.count(ProductReview.id).filter(ProductReview.rating == 5).label("five_star"),
            func.count(ProductReview.id).filter(ProductReview.rating == 4).label("four_star"),
            func.count(ProductReview.id).filter(ProductReview.rating == 3).label("three_star"),
            func.count(ProductReview.id).filter(ProductReview.rating == 2).label("two_star"),
            func.count(ProductReview.id).filter(ProductReview.rating == 1).label("one_star"),
        ).where(
            and_(
                ProductReview.organization_id == organization_id,
                ProductReview.product_id == product_id,
                ProductReview.status == "published",
            )
        )
        result = await self.db.execute(stmt)
        row = result.first()

        return {
            "total_reviews": row.total_reviews if row else 0,
            "average_rating": round(float(row.avg_rating), 2) if row else 0,
            "rating_distribution": {
                "5": row.five_star if row else 0,
                "4": row.four_star if row else 0,
                "3": row.three_star if row else 0,
                "2": row.two_star if row else 0,
                "1": row.one_star if row else 0,
            },
        }

    async def get_recent_reviews(
        self, organization_id: UUID, limit: int = 10
    ) -> list[dict]:
        """Get recent published reviews for social proof."""
        stmt = (
            select(ProductReview)
            .where(
                and_(
                    ProductReview.organization_id == organization_id,
                    ProductReview.status == "published",
                )
            )
            .order_by(ProductReview.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        reviews = result.scalars().all()

        return [
            {
                "id": str(r.id),
                "product_id": str(r.product_id),
                "customer_name": r.customer_name,
                "rating": r.rating,
                "title": r.title,
                "body": r.body,
                "is_verified": r.is_verified_purchase,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reviews
        ]

    # ── Auto-Review Triggers ────────────────────────────────────────────

    async def can_leave_review(
        self, organization_id: UUID, customer_email: str, product_id: UUID
    ) -> bool:
        """Check if a customer can leave a review (has purchased and hasn't reviewed yet)."""
        # Check for existing purchase
        stmt = select(FunnelOrder).where(
            and_(
                FunnelOrder.organization_id == organization_id,
                FunnelOrder.customer_email == str(customer_email),
                FunnelOrder.status == "paid",
            )
        )
        result = await self.db.execute(stmt)
        order = result.scalar_one_or_none()
        if not order:
            return False

        # Check for existing review
        stmt = select(ProductReview).where(
            and_(
                ProductReview.organization_id == organization_id,
                ProductReview.customer_email == str(customer_email),
                ProductReview.product_id == product_id,
            )
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()
        return existing is None
