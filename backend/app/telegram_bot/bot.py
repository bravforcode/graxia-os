"""
Telegram Bot Implementation

Provides command handlers, approval flow, and notifications.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.approval_request import ApprovalRequest
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Global application instance
_app: Optional[Application] = None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    welcome_message = """
🤖 Welcome to Personal OS Assistant!

I'm your AI-powered personal assistant. I can help you with:

📋 Commands:
/status - System status and today's summary
/jobs - Top job opportunities
/contacts - Top contacts to reach out
/tasks - Your pending tasks
/costs - API cost breakdown
/briefing - Generate daily briefing
/help - Show this help message

I'll send you notifications for:
- High-scoring job opportunities
- Urgent emails
- Task reminders
- Budget alerts

Let's get started! 🚀
"""
    await update.message.reply_text(welcome_message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = """
📚 Available Commands:

/status - System status
  Shows: jobs, contacts, tasks, emails count

/jobs - Top job opportunities
  Shows: Top 5 high-scoring jobs

/contacts - Top contacts
  Shows: Top 5 valuable contacts

/tasks - Pending tasks
  Shows: Overdue and urgent tasks

/costs - Cost breakdown
  Shows: Today and month costs

/briefing - Daily briefing
  Generates: Comprehensive daily summary

/help - This help message

💡 Tips:
- I send notifications automatically
- High priority items bypass rate limits
- You can approve/reject actions via inline buttons
"""
    await update.message.reply_text(help_text)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command."""
    try:
        from app.agents.personal_assistant import personal_assistant_agent
        
        status = await personal_assistant_agent.get_system_status()
        
        message = f"""
📊 System Status

✅ Status: {status.get('status', 'unknown')}

📈 Current Stats:
• Jobs: {status.get('total_jobs', 0)}
• Contacts: {status.get('total_contacts', 0)}
• Pending Tasks: {status.get('pending_tasks', 0)}
• Unread Emails: {status.get('unread_emails', 0)}

🕐 Last Updated: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}
"""
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Status command failed: {e}")
        await update.message.reply_text("❌ Failed to get system status")


async def jobs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /jobs command."""
    try:
        from app.agents.job_hunter import job_hunter_agent
        
        jobs = await job_hunter_agent.get_top_jobs(limit=5, min_score=7.0)
        
        if not jobs:
            await update.message.reply_text("📭 No high-scoring jobs found")
            return
        
        message = "🎯 Top Job Opportunities:\n\n"
        for i, job in enumerate(jobs, 1):
            score = float(job.match_score) if job.match_score else 0
            message += f"{i}. {job.title}\n"
            message += f"   Company: {job.company}\n"
            message += f"   Platform: {job.source_platform}\n"
            message += f"   Score: {score:.1f}/10\n"
            if job.source_url:
                message += f"   URL: {job.source_url[:50]}...\n"
            message += "\n"
        
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Jobs command failed: {e}")
        await update.message.reply_text("❌ Failed to get jobs")


async def contacts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /contacts command."""
    try:
        from app.agents.network_builder import network_builder_agent
        
        contacts = await network_builder_agent.get_top_contacts(limit=5, min_score=7.0)
        
        if not contacts:
            await update.message.reply_text("📭 No high-value contacts found")
            return
        
        message = "👥 Top Contacts:\n\n"
        for i, contact in enumerate(contacts, 1):
            score = float(contact.value_score) if contact.value_score else 0
            message += f"{i}. {contact.name}\n"
            message += f"   Title: {contact.title or 'N/A'}\n"
            message += f"   Company: {contact.company or 'N/A'}\n"
            message += f"   Score: {score:.1f}/10\n"
            if contact.linkedin_url:
                message += f"   LinkedIn: {contact.linkedin_url[:50]}...\n"
            message += "\n"
        
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Contacts command failed: {e}")
        await update.message.reply_text("❌ Failed to get contacts")


