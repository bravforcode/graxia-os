"""Customer support agent - intent classification + identity-verified, policy-checked actions.

Security model (Risk Audit #3/#4/#6/#7):
- WISMO/REFUND require a one-time 6-digit code emailed to the address on the order.
- Refunds are idempotent, per-customer capped, dual-cap policy checked, and escalate
  (IncidentEvent) instead of silently denying or auto-approving above threshold.
- Every REFUND classification logs the matched keyword (Risk Audit #6 transparency).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import (
    SUPPORT_VERIFICATION_MAX_ATTEMPTS,
    SUPPORT_VERIFICATION_TTL_MINUTES,
    SUPPORT_VERIFICATION_SALT,
)
from ..core.policy_engine import PolicyEngine
from ..enums import ActionType, IncidentSeverity, OrderStatus, RefundStatus, SupportIntent
from ..models import IncidentEvent, Order, Product, Refund, SupportVerification
from ..services.email_service import EmailService
from .chief_of_staff import escalate_issue

logger = structlog.get_logger()

REFUND_WINDOW_DAYS = 30
REFUND_PER_ORDER_24H = 1
WISMO_KEYWORDS = ["order", "สถานะ", "ส่งของ", "shipping", "where", "track", "tracking", "อยู่ไหน", "wismo"]
REFUND_KEYWORDS = ["refund", "คืนเงิน", "คืน", "money back", "refunded"]
PRODUCT_KEYWORDS = ["product", "สินค้า", "เหมาะ", "เนื้อหา", "buy", "ซื้อ", "ราคา", "price"]
COMPLAINT_KEYWORDS = ["complaint", "ร้องเรียน", "terrible", "แย่", "scam", "หลอก", "furious", "angry"]
SALES_KEYWORDS = ["recommend", "แนะนำ", "interested", "สนใจ", "sale", "โปรโมชัน"]


@dataclass
class SupportReply:
    intent: SupportIntent
    text: str
    action_taken: Optional[str] = None


def _hash_code(code: str) -> str:
    return hashlib.sha256((code + SUPPORT_VERIFICATION_SALT).encode()).hexdigest()


def _naive(dt: datetime) -> datetime:
    if dt is not None and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


class SupportAgent:
    """Handles customer chat messages. Money-moving actions are identity-verified + policy-checked."""

    @staticmethod
    def classify_intent(message: str) -> SupportIntent:
        msg = message.lower()
        if any(k in msg for k in COMPLAINT_KEYWORDS):
            return SupportIntent.COMPLAINT
        if any(k in msg for k in REFUND_KEYWORDS):
            return SupportIntent.REFUND
        if any(k in msg for k in WISMO_KEYWORDS):
            return SupportIntent.WISMO
        if any(k in msg for k in SALES_KEYWORDS):
            return SupportIntent.SALES
        if any(k in msg for k in PRODUCT_KEYWORDS):
            return SupportIntent.PRODUCT_QUESTION
        return SupportIntent.OTHER

    @staticmethod
    async def _latest_order(db: AsyncSession, customer_email: str) -> Optional[Order]:
        return await db.scalar(
            select(Order).where(Order.customer_email == customer_email)
            .order_by(Order.created_at.desc()).limit(1)
        )

    @staticmethod
    async def _issue_verification_code(db: AsyncSession, email: str) -> str:
        """Create a fresh 6-digit code, expire outstanding unused ones, email it. Returns the code."""
        await db.execute(
            SupportVerification.__table__.update()
            .where(SupportVerification.email == email, SupportVerification.used_at.is_(None))
            .values(expires_at=datetime.now(timezone.utc))  # expire outstanding codes
        )
        code = f"{secrets.randbelow(1_000_000):06d}"
        db.add(SupportVerification(
            email=email,
            code_hash=_hash_code(code),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=SUPPORT_VERIFICATION_TTL_MINUTES),
        ))
        await db.flush()
        await EmailService.queue_email(
            db,
            to_email=email,
            subject="รหัสยืนยันตัวตน (verification code)",
            body=f"รหัสยืนยันของคุณ: {code} ใช้ได้ {SUPPORT_VERIFICATION_TTL_MINUTES} นาที",
        )
        return code

    @staticmethod
    async def _verify_code(db: AsyncSession, email: str, code: Optional[str]) -> tuple[bool, Optional[str]]:
        """Return (ok, failure_action). failure_action: verification_required |
        verification_failed | verification_exhausted."""
        if not code:
            return False, "verification_required"
        ver = await db.scalar(
            select(SupportVerification)
            .where(SupportVerification.email == email, SupportVerification.used_at.is_(None))
            .order_by(SupportVerification.created_at.desc()).limit(1)
        )
        if ver is None:
            return False, "verification_required"
        if ver.expires_at < datetime.now(timezone.utc):
            return False, "verification_required"
        if hmac.compare_digest(ver.code_hash, _hash_code(code)):
            ver.used_at = datetime.now(timezone.utc)
            await db.flush()
            return True, None
        ver.attempts += 1
        if ver.attempts >= SUPPORT_VERIFICATION_MAX_ATTEMPTS:
            ver.used_at = datetime.now(timezone.utc)  # burn the code
            await db.flush()
            return False, "verification_exhausted"
        await db.flush()
        return False, "verification_failed"

    @staticmethod
    async def _handle_wismo(db: AsyncSession, customer_email: str) -> str:
        order = await SupportAgent._latest_order(db, customer_email)
        if order is None:
            return "ไม่พบออเดอร์ในระบบของเรา (no orders found for this email)"
        return f"สถานะออเดอร์ {order.id}: {order.status.value}"

    @staticmethod
    async def _handle_refund(db: AsyncSession, customer_email: str, message: str) -> tuple[str, str]:
        """Returns (reply_text, action). Actions: refund | refund_duplicate | refund_escalated | refund_denied."""
        order = await SupportAgent._latest_order(db, customer_email)
        if order is None:
            return "ไม่พบออเดอร์สำหรับอีเมลนี้ จึงไม่สามารถคืนเงินได้", "refund_denied"
        # Idempotency (Risk Audit #4): no refund already in flight for this order
        existing = await db.scalar(
            select(Refund).where(
                Refund.order_id == order.id,
                Refund.status.in_([RefundStatus.PENDING, RefundStatus.PROCESSING]),
            ).limit(1)
        )
        if existing is not None:
            return "มีการดำเนินการคืนเงินสำหรับออเดอร์นี้อยู่แล้ว", "refund_duplicate"
        # Per-customer rate cap: max REFUND_PER_ORDER_24H auto-refunds per order per 24h
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent = await db.scalar(
            select(Refund.id).where(Refund.order_id == order.id, Refund.created_at >= cutoff)
            .limit(REFUND_PER_ORDER_24H)
        )
        if recent is not None:
            return "มีการคืนเงินสำหรับออเดอร์นี้ภายใน 24 ชั่วโมงที่ผ่านมา", "refund_duplicate"
        # Dual-cap policy check (percent + absolute cents)
        age_days = (datetime.utcnow() - _naive(order.purchased_at)).days
        if age_days > REFUND_WINDOW_DAYS:
            return (
                "ขออภัย ไม่สามารถคืนเงินได้ เกินระยะเวลา 30 วันตามนโยบาย "
                "(refund window is 30 days)",
                "refund_denied",
            )
        decision = await PolicyEngine.check(
            db, ActionType.REFUND,
            {
                "value": 100.0,
                "value_cents": order.amount_cents,
                "order_id": str(order.id),
                "order_age_days": age_days,
            },
        )
        if not decision.allow:
            # Above threshold → escalate instead of silently denying (Risk Audit #3/#9)
            db.add(IncidentEvent(
                title=f"Refund request needs human review: {order.id}",
                description=f"{decision.reason} | message: {message[:300]}",
                severity=IncidentSeverity.MEDIUM,
                affected_order_id=order.id,
            ))
            return (
                "ออเดอร์นี้เกินวงเงินที่ระบบคืนเงินอัตโนมัติได้ เราส่งเรื่องให้ทีมตรวจสอบแล้ว "
                "จะติดต่อกลับทางอีเมล",
                "refund_escalated",
            )
        db.add(Refund(
            order_id=order.id,
            amount_cents=order.amount_cents,
            currency=order.currency,
            reason=f"support agent: {message[:200]}",
            status=RefundStatus.PROCESSING,
        ))
        await db.flush()
        return "เราเริ่มดำเนินการคืนเงินให้แล้ว จะอัปเดตทางอีเมลภายใน 3-5 วันทำการ", "refund"

    @classmethod
    async def handle_message(
        cls, db: AsyncSession, message: str, customer_email: str, verification_code: Optional[str] = None
    ) -> SupportReply:
        intent = cls.classify_intent(message)
        if intent == SupportIntent.COMPLAINT:
            await escalate_issue(
                db,
                title=f"Support complaint from {customer_email}",
                description=message[:500],
                severity=IncidentSeverity.MEDIUM,
            )
            await db.commit()
            return SupportReply(
                intent=intent,
                text="รับทราบแล้ว เราส่งเรื่องนี้ให้ทีมตรวจสอบโดยด่วน ขออภัยในความไม่สะดวก",
                action_taken="escalated",
            )
        if intent in (SupportIntent.REFUND, SupportIntent.WISMO):
            ok, fail_action = await cls._verify_code(db, customer_email, verification_code)
            if not ok:
                if fail_action == "verification_required":
                    # Issue a fresh one-time code and email it to the customer
                    await cls._issue_verification_code(db, customer_email)
                elif fail_action == "verification_exhausted":
                    await escalate_issue(
                        db,
                        title=f"Verification abuse suspected: {customer_email}",
                        description="Too many wrong verification codes",
                        severity=IncidentSeverity.LOW,
                    )
                await db.commit()
                return SupportReply(
                    intent=intent,
                    text="เราส่งรหัสยืนยัน 6 หลักไปที่อีเมลของคุณแล้ว "
                         "(เราไม่เปิดเผยข้อมูลออเดอร์โดยไม่ยืนยันตัวตน)",
                    action_taken=fail_action,
                )
        if intent == SupportIntent.REFUND:
            matched = [k for k in REFUND_KEYWORDS if k in message.lower()]  # Risk Audit #6 transparency
            logger.info("refund_request", email=customer_email, matched_keywords=matched)
            text, action = await cls._handle_refund(db, customer_email, message)
            await db.commit()
            return SupportReply(intent=intent, text=text, action_taken=action)
        if intent == SupportIntent.WISMO:
            text = await cls._handle_wismo(db, customer_email)
            await db.commit()
            return SupportReply(intent=intent, text=text, action_taken="wismo")
        if intent in (SupportIntent.PRODUCT_QUESTION, SupportIntent.SALES):
            result = await db.execute(select(Product).limit(3))
            products = list(result.scalars().all())
            names = ", ".join(p.name for p in products) if products else "(no products yet)"
            await db.commit()
            return SupportReply(intent=intent, text=f"สินค้าของเรา: {names} — ถามเพิ่มเติมได้เลยครับ", action_taken="catalog")
        await db.commit()
        return SupportReply(intent=intent, text="ขอบคุณที่ติดต่อ เราจะตอบกลับโดยเร็วที่สุด", action_taken="none")
