"""
Coupon & discount service — validates, applies, and auto-generates coupons.
Supports percentage and fixed-amount discounts with usage limits and expiry.
"""
import logging
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select, and_, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.funnel import Coupon, FunnelOrder
from app.schemas.funnel import CouponCreate, CouponUpdate

logger = logging.getLogger(__name__)


class CouponService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── CRUD ────────────────────────────────────────────────────────────

    async def create_coupon(
        self, organization_id: UUID, payload: CouponCreate
    ) -> Coupon:
        coupon = Coupon(
            organization_id=organization_id,
            code=payload.code.upper(),
            coupon_type=payload.coupon_type,
            discount_value=payload.discount_value,
            currency=payload.currency or "THB",
            min_order_amount=payload.min_order_amount or Decimal("0"),
            max_uses=payload.max_uses,
            product_id=payload.product_id,
            status="active",
            expires_at=payload.expires_at,
            description=payload.description,
        )
        self.db.add(coupon)
        await self.db.commit()
        await self.db.refresh(coupon)
        return coupon

    async def get_coupon(
        self, organization_id: UUID, coupon_id: UUID
    ) -> Optional[Coupon]:
        stmt = select(Coupon).where(
            and_(Coupon.id == coupon_id, Coupon.organization_id == organization_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_coupon_by_code(
        self, organization_id: UUID, code: str
    ) -> Optional[Coupon]:
        stmt = select(Coupon).where(
            and_(
                Coupon.code == code.upper(),
                Coupon.organization_id == organization_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_coupons(self, organization_id: UUID) -> list[Coupon]:
        stmt = (
            select(Coupon)
            .where(Coupon.organization_id == organization_id)
            .order_by(Coupon.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_coupon(
        self, organization_id: UUID, coupon_id: UUID, payload: CouponUpdate
    ) -> Optional[Coupon]:
        coupon = await self.get_coupon(organization_id, coupon_id)
        if not coupon:
            return None
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(coupon, field, value)
        await self.db.commit()
        await self.db.refresh(coupon)
        return coupon

    async def delete_coupon(
        self, organization_id: UUID, coupon_id: UUID
    ) -> bool:
        coupon = await self.get_coupon(organization_id, coupon_id)
        if not coupon:
            return False
        await self.db.delete(coupon)
        await self.db.commit()
        return True

    # ── Validation & Application ────────────────────────────────────────

    async def validate_coupon(
        self,
        organization_id: UUID,
        code: str,
        order_amount: Decimal,
        product_id: Optional[UUID] = None,
    ) -> tuple[bool, str, Optional[Coupon]]:
        """
        Validate a coupon code. Returns (is_valid, message, coupon).
        """
        coupon = await self.get_coupon_by_code(organization_id, code)
        if not coupon:
            return False, "Invalid coupon code", None

        if coupon.status != "active":
            return False, "This coupon is no longer active", None

        if coupon.expires_at and coupon.expires_at < datetime.now():
            return False, "This coupon has expired", None

        if coupon.max_uses and coupon.used_count >= coupon.max_uses:
            return False, "This coupon has reached its usage limit", None

        if coupon.min_order_amount and order_amount < coupon.min_order_amount:
            return False, f"Minimum order amount is {coupon.min_order_amount} {coupon.currency}", None

        if coupon.product_id and product_id and coupon.product_id != product_id:
            return False, "This coupon is not valid for this product", None

        return True, "Valid", coupon

    def calculate_discount(
        self, coupon: Coupon, order_amount: Decimal
    ) -> Decimal:
        """Calculate the discount amount."""
        if coupon.coupon_type == "percentage":
            discount = order_amount * (coupon.discount_value / Decimal("100"))
        else:
            discount = min(coupon.discount_value, order_amount)
        return discount.quantize(Decimal("0.01"))

    async def apply_coupon(
        self, organization_id: UUID, code: str, order_amount: Decimal, product_id: Optional[UUID] = None
    ) -> tuple[bool, str, Decimal, Decimal]:
        """
        Validate and apply a coupon. Returns (success, message, discount_amount, final_amount).
        """
        is_valid, message, coupon = await self.validate_coupon(
            organization_id, code, order_amount, product_id
        )
        if not is_valid:
            return False, message, Decimal("0"), order_amount

        discount = self.calculate_discount(coupon, order_amount)
        final_amount = max(order_amount - discount, Decimal("0"))

        # Increment usage count
        coupon.used_count += 1
        await self.db.commit()

        return True, "Coupon applied", discount, final_amount

    # ── Auto-Generate Coupons ───────────────────────────────────────────

    async def auto_generate_welcome_coupon(
        self,
        organization_id: UUID,
        discount_percent: int = 10,
        valid_days: int = 7,
    ) -> Coupon:
        """Auto-generate a welcome discount coupon for new leads."""
        code = f"WELCOME{secrets.token_hex(3).upper()}"
        payload = CouponCreate(
            code=code,
            coupon_type="percentage",
            discount_value=Decimal(str(discount_percent)),
            currency="THB",
            min_order_amount=Decimal("0"),
            max_uses=1,
            expires_at=datetime.now() + timedelta(days=valid_days),
            description=f"Welcome discount — {discount_percent}% off your first purchase",
        )
        return await self.create_coupon(organization_id, payload)

    async def auto_generate_abandoned_cart_coupon(
        self,
        organization_id: UUID,
        customer_email: str,
        discount_percent: int = 15,
        valid_days: int = 3,
    ) -> Coupon:
        """Auto-generate a coupon for abandoned cart recovery."""
        code = f"COMEBACK{secrets.token_hex(3).upper()}"
        payload = CouponCreate(
            code=code,
            coupon_type="percentage",
            discount_value=Decimal(str(discount_percent)),
            currency="THB",
            min_order_amount=Decimal("0"),
            max_uses=1,
            expires_at=datetime.now() + timedelta(days=valid_days),
            description=f"Come back! {discount_percent}% off — valid for {valid_days} days",
        )
        return await self.create_coupon(organization_id, payload)
