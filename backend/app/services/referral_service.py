from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.contact import Contact
from app.models.funnel import DeliveryAccess, FunnelCheckoutSession, FunnelOrder
from app.models.referral import (
    ReferralAttribution,
    ReferralCode,
    ReferralConversion,
    ReferralPartner,
)

SOURCE_TYPES = {"captured_lead", "verified_delivery", "approved_partner"}
ALLOWED_REDIRECT_PREFIXES = (
    "/store",
    "/free/",
    "/guides/",
    "/f/",
    "/revenue-os",
)
REFERRAL_SESSION_COOKIE = "graxia_referral_session"
DEFAULT_COMMISSION_RATE = Decimal("0.20")
DEFAULT_HOLD_DAYS = 14


class ReferralError(ValueError):
    """Base class for safe referral validation failures."""


class ReferralValidationError(ReferralError):
    pass


class ReferralEligibilityError(ReferralError):
    pass


class ReferralNotFoundError(ReferralError):
    pass


@dataclass(frozen=True)
class IssuedReferral:
    code: str
    record: ReferralCode


@dataclass(frozen=True)
class ReferralResolution:
    record: ReferralCode
    redirect_path: str
    accepted: bool


def hash_referral_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def hash_identity(identity: str) -> str:
    return hashlib.sha256(identity.strip().encode("utf-8")).hexdigest()


def is_allowed_internal_path(path: str) -> bool:
    if not path or len(path) > 500 or any(ord(char) < 32 for char in path):
        return False
    if "\\" in path or path.startswith("//"):
        return False
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        return False
    return path == "/" or any(
        path.startswith(prefix)
        if prefix.endswith("/")
        else path == prefix or path.startswith(prefix + "/")
        for prefix in ALLOWED_REDIRECT_PREFIXES
    )


