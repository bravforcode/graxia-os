"""Serverless-friendly funnel automation scans (no Celery required).

Used by the Vercel store API: triggered on a schedule (cron-job.org ping →
/internal/funnel/process-due) and best-effort in-process APScheduler jobs.

The Celery tasks in funnel_automation_tasks.py remain the transport for the
Render/worker deployment; this module is the plain-async equivalent that also
implements the SCAN side (Celery scheduled per-session; here we discover due
sessions/orders directly from the database).
"""
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.funnel import FunnelCheckoutSession, FunnelOrder, ConversionEvent
from app.services.automation_email_service import AutomationEmailService

logger = logging.getLogger("graxia.tasks.funnel_runtime")

ABANDONED_CART_AFTER = timedelta(hours=1)
REVIEW_AFTER = timedelta(days=3)
CROSS_SELL_AFTER = timedelta(days=7)
WIN_BACK_AFTER = timedelta(days=30)
BATCH_LIMIT = 50


async def scan_abandoned_carts(limit: int = BATCH_LIMIT) -> int:
    """Send abandoned-cart emails for pending checkouts older than 1 hour."""
    async with AsyncSessionLocal() as db:
        cutoff = datetime.now(UTC) - ABANDONED_CART_AFTER
        rows = (
            await db.execute(
                select(FunnelCheckoutSession)
                .where(
                    FunnelCheckoutSession.status == "pending",
                    FunnelCheckoutSession.created_at < cutoff,
                    FunnelCheckoutSession.abandoned_email_sent_at.is_(None),
                )
                .limit(limit)
            )
        ).scalars().all()

        svc = AutomationEmailService(db)
        sent = 0
        for cs in rows:
            try:
                await svc.trigger_abandoned_cart(cs.organization_id, cs.id)
                cs.abandoned_email_sent_at = datetime.now(UTC)
                sent += 1
            except Exception as exc:  # noqa: BLE001 — one bad email must not kill the scan
                logger.warning(f"Abandoned cart email failed for session {cs.id}: {exc}")
        await db.commit()
        if sent:
            logger.info(f"[RUNTIME] Abandoned cart emails sent: {sent}")
        return sent


async def _scan_order_emails(
    event_type: str,
    service_trigger,
    cutoff_delta: timedelta,
    limit: int = BATCH_LIMIT,
) -> int:
    """Send review/cross-sell emails for paid orders older than cutoff, dedup via ConversionEvent."""
    async with AsyncSessionLocal() as db:
        cutoff = datetime.now(UTC) - cutoff_delta
        rows = (
            await db.execute(
                select(FunnelOrder).where(
                    FunnelOrder.status == "paid",
                    FunnelOrder.paid_at < cutoff,
                ).limit(limit)
            )
        ).scalars().all()

        existing_rows = await db.execute(
            select(ConversionEvent.metadata_json).where(
                ConversionEvent.event_type == event_type
            )
        )
        already = set()
        for evt in existing_rows.scalars().all():
            if evt and evt.get("order_id"):
                already.add(evt["order_id"])

        svc = AutomationEmailService(db)
        sent = 0
        for order in rows:
            if str(order.id) in already:
                continue
            try:
                await service_trigger(svc, order)
                db.add(ConversionEvent(
                    organization_id=order.organization_id,
                    event_type=event_type,
                    metadata_json={"order_id": str(order.id)},
                ))
                sent += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"{event_type} failed for order {order.id}: {exc}")
        await db.commit()
        if sent:
            logger.info(f"[RUNTIME] {event_type} emails sent: {sent}")
        return sent


async def scan_review_requests(limit: int = BATCH_LIMIT) -> int:
    async def _trigger(svc, order):
        await svc.trigger_review_request(
            organization_id=order.organization_id,
            order_id=order.id,
        )
    return await _scan_order_emails("review_request_sent", _trigger, REVIEW_AFTER, limit)


async def scan_cross_sells(limit: int = BATCH_LIMIT) -> int:
    async def _trigger(svc, order):
        await svc.trigger_cross_sell(
            organization_id=order.organization_id,
            order_id=order.id,
        )
    return await _scan_order_emails("cross_sell_sent", _trigger, CROSS_SELL_AFTER, limit)


async def scan_win_backs(limit: int = BATCH_LIMIT) -> int:
    """Find customers whose last purchase is older than 30 days and email them (dedup 7d)."""
    from sqlalchemy import func

    async with AsyncSessionLocal() as db:
        cutoff = datetime.now(UTC) - WIN_BACK_AFTER
        recently_contacted = datetime.now(UTC) - timedelta(days=7)

        subq = (
            select(
                FunnelOrder.customer_email,
                FunnelOrder.organization_id,
                func.max(FunnelOrder.paid_at).label("last_paid_at"),
            )
            .where(
                FunnelOrder.customer_email.isnot(None),
                FunnelOrder.status == "paid",
            )
            .group_by(FunnelOrder.customer_email, FunnelOrder.organization_id)
            .having(func.max(FunnelOrder.paid_at) < cutoff)
            .limit(limit)
            .subquery()
        )
        result = await db.execute(
            select(subq.c.customer_email, subq.c.organization_id, subq.c.last_paid_at)
        )
        inactive = result.all()
        if not inactive:
            return 0

        recent = await db.execute(
            select(ConversionEvent.metadata_json).where(
                ConversionEvent.event_type == "win_back_sent",
                ConversionEvent.occurred_at >= recently_contacted,
            )
        )
        already_contacted = set()
        for evt in recent.scalars().all():
            if evt and "email" in evt:
                already_contacted.add(evt["email"])

        svc = AutomationEmailService(db)
        sent = 0
        for row in inactive:
            email = row.customer_email
            if email in already_contacted:
                continue
            try:
                await svc.trigger_win_back(
                    organization_id=row.organization_id,
                    customer_email=email,
                    customer_name=email.split("@")[0].capitalize(),
                )
                db.add(ConversionEvent(
                    organization_id=row.organization_id,
                    event_type="win_back_sent",
                    metadata_json={"email": email},
                ))
                sent += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Win-back failed for {email}: {exc}")
        await db.commit()
        if sent:
            logger.info(f"[RUNTIME] Win-back emails sent: {sent}")
        return sent


async def process_all_due() -> dict:
    """Run every funnel automation scan. Called by cron-job.org → /internal/funnel/process-due."""
    return {
        "abandoned_carts": await scan_abandoned_carts(),
        "review_requests": await scan_review_requests(),
        "cross_sells": await scan_cross_sells(),
        "win_backs": await scan_win_backs(),
    }
