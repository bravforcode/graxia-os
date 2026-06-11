"""Celery tasks for funnel automation — abandoned cart, review requests, cross-sell, win-back."""
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from celery import shared_task

logger = logging.getLogger("graxia.tasks.funnel_automation")


@shared_task(
    name="tasks.funnel_automation.check_and_send_abandoned_cart",
    queue="background",
    bind=True,
    max_retries=1,
)
def check_and_send_abandoned_cart(self, organization_id: str, checkout_session_id: str):
    """Check if a checkout session is still pending after 1hr — if so, send abandoned cart email."""
    import asyncio
    from app.database import AsyncSessionLocal
    from app.services.automation_email_service import AutomationEmailService

    async def _run():
        async with AsyncSessionLocal() as db:
            svc = AutomationEmailService(db)
            await svc.trigger_abandoned_cart(
                organization_id=UUID(organization_id),
                checkout_session_id=UUID(checkout_session_id),
            )
            await db.commit()

    try:
        asyncio.run(_run())
        logger.info(f"[TASK] Abandoned cart check done for session {checkout_session_id}")
    except Exception as exc:
        logger.error(f"[TASK] Abandoned cart check failed for session {checkout_session_id}: {exc}")
        raise self.retry(exc=exc, countdown=1800)


@shared_task(
    name="tasks.funnel_automation.send_review_request",
    queue="background",
    bind=True,
    max_retries=2,
)
def send_review_request(self, organization_id: str, order_id: str):
    """Send review request email (scheduled 3 days after purchase)."""
    import asyncio
    from app.database import AsyncSessionLocal
    from app.services.automation_email_service import AutomationEmailService

    async def _run():
        async with AsyncSessionLocal() as db:
            svc = AutomationEmailService(db)
            await svc.trigger_review_request(
                organization_id=UUID(organization_id),
                order_id=UUID(order_id),
            )
            await db.commit()

    try:
        asyncio.run(_run())
        logger.info(f"[TASK] Review request sent for order {order_id}")
    except Exception as exc:
        logger.error(f"[TASK] Review request failed for order {order_id}: {exc}")
        raise self.retry(exc=exc, countdown=3600)


@shared_task(
    name="tasks.funnel_automation.send_cross_sell",
    queue="background",
    bind=True,
    max_retries=2,
)
def send_cross_sell(self, organization_id: str, order_id: str):
    """Send cross-sell email (scheduled 7 days after purchase)."""
    import asyncio
    from app.database import AsyncSessionLocal
    from app.services.automation_email_service import AutomationEmailService

    async def _run():
        async with AsyncSessionLocal() as db:
            svc = AutomationEmailService(db)
            await svc.trigger_cross_sell(
                organization_id=UUID(organization_id),
                order_id=UUID(order_id),
            )
            await db.commit()

    try:
        asyncio.run(_run())
        logger.info(f"[TASK] Cross-sell email sent for order {order_id}")
    except Exception as exc:
        logger.error(f"[TASK] Cross-sell email failed for order {order_id}: {exc}")
        raise self.retry(exc=exc, countdown=3600)


@shared_task(
    name="tasks.funnel_automation.send_win_back_emails",
    queue="background",
    bind=True,
    max_retries=1,
)
def send_win_back_emails(self):
    """Daily beat: find customers who haven't purchased in 30+ days and send win-back emails."""
    import asyncio
    from app.database import AsyncSessionLocal
    from app.models.funnel import FunnelOrder
    from app.services.automation_email_service import AutomationEmailService
    from sqlalchemy import select, func

    async def _run():
        async with AsyncSessionLocal() as db:
            from app.models.funnel import ConversionEvent

            cutoff = datetime.now(UTC) - timedelta(days=30)
            recently_contacted = datetime.now(UTC) - timedelta(days=7)

            # Find customers whose last purchase was >30 days ago
            # Subquery: max paid_at and org per customer_email
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
                .subquery()
            )

            result = await db.execute(select(subq.c.customer_email, subq.c.organization_id, subq.c.last_paid_at))
            inactive_customers = result.all()

            if not inactive_customers:
                logger.info("[TASK] No inactive customers found for win-back")
                return

            # Filter out customers who received a win-back email in the last 7 days
            win_back_emails = [
                row.customer_email for row in inactive_customers
            ]
            if win_back_emails:
                recent_events = await db.execute(
                    select(ConversionEvent.metadata_json).where(
                        ConversionEvent.event_type == "win_back_sent",
                        ConversionEvent.occurred_at >= recently_contacted,
                    )
                )
                already_contacted = set()
                for evt in recent_events.scalars().all():
                    if evt and "email" in evt:
                        already_contacted.add(evt["email"])
            else:
                already_contacted = set()

            svc = AutomationEmailService(db)
            sent = 0
            for row in inactive_customers:
                email = row.customer_email
                if email in already_contacted:
                    continue
                name = email.split("@")[0].capitalize()
                try:
                    await svc.trigger_win_back(
                        organization_id=row.organization_id,
                        customer_email=email,
                        customer_name=name,
                    )
                    # Log win-back event for dedup on next run
                    db.add(ConversionEvent(
                        organization_id=row.organization_id,
                        event_type="win_back_sent",
                        metadata_json={"email": email},
                    ))
                    sent += 1
                except Exception as e:
                    logger.warning(f"[TASK] Win-back failed for {email}: {e}")

            await db.commit()
            logger.info(f"[TASK] Win-back emails sent: {sent}/{len(inactive_customers)}")

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.error(f"[TASK] Win-back beat failed: {exc}")
        raise self.retry(exc=exc, countdown=3600)
