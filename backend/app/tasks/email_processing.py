"""
Email Processing Task

Scheduled task to process unread emails.
"""
import logging

from app.agents.email_manager import email_manager_agent
from app.tasks.base import execute_managed_async_task, idempotent_task
from app.tasks.celery_app import celery_app
from app.tasks.queues import BACKGROUND_QUEUE
from app.telegram_bot.bot import send_message

logger = logging.getLogger(__name__)


async def run_email_processing():
    """
    Process unread emails from Gmail.
    
    Scheduled: Every 30 minutes (9 AM - 6 PM Bangkok time)
    """
    logger.info("Starting scheduled email processing")
    
    try:
        # Process unread emails
        result = await email_manager_agent.fetch_and_process(
            max_emails=50,
            query="is:unread"
        )
        
        processed = result.get("processed", 0)
        categorized = result.get("categorized", {})
        action_items = result.get("action_items_created", 0)
        
        # Log results
        logger.info(
            f"Email processing complete: {processed} processed, "
            f"{action_items} action items created"
        )
        
        # Send notification for urgent emails
        urgent_count = categorized.get("urgent", 0)
        if urgent_count > 0:
            message = f"""
📧 Urgent Emails Alert

🔴 {urgent_count} urgent email(s) require attention!

Check your inbox or use /status for details.
"""
            await send_message(message)
        
        return result
    except Exception as e:
        logger.error(f"Email processing task failed: {e}", exc_info=True)
        # Don't send notification for every email processing error
        # (runs frequently, would spam)
        raise


@celery_app.task(name="tasks.email_processing.run", queue=BACKGROUND_QUEUE)
@idempotent_task("{task_name}:{date}")
def email_processing_task():
    return execute_managed_async_task(
        task_name="email_processing",
        queue=BACKGROUND_QUEUE,
        coroutine_factory=run_email_processing,
    )