async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /tasks command."""
    try:
        from app.models.assistant_task import AssistantTask
        from sqlalchemy import and_
        
        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
            
            # Get overdue and urgent tasks
            query = (
                select(AssistantTask)
                .where(AssistantTask.status == "pending")
                .where(
                    (AssistantTask.due_date < now) |
                    (AssistantTask.priority >= 7)
                )
                .order_by(AssistantTask.priority.desc())
                .limit(10)
            )
            result = await db.execute(query)
            tasks = list(result.scalars().all())
            
            if not tasks:
                await update.message.reply_text("✅ No urgent tasks!")
                return
            
            message = "📌 Your Tasks:\n\n"
            for i, task in enumerate(tasks, 1):
                status_emoji = "⚠️" if task.due_date and task.due_date < now else "🔥"
                due_str = task.due_date.strftime("%b %d") if task.due_date else "No date"
                
                message += f"{status_emoji} {i}. {task.title}\n"
                message += f"   Priority: {task.priority}/10\n"
                message += f"   Due: {due_str}\n"
                message += "\n"
            
            await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Tasks command failed: {e}")
        await update.message.reply_text("❌ Failed to get tasks")


async def costs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /costs command."""
    try:
        from app.models.openclaw_usage import OpenClawUsage
        from sqlalchemy import func
        
        async with AsyncSessionLocal() as db:
            today = datetime.now(timezone.utc).date()
            month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0)
            
            # Today's cost
            today_query = select(func.sum(OpenClawUsage.cost_usd)).where(
                func.date(OpenClawUsage.created_at) == today
            )
            today_result = await db.execute(today_query)
            today_cost = float(today_result.scalar() or 0)
            
            # Month's cost
            month_query = select(func.sum(OpenClawUsage.cost_usd)).where(
                OpenClawUsage.created_at >= month_start
            )
            month_result = await db.execute(month_query)
            month_cost = float(month_result.scalar() or 0)
            
            # Budget limits
            daily_limit = 1.67
            monthly_limit = 50.0
            
            daily_pct = (today_cost / daily_limit) * 100 if daily_limit > 0 else 0
            monthly_pct = (month_cost / monthly_limit) * 100 if monthly_limit > 0 else 0
            
            message = f"""
💰 Cost Breakdown

📅 Today:
• Spent: ${today_cost:.2f}
• Budget: ${daily_limit:.2f}
• Usage: {daily_pct:.0f}%

📆 This Month:
• Spent: ${month_cost:.2f}
• Budget: ${monthly_limit:.2f}
• Usage: {monthly_pct:.0f}%

{"⚠️ Budget warning!" if monthly_pct >= 80 else "✅ Within budget"}
"""
            await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Costs command failed: {e}")
        await update.message.reply_text("❌ Failed to get costs")


async def briefing_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /briefing command."""
    try:
        await update.message.reply_text("⏳ Generating daily briefing...")
        
        from app.agents.personal_assistant import personal_assistant_agent
        
        briefing = await personal_assistant_agent.generate_daily_briefing()
        
        # Split long messages
        if len(briefing) > 4000:
            parts = [briefing[i:i+4000] for i in range(0, len(briefing), 4000)]
            for part in parts:
                await update.message.reply_text(part)
        else:
            await update.message.reply_text(briefing)
    except Exception as e:
        logger.error(f"Briefing command failed: {e}")
        await update.message.reply_text("❌ Failed to generate briefing")


async def outreach_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        from app.agents.outreach_agent import outreach_agent

        result = await outreach_agent.run()
        await update.message.reply_text(str(result))
    except Exception as e:
        logger.error(f"Outreach command failed: {e}")
        await update.message.reply_text("❌ Failed to run outreach")


async def approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle approval button callbacks."""
    query = update.callback_query
    await query.answer()
    
    try:
        # Parse callback data: "approve:request_id" or "reject:request_id"
        action, request_id = query.data.split(":", 1)
        
        async with AsyncSessionLocal() as db:
            # Get approval request
            approval_query = select(ApprovalRequest).where(
                ApprovalRequest.id == request_id
            )
            result = await db.execute(approval_query)
            approval = result.scalar_one_or_none()
            
            if not approval:
                await query.edit_message_text("❌ Approval request not found")
                return
            
            if approval.status != "pending":
                await query.edit_message_text(f"ℹ️ Already {approval.status}")
                return
            
            # Update approval status
            approval.status = "approved" if action == "approve" else "rejected"
            approval.responded_at = datetime.now(timezone.utc)
            approval.response_notes = f"Via Telegram by user"
            
            await db.commit()
            
            # Execute action if approved
            if action == "approve":
                await _execute_approved_action(approval)
                await query.edit_message_text(
                    f"✅ Approved and executed!\n\n{approval.title}"
                )
            else:
                await query.edit_message_text(
                    f"❌ Rejected\n\n{approval.title}"
                )
    except Exception as e:
        logger.error(f"Approval callback failed: {e}")
        await query.edit_message_text("❌ Failed to process approval")


