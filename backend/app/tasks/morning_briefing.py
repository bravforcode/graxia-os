"""
Morning Briefing Task

Scheduled task to send daily briefing.
"""
import logging

from app.agents.personal_assistant import personal_assistant_agent
from app.tasks.base import execute_managed_async_task, idempotent_task
from app.tasks.celery_app import celery_app
from app.tasks.queues import DEFAULT_QUEUE
from app.telegram_bot.bot import send_message

logger = logging.getLogger(__name__)


async def send_morning_briefing():
    """
    Generate and send daily briefing.
    
    Scheduled: 8:00 AM Bangkok time daily
    """
    logger.info("Starting morning briefing generation")
    
    try:
        # Generate briefing
        briefing = await personal_assistant_agent.generate_daily_briefing()
        
        # Send via Telegram
        # Split long messages if needed
        if len(briefing) > 4000:
            parts = [briefing[i:i+4000] for i in range(0, len(briefing), 4000)]
            for part in parts:
                await send_message(part)
        else:
            await send_message(briefing)
        
        logger.info("Morning briefing sent successfully")
        return {"status": "sent", "length": len(briefing)}
    except Exception as e:
        logger.error(f"Morning briefing task failed: {e}", exc_info=True)
        await send_message(f"❌ Failed to generate morning briefing: {str(e)[:100]}")
        raise


@celery_app.task(name="tasks.morning_briefing.run", queue=DEFAULT_QUEUE)
@idempotent_task("{task_name}:{date}")
def morning_briefing_task():
    return execute_managed_async_task(
        task_name="morning_briefing",
        queue=DEFAULT_QUEUE,
        coroutine_factory=send_morning_briefing,
    )
