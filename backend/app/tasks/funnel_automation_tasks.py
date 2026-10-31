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
    from app.tasks.async_runner import run_async
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
        run_async(_run())
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
    from app.tasks.async_runner import run_async
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
        run_async(_run())
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
    from app.tasks.async_runner import run_async
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
        run_async(_run())
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
    from app.tasks.async_runner import run_async
    from app.database import AsyncSessionLocal
    from app.services.automation_email_service import (
        AutomationEmailService,
        _normalized_email_digest,
        _win_back_event_email_digest,
        win_back_candidates_statement,
    )
    from app.services.delivery_email_attempts import DeliveryEmailAttemptStore
    from app.services.email_service import email_accepted
    from sqlalchemy import select

    async def _run():
        async with AsyncSessionLocal() as db:
            from app.models.funnel import ConversionEvent

            now = datetime.now(UTC)
            cutoff = now - timedelta(days=30)
            recently_contacted = now - timedelta(days=7)
            result = await db.execute(win_back_candidates_statement(cutoff))
            inactive_customers = result.all()

            if not inactive_customers:
                logger.info("[TASK] No inactive customers found for win-back")
                return

            # Filter out customers who received a win-back email in the last 7 days
            organization_ids = {row.organization_id for row in inactive_customers}
            recent_events = await db.execute(
                select(
                    ConversionEvent.organization_id,
                    ConversionEvent.metadata_json,
                ).where(
                    ConversionEvent.organization_id.in_(organization_ids),
                    ConversionEvent.event_type == "win_back_sent",
                    ConversionEvent.occurred_at >= recently_contacted,
                )
            )
            already_contacted = set()
            for organization_id, metadata_json in recent_events.all():
                email_digest = _win_back_event_email_digest(metadata_json)
                if email_digest:
                    already_contacted.add((organization_id, email_digest))

            svc = AutomationEmailService(db)
            attempt_store = DeliveryEmailAttemptStore()
            sent = 0
            for row in inactive_customers:
                email = row.customer_email
                if not isinstance(email, str) or not email.strip():
                    continue
                email_digest = _normalized_email_digest(email)
                if (row.organization_id, email_digest) in already_contacted:
                    continue
                claim = await attempt_store.claim_win_back(
                    row.organization_id, row.order_id, email, now=now
                )
                if not claim.acquired:
                    continue
                name = email.split("@")[0].capitalize()
                try:
                    result = await svc.trigger_win_back(
                        organization_id=row.organization_id,
                        customer_email=email,
                        customer_name=name,
                        idempotency_key=claim.key,
                    )
                except Exception as exc:
                    await attempt_store.finish_win_back(claim, "unknown")
                    logger.warning(
                        "[TASK] Win-back outcome unknown for organization %s (%s)",
                        row.organization_id,
                        type(exc).__name__,
                    )
                    continue

                if email_accepted(result):
                    await attempt_store.finish_win_back(claim, "sent", result["id"])
                    sent += 1
                elif (isinstance(result, dict) and result.get("status") == "suppressed"
                      and result.get("error") is None):
                    await attempt_store.finish_win_back(claim, "suppressed")
                else:
                    await attempt_store.finish_win_back(claim, "unknown")

            logger.info(f"[TASK] Win-back emails sent: {sent}/{len(inactive_customers)}")

    try:
        run_async(_run())
    except Exception as exc:
        logger.error(f"[TASK] Win-back beat failed: {exc}")
        raise self.retry(exc=exc, countdown=3600)