def _ensure_session_id(session_id: str) -> str:
    value = session_id.strip()
    if not value or len(value) > 255 or any(ord(char) < 32 for char in value):
        raise ReferralValidationError("Invalid referral session")
    return value


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class ReferralService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def issue_code(
        self,
        *,
        organization_id: UUID,
        issuer_user_id: UUID | None,
        source_type: str,
        source_id: UUID | None,
        redirect_path: str,
        owner_identity: str | None = None,
        bonus_asset_path: str | None = None,
    ) -> IssuedReferral:
        if not settings.REFERRAL_LOOP_ENABLED:
            raise ReferralError("Referral loop is disabled")
        if source_type not in SOURCE_TYPES:
            raise ReferralValidationError("Unsupported referral source")
        if not is_allowed_internal_path(redirect_path):
            raise ReferralValidationError("Referral redirect must be an allowed internal path")
        if source_id is None:
            raise ReferralValidationError("A verified referral source is required")

        audience = "regular_user"
        partner_id: UUID | None = None
        commission_rate = Decimal("0.00")

        if source_type == "captured_lead":
            lead = await self.db.scalar(
                select(Contact).where(
                    Contact.id == source_id,
                    Contact.organization_id == organization_id,
                    Contact.contact_type == "lead",
                    Contact.is_deleted.is_(False),
                    Contact.email.is_not(None),
                )
            )
            if lead is None:
                raise ReferralEligibilityError("Referral source is not a captured lead")
        elif source_type == "verified_delivery":
            delivery = await self.db.scalar(
                select(DeliveryAccess).where(
                    DeliveryAccess.id == source_id,
                    DeliveryAccess.organization_id == organization_id,
                    DeliveryAccess.status == "active",
                )
            )
            if delivery is None or (
                _as_utc(delivery.expires_at) is not None
                and _as_utc(delivery.expires_at) <= datetime.now(UTC)
            ):
                raise ReferralEligibilityError("Referral source is not a verified delivery")
        else:
            partner = await self.db.scalar(
                select(ReferralPartner).where(
                    ReferralPartner.id == source_id,
                    ReferralPartner.organization_id == organization_id,
                    ReferralPartner.status == "approved",
                )
            )
            if partner is None:
                raise ReferralEligibilityError("Referral source is not an approved partner")
            audience = "partner"
            partner_id = partner.id
            commission_rate = Decimal(str(partner.commission_rate or DEFAULT_COMMISSION_RATE))
            if bonus_asset_path is not None:
                raise ReferralValidationError("Partner referrals cannot issue a user bonus asset")

        if bonus_asset_path is not None:
            if audience != "regular_user" or not is_allowed_internal_path(bonus_asset_path):
                raise ReferralValidationError("Bonus asset must be an internal regular-user asset")
            if not bonus_asset_path.startswith("/free/"):
                raise ReferralValidationError("Bonus asset must use the /free/ path")

        raw_code = "r_" + secrets.token_urlsafe(24)
        record = ReferralCode(
            organization_id=organization_id,
            code_hash=hash_referral_code(raw_code),
            source_type=source_type,
            source_id=source_id,
            issuer_user_id=issuer_user_id,
            owner_identity_hash=hash_identity(owner_identity) if owner_identity else None,
            partner_id=partner_id,
            audience=audience,
            redirect_path=redirect_path,
            bonus_asset_path=bonus_asset_path,
            commission_rate=commission_rate,
            hold_days=DEFAULT_HOLD_DAYS,
            is_active=True,
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return IssuedReferral(code=raw_code, record=record)

    async def resolve_code(
        self,
        *,
        code: str,
        session_id: str,
        organization_id: UUID | None = None,
        identity_key: str | None = None,
    ) -> ReferralResolution:
        if not settings.REFERRAL_LOOP_ENABLED:
            raise ReferralNotFoundError("Referral loop is disabled")
        session_id = _ensure_session_id(session_id)
        code_hash = hash_referral_code(code.strip())
        filters = [ReferralCode.code_hash == code_hash, ReferralCode.is_active.is_(True)]
        if organization_id is not None:
            filters.append(ReferralCode.organization_id == organization_id)
        record = await self.db.scalar(select(ReferralCode).where(*filters))
        if record is None or (
            _as_utc(record.expires_at) is not None
            and _as_utc(record.expires_at) <= datetime.now(UTC)
        ):
            raise ReferralNotFoundError("Referral not found")
        if record.owner_identity_hash:
            # Anonymous visitors may still be referred.  When an identity is
            # available, reject only the owner; the verified-order path makes
            # the same comparison again before granting a reward.
            if identity_key and hash_identity(identity_key) == record.owner_identity_hash:
                raise ReferralEligibilityError("Self-referral is not eligible")

        existing = await self.db.scalar(
            select(ReferralAttribution).where(
                ReferralAttribution.organization_id == record.organization_id,
                ReferralAttribution.session_id == session_id,
            )
        )
        if existing is not None:
            return ReferralResolution(
                record=record,
                redirect_path=record.redirect_path,
                accepted=existing.referral_code_id == record.id,
            )

        attribution = ReferralAttribution(
            organization_id=record.organization_id,
            referral_code_id=record.id,
            session_id=session_id,
            identity_hash=hash_identity(identity_key) if identity_key else None,
        )
        self.db.add(attribution)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            existing = await self.db.scalar(
                select(ReferralAttribution).where(
                    ReferralAttribution.organization_id == record.organization_id,
                    ReferralAttribution.session_id == session_id,
                )
            )
            if existing is None:
                raise
            return ReferralResolution(
                record=record,
                redirect_path=record.redirect_path,
                accepted=existing.referral_code_id == record.id,
            )
        return ReferralResolution(record=record, redirect_path=record.redirect_path, accepted=True)

    async def record_conversion(
        self,
        *,
        organization_id: UUID,
        code_id: UUID,
        session_id: str,
        conversion_key: str,
        verified_order_id: UUID,
        verified_amount: Decimal | None = None,
    ) -> ReferralConversion:
        if not settings.REFERRAL_LOOP_ENABLED:
            raise ReferralEligibilityError("Referral loop is disabled")
        session_id = _ensure_session_id(session_id)
        if not conversion_key.strip() or len(conversion_key) > 255:
            raise ReferralValidationError("Invalid conversion key")
        record = await self.db.scalar(
            select(ReferralCode).where(
                ReferralCode.id == code_id,
                ReferralCode.organization_id == organization_id,
                ReferralCode.is_active.is_(True),
            )
        )
        if record is None:
            raise ReferralNotFoundError("Referral not found")
        attribution = await self.db.scalar(
            select(ReferralAttribution).where(
                ReferralAttribution.organization_id == organization_id,
                ReferralAttribution.referral_code_id == code_id,
                ReferralAttribution.session_id == session_id,
            )
        )
        if attribution is None:
            raise ReferralEligibilityError("Conversion requires a valid referral attribution")
        order = await self.db.scalar(
            select(FunnelOrder).where(
                FunnelOrder.id == verified_order_id,
                FunnelOrder.organization_id == organization_id,
                FunnelOrder.status == "paid",
                FunnelOrder.refunded_at.is_(None),
            )
        )
        if order is None:
            raise ReferralEligibilityError(
                "Conversion requires a paid, non-refunded order"
            )
        if record.issuer_user_id is not None and order.user_id == record.issuer_user_id:
            raise ReferralEligibilityError("Self-referral is not eligible")
        if record.source_type == "captured_lead":
            source_contact = await self.db.scalar(
                select(Contact).where(
                    Contact.id == record.source_id,
                    Contact.organization_id == organization_id,
                )
            )
            order_email = (order.customer_email or "").strip().casefold()
            source_email = (source_contact.email or "").strip().casefold() if source_contact else ""
            if source_email and order_email and source_email == order_email:
                raise ReferralEligibilityError("Self-referral is not eligible")
        server_amount = Decimal(str(order.total_amount or 0))
        checkout = None
        if order.checkout_session_id is not None:
            checkout = await self.db.scalar(
                select(FunnelCheckoutSession).where(
                    FunnelCheckoutSession.id == order.checkout_session_id,
                    FunnelCheckoutSession.organization_id == organization_id,
                )
            )
        if checkout is not None:
            checkout_metadata = checkout.metadata_json or {}
            if checkout_metadata.get("session_id") not in (None, session_id):
                raise ReferralEligibilityError("Order is not linked to referral session")
            referral_code = checkout_metadata.get("referral_code")
            if referral_code and hash_referral_code(str(referral_code)) != record.code_hash:
                raise ReferralEligibilityError("Order is not linked to referral code")
        existing = await self.db.scalar(
            select(ReferralConversion).where(ReferralConversion.referral_code_id == code_id)
        )
        if existing is not None:
            raise ReferralEligibilityError("Referral reward already recorded")

        if not settings.REFERRAL_REWARD_ENABLED:
            gross_amount = Decimal("0.00")
            commission_amount = Decimal("0.00")
            reward_type = "partner_commission" if record.audience == "partner" else "regular_bonus"
            status = "disabled"
            settlement_status = "not_applicable"
            hold_until = None
            bonus_asset_path = None
        elif record.audience == "partner":
            gross_amount = server_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            commission_amount = (gross_amount * record.commission_rate).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            reward_type = "partner_commission"
            status = "held"
            settlement_status = "manual_pending"
            hold_until = datetime.now(UTC) + timedelta(days=record.hold_days)
            bonus_asset_path = None
        else:
            gross_amount = Decimal("0.00")
            commission_amount = Decimal("0.00")
            reward_type = "regular_bonus"
            status = "eligible"
            settlement_status = "not_applicable"
            hold_until = None
            bonus_asset_path = record.bonus_asset_path

        conversion = ReferralConversion(
            organization_id=organization_id,
            referral_code_id=code_id,
            session_id=session_id,
            conversion_key=conversion_key.strip(),
            verified_order_id=verified_order_id,
            reward_type=reward_type,
            bonus_asset_path=bonus_asset_path,
            gross_amount=gross_amount,
            commission_rate=record.commission_rate,
            commission_amount=commission_amount,
            hold_until=hold_until,
            status=status,
            settlement_status=settlement_status,
            metadata_json={"source": "server_verified"},
        )
        self.db.add(conversion)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ReferralEligibilityError("Referral reward already recorded") from exc
        await self.db.refresh(conversion)
        return conversion

    async def record_conversion_for_order(
        self,
        *,
        organization_id: UUID,
        referral_code: str,
        session_id: str,
        order_id: UUID,
        conversion_key: str,
    ) -> ReferralConversion:
        record = await self.db.scalar(
            select(ReferralCode).where(
                ReferralCode.organization_id == organization_id,
                ReferralCode.code_hash == hash_referral_code(referral_code.strip()),
                ReferralCode.is_active.is_(True),
            )
        )
        if record is None:
            raise ReferralNotFoundError("Referral not found")
        return await self.record_conversion(
            organization_id=organization_id,
            code_id=record.id,
            session_id=session_id,
            conversion_key=conversion_key,
            verified_order_id=order_id,
        )

    async def analytics(self, organization_id: UUID) -> list[dict[str, object]]:
        codes = (
            await self.db.execute(
                select(ReferralCode)
                .where(ReferralCode.organization_id == organization_id)
                .order_by(ReferralCode.created_at)
            )
        ).scalars().all()
        rows: list[dict[str, object]] = []
        for code in codes:
            valid_referrals = await self.db.scalar(
                select(func.count(ReferralAttribution.id)).where(
                    ReferralAttribution.organization_id == organization_id,
                    ReferralAttribution.referral_code_id == code.id,
                )
            )
            conversions = await self.db.scalar(
                select(func.count(ReferralConversion.id)).where(
                    ReferralConversion.organization_id == organization_id,
                    ReferralConversion.referral_code_id == code.id,
                )
            )
            commission_held = await self.db.scalar(
                select(func.coalesce(func.sum(ReferralConversion.commission_amount), 0)).where(
                    ReferralConversion.organization_id == organization_id,
                    ReferralConversion.referral_code_id == code.id,
                    ReferralConversion.settlement_status == "manual_pending",
                )
            )
            rows.append(
                {
                    "code_id": code.id,
                    "source_type": code.source_type,
                    "audience": code.audience,
                    "redirect_path": code.redirect_path,
                    "is_active": code.is_active,
                    "valid_referrals": int(valid_referrals or 0),
                    "conversions": int(conversions or 0),
                    "commission_held": float(commission_held or 0),
                }
            )
        return rows
