"""
Send Pending Emails Task
Runs every 5 minutes to dispatch queued emails
"""
from datetime import datetime
import structlog

from celery import Task

from ...db import get_db_session
from ...core.db_ops import acquire_automation_lock
from ...services.email_service import EmailService

logger = structlog.get_logger()


async def _send_pending_emails_impl(resend_client):
    """
    Send pending emails implementation.

    Tasks:
    1. Query EmailOutbox WHERE status='pending' AND approved
    2. For each email: call Resend API
    3. On success: update status='sent', set sent_at
    4. On failure: increment retry_count, set last_error
    5. Update linked DeliveryEvent accordingly
    """
    async with get_db_session() as db:
        async with acquire_automation_lock(db, "send_pending_emails", ttl_seconds=240) as acquired:
            if not acquired:
                logger.debug("send_pending_emails: lock not acquired, skipping")
                return {
                    "status": "skipped",
                    "reason": "lock_held_by_another_worker",
                }

            try:
                metrics = {
                    "emails_processed": 0,
                    "emails_sent": 0,
                    "emails_failed": 0,
                }

                # Get pending emails
                logger.info("send_pending_emails: fetching pending emails")
                pending_emails = await EmailService.get_pending_emails(db, limit=50)
                metrics["emails_processed"] = len(pending_emails)

                if not pending_emails:
                    logger.debug("send_pending_emails: no pending emails")
                    return {
                        "status": "completed",
                        "metrics": metrics,
                    }

                # Send each email
                for email in pending_emails:
                    try:
                        success = await EmailService.send_email(
                            db, email.id, resend_client
                        )
                        if success:
                            metrics["emails_sent"] += 1
                        else:
                            metrics["emails_failed"] += 1
                    except Exception as e:
                        logger.error(
                            "send_pending_emails: email send error",
                            email_id=str(email.id),
                            error=str(e),
                        )
                        metrics["emails_failed"] += 1

                logger.info(
                    "send_pending_emails: completed",
                    **metrics,
                )

                return {
                    "status": "completed",
                    "metrics": metrics,
                    "completed_at": datetime.utcnow().isoformat(),
                }

            except Exception as e:
                logger.error(
                    "send_pending_emails: failed",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                raise


def send_pending_emails(self: Task, resend_client=None):
    """
    Celery task wrapper for sending pending emails.

    Args:
        resend_client: Resend API client (injected, optional)
    """
    import asyncio
    from ...core.resend_client import create_resend_client

    # Create Resend client if not provided
    if not resend_client:
        try:
            resend_client = create_resend_client()
            logger.info("send_pending_emails: created resend client from environment")
        except Exception as e:
            logger.error("send_pending_emails: failed to create resend client", error=str(e))
            return {"status": "skipped", "reason": "no_resend_client"}

    return asyncio.run(_send_pending_emails_impl(resend_client))