async def _execute_approved_action(approval: ApprovalRequest):
    """Execute approved action."""
    try:
        action_type = approval.action_type
        action_data = approval.details or {}
        
        if action_type == "send_email":
            from app.core.google_workspace import google_workspace
            await google_workspace.send_message(
                to=str(action_data.get("to") or ""),
                subject=str(action_data.get("subject") or ""),
                body=str(action_data.get("body_html") or action_data.get("body") or ""),
                is_html=bool(action_data.get("is_html") or action_data.get("body_html")),
                extra_headers=action_data.get("headers") if isinstance(action_data.get("headers"), dict) else None,
            )
        elif action_type == "linkedin_outreach":
            # Log outreach (actual sending would be manual)
            logger.info(f"LinkedIn outreach approved: {action_data}")
        elif action_type == "job_application":
            # Log application (actual submission would be manual)
            logger.info(f"Job application approved: {action_data}")
        else:
            logger.warning(f"Unknown action type: {action_type}")
    except Exception as e:
        logger.error(f"Action execution failed: {e}")


async def send_message(
    text: str,
    parse_mode: str = "Markdown",
    reply_markup: Any | None = None,
) -> bool:
    """
    Send message to user via Telegram.
    
    Args:
        text: Message text
        parse_mode: Parse mode (Markdown or HTML)
    
    Returns:
        True if sent successfully
    """
    global _app
    
    if not settings.HAS_REAL_TELEGRAM_TOKEN or not settings.HAS_REAL_TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not configured; message not sent")
        return False

    if not _app:
        _app = setup_bot()

    if not _app or not settings.TELEGRAM_CHAT_ID:
        logger.warning("Telegram bot not initialized or chat ID not set")
        return False
    
    try:
        await _app.bot.send_message(
            chat_id=settings.TELEGRAM_CHAT_ID,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


async def send_approval_request(
    request_id: str,
    description: str,
    action_type: str
) -> bool:
    """
    Send approval request with inline buttons.
    
    Args:
        request_id: Approval request ID
        description: Action description
        action_type: Type of action
    
    Returns:
        True if sent successfully
    """
    global _app
    
    if not _app or not settings.TELEGRAM_CHAT_ID:
        return False
    
    try:
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve:{request_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject:{request_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = f"""
🔔 Approval Required

Type: {action_type}

{description}

Please approve or reject this action.
"""
        
        await _app.bot.send_message(
            chat_id=settings.TELEGRAM_CHAT_ID,
            text=message,
            reply_markup=reply_markup
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send approval request: {e}")
        return False


def setup_bot() -> Application:
    """Setup Telegram bot with handlers."""
    global _app
    
    if not settings.HAS_REAL_TELEGRAM_TOKEN:
        logger.warning("Telegram bot token not configured")
        return None
    
    # Create application
    _app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    
    # Add command handlers
    _app.add_handler(CommandHandler("start", start_command))
    _app.add_handler(CommandHandler("help", help_command))
    _app.add_handler(CommandHandler("status", status_command))
    _app.add_handler(CommandHandler("jobs", jobs_command))
    _app.add_handler(CommandHandler("contacts", contacts_command))
    _app.add_handler(CommandHandler("tasks", tasks_command))
    _app.add_handler(CommandHandler("costs", costs_command))
    _app.add_handler(CommandHandler("briefing", briefing_command))
    _app.add_handler(CommandHandler("outreach", outreach_command))
    
    # Add callback handler for approvals
    _app.add_handler(CallbackQueryHandler(approval_callback))
    
    logger.info("Telegram bot setup complete")
    return _app


def get_application() -> Optional[Application]:
    """Get the global application instance."""
    return _app


async def start_polling():
    """Start bot polling (for standalone mode)."""
    global _app
    
    if not _app:
        _app = setup_bot()
    
    if _app:
        logger.info("Starting Telegram bot polling...")
        await _app.initialize()
        await _app.start()
        await _app.updater.start_polling()


async def run_polling_forever():
    """Run Telegram polling until the process receives cancellation."""
    while True:
        try:
            await start_polling()
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            msg = str(exc)
            if "Conflict" in msg or "409" in msg:
                logger.warning("Telegram polling conflict detected; retrying: %s", msg)
                await asyncio.sleep(60)
                continue
            logger.exception("Telegram polling crashed; restarting")
            await asyncio.sleep(10)
        finally:
            try:
                await stop_polling()
            except Exception:
                pass


async def stop_polling():
    """Stop bot polling."""
    global _app
    
    if _app:
        logger.info("Stopping Telegram bot...")
        await _app.updater.stop()
        await _app.stop()
        await _app.shutdown()


if __name__ == "__main__":
    # Run bot in standalone mode
    asyncio.run(run_polling_forever())
