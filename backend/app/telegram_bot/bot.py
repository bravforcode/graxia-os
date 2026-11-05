"""
Telegram Bot Implementation

Provides command handlers, approval flow, and notifications.
"""
import asyncio
import logging
from uuid import UUID

from app.auth.context import AuthContext
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.approval_request import ApprovalRequest

logger = logging.getLogger(__name__)

# Global application instance
_app: Application | None = None


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
/pair <code> - Link this private chat to your authenticated account
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
  Unavailable until usage records have organization attribution

/briefing - Daily briefing
  Unavailable until every section is organization-scoped

/pair <code> - Link this private chat to your authenticated account
  Run in a private chat using a one-time code from the web app

/help - This help message

💡 Tips:
- Data commands require a paired account in a private chat
- I send notifications automatically
- High priority items bypass rate limits
- You can approve/reject actions via inline buttons
"""
    await update.message.reply_text(help_text)


def _private_telegram_identity(update: Update) -> tuple[str, str] | None:
    chat = getattr(update, "effective_chat", None)
    user = getattr(update, "effective_user", None)
    if (
        chat is None
        or user is None
        or getattr(chat, "type", None) != "private"
        or str(chat.id) != str(user.id)
    ):
        return None
    return str(user.id), str(chat.id)


def _telegram_command_message(update: Update):
    return getattr(update, "effective_message", None) or getattr(update, "message", None)


async def _deny_telegram_read_command(update: Update) -> None:
    chat = getattr(update, "effective_chat", None)
    message = _telegram_command_message(update)
    if chat is not None and getattr(chat, "type", None) == "private" and message is not None:
        await message.reply_text(
            "Read access unavailable: an active paired account with the required permission is required."
        )


async def _telegram_read_auth_context(
    update: Update, required_permission: str
) -> AuthContext | None:
    identity = _private_telegram_identity(update)
    if identity is None:
        return None
    try:
        from app.services.telegram_pairing import resolve_telegram_read_auth_context

        async with AsyncSessionLocal() as db:
            auth = await resolve_telegram_read_auth_context(
                db,
                identity[0],
                identity[1],
                required_permission=required_permission,
            )
    except Exception as exc:
        logger.warning("Telegram read identity lookup failed: %s", type(exc).__name__)
        return None

    if (
        not isinstance(auth, AuthContext)
        or not auth.is_authenticated
        or auth.is_mock_auth
        or auth.auth_method != "telegram_binding"
        or not isinstance(auth.organization_id, UUID)
        or auth.organization_id.int == 0
        or not auth.has_permission(required_permission)
    ):
        return None
    return auth


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show counts scoped to the authenticated Telegram user's organization."""
    auth = await _telegram_read_auth_context(update, "system:read")
    if auth is None:
        await _deny_telegram_read_command(update)
        return
    try:
        from sqlalchemy import func

        from app.models.assistant_task import AssistantTask
        from app.models.contact import Contact
        from app.models.email_thread import EmailThread
        from app.models.job_posting import JobPosting

        async with AsyncSessionLocal() as db:
            jobs = int((await db.execute(
                select(func.count(JobPosting.id)).where(
                    JobPosting.organization_id == auth.organization_id
                )
            )).scalar_one())
            contacts = int((await db.execute(
                select(func.count(Contact.id)).where(
                    Contact.organization_id == auth.organization_id,
                    Contact.is_deleted.is_(False),
                )
            )).scalar_one())
            tasks = int((await db.execute(
                select(func.count(AssistantTask.id)).where(
                    AssistantTask.organization_id == auth.organization_id,
                    AssistantTask.status == "pending",
                )
            )).scalar_one())
            unread_threads = int((await db.execute(
                select(func.count(EmailThread.id)).where(
                    EmailThread.organization_id == auth.organization_id,
                    EmailThread.status == "unread",
                )
            )).scalar_one())

        message = f"""
📊 Tenant Summary

📈 Current Stats:
• Jobs: {jobs}
• Contacts: {contacts}
• Pending Tasks: {tasks}
• Unread Emails: {unread_threads}

🕐 Last Updated: {datetime.now(UTC).strftime('%H:%M:%S UTC')}
"""
        await _telegram_command_message(update).reply_text(message)
    except Exception as exc:
        logger.error("Status command failed: error=%s", type(exc).__name__)
        await _telegram_command_message(update).reply_text("❌ Failed to get tenant summary")


async def jobs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show high-scoring jobs belonging to the paired organization."""
    auth = await _telegram_read_auth_context(update, "workflow:read")
    if auth is None:
        await _deny_telegram_read_command(update)
        return
    try:
        from app.models.job_posting import JobPosting

        async with AsyncSessionLocal() as db:
            jobs = list((await db.execute(
                select(JobPosting).where(
                    JobPosting.organization_id == auth.organization_id,
                    JobPosting.status == "discovered",
                    JobPosting.match_score >= 7,
                ).order_by(JobPosting.match_score.desc()).limit(5)
            )).scalars().all())

        if not jobs:
            await _telegram_command_message(update).reply_text("📭 No high-scoring jobs found")
            return
        message = "🎯 Top Job Opportunities:\n\n"
        for i, job in enumerate(jobs, 1):
            score = float(job.match_score) if job.match_score else 0
            message += f"{i}. {job.title}\n"
            message += f"   Company: {job.company or 'N/A'}\n"
            message += f"   Platform: {job.source_platform or 'N/A'}\n"
            message += f"   Score: {score:.1f}/10\n"
            if job.source_url:
                message += f"   URL: {job.source_url[:50]}...\n"
            message += "\n"
        await _telegram_command_message(update).reply_text(message)
    except Exception as exc:
        logger.error("Jobs command failed: error=%s", type(exc).__name__)
        await _telegram_command_message(update).reply_text("❌ Failed to get jobs")


async def contacts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show valuable contacts belonging to the paired organization."""
    auth = await _telegram_read_auth_context(update, "leads:read")
    if auth is None:
        await _deny_telegram_read_command(update)
        return
    try:
        from app.models.contact import Contact

        async with AsyncSessionLocal() as db:
            contacts = list((await db.execute(
                select(Contact).where(
                    Contact.organization_id == auth.organization_id,
                    Contact.is_deleted.is_(False),
                    Contact.value_score >= 7,
                ).order_by(Contact.value_score.desc()).limit(5)
            )).scalars().all())

        if not contacts:
            await _telegram_command_message(update).reply_text("📭 No high-value contacts found")
            return
        message = "👥 Top Contacts:\n\n"
        for i, contact in enumerate(contacts, 1):
            score = float(contact.value_score) if contact.value_score else 0
            message += f"{i}. {contact.name}\n"
            message += f"   Title: {contact.role or 'N/A'}\n"
            message += f"   Company: {contact.company or 'N/A'}\n"
            message += f"   Score: {score:.1f}/10\n"
            if contact.linkedin_url:
                message += f"   LinkedIn: {contact.linkedin_url[:50]}...\n"
            message += "\n"
        await _telegram_command_message(update).reply_text(message)
    except Exception as exc:
        logger.error("Contacts command failed: error=%s", type(exc).__name__)
        await _telegram_command_message(update).reply_text("❌ Failed to get contacts")


async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show urgent tasks belonging to the paired organization."""
    auth = await _telegram_read_auth_context(update, "workflow:read")
    if auth is None:
        await _deny_telegram_read_command(update)
        return
    try:
        from app.models.assistant_task import AssistantTask

        async with AsyncSessionLocal() as db:
            now = datetime.now(UTC)
            query = (
                select(AssistantTask)
                .where(
                    AssistantTask.organization_id == auth.organization_id,
                    AssistantTask.status == "pending",
                    (AssistantTask.due_date < now) | (AssistantTask.priority >= 7),
                )
                .order_by(AssistantTask.priority.desc())
                .limit(10)
            )
            tasks = list((await db.execute(query)).scalars().all())

        if not tasks:
            await _telegram_command_message(update).reply_text("✅ No urgent tasks!")
            return
        message = "📌 Your Tasks:\n\n"
        for i, task in enumerate(tasks, 1):
            due_date = task.due_date
            if due_date is not None and due_date.tzinfo is None:
                due_date = due_date.replace(tzinfo=UTC)
            status_emoji = "⚠️" if due_date and due_date < now else "🔥"
            due_str = due_date.strftime("%b %d") if due_date else "No date"
            message += f"{status_emoji} {i}. {task.title}\n"
            message += f"   Priority: {task.priority}/10\n"
            message += f"   Due: {due_str}\n\n"
        await _telegram_command_message(update).reply_text(message)
    except Exception as exc:
        logger.error("Tasks command failed: error=%s", type(exc).__name__)
        await _telegram_command_message(update).reply_text("❌ Failed to get tasks")


async def costs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fail closed until usage rows have authoritative tenant attribution."""
    auth = await _telegram_read_auth_context(update, "analytics:read")
    if auth is None:
        await _deny_telegram_read_command(update)
        return
    await _telegram_command_message(update).reply_text(
        "Costs unavailable: usage records are not attributed to an organization yet."
    )


async def briefing_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fail closed until every briefing section is tenant-scoped."""
    auth = await _telegram_read_auth_context(update, "workflow:run")
    if auth is None:
        await _deny_telegram_read_command(update)
        return
    await _telegram_command_message(update).reply_text(
        "Daily briefing unavailable until every section is scoped to this organization."
    )


async def outreach_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = getattr(update, "effective_chat", None)
    user = getattr(update, "effective_user", None)
    message = getattr(update, "effective_message", None) or getattr(update, "message", None)
    if (
        chat is None
        or user is None
        or message is None
        or getattr(chat, "type", None) != "private"
        or str(chat.id) != str(user.id)
    ):
        return

    auth = await _telegram_read_auth_context(update, "workflow:run")
    if (
        not isinstance(auth, AuthContext)
        or not auth.is_authenticated
        or auth.is_mock_auth
        or auth.auth_method != "telegram_binding"
        or not isinstance(auth.organization_id, UUID)
        or auth.organization_id.int == 0
        or not auth.has_permission("workflow:run")
        or not auth.has_permission("leads:read")
    ):
        await message.reply_text(
            "Outreach unavailable: active paired account with workflow:run and leads:read permissions required."
        )
        return

    try:
        from app.agents.outreach_agent import outreach_agent

        result = await outreach_agent.run(auth=auth)
        await message.reply_text(str(result))
    except Exception as exc:
        logger.warning("Outreach command failed: %s", type(exc).__name__)
        await message.reply_text("❌ Failed to run outreach")


async def pair_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bind this private chat using a short-lived code issued to its owner."""
    chat = getattr(update, "effective_chat", None)
    user = getattr(update, "effective_user", None)
    message = getattr(update, "effective_message", None)
    if (
        chat is None
        or user is None
        or getattr(chat, "type", None) != "private"
        or str(chat.id) != str(user.id)
        or message is None
    ):
        return

    args = list(getattr(context, "args", None) or [])
    if len(args) != 1:
        await message.reply_text("Pairing requires one valid code from your authenticated account.")
        return

    try:
        from app.services.telegram_pairing import consume_pairing_code

        async with AsyncSessionLocal() as db:
            paired = await consume_pairing_code(db, args[0], str(user.id), str(chat.id))
    except Exception as exc:
        logger.warning("Telegram pairing failed: %s", type(exc).__name__)
        paired = False

    if paired:
        await message.reply_text(
            "Telegram account paired. Approval decisions remain tenant-scoped; no action is executed."
        )
    else:
        await message.reply_text("Pairing code invalid, expired, used, or no longer authorized.")


async def _approval_callback_auth(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE | None = None,
) -> AuthContext | None:
    """Resolve authority from a persisted binding and the user's current DB role."""
    chat = update.effective_chat
    user = getattr(update, "effective_user", None)
    if (
        chat is None
        or user is None
        or getattr(chat, "type", None) != "private"
        or str(chat.id) != str(user.id)
    ):
        return None
    try:
        from app.services.telegram_pairing import resolve_telegram_auth_context

        async with AsyncSessionLocal() as db:
            return await resolve_telegram_auth_context(db, str(user.id), str(chat.id))
    except Exception as exc:
        logger.warning("Telegram approval identity lookup failed: %s", type(exc).__name__)
        return None


async def approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Persist one tenant-bound decision; delivery requires a provider reference."""
    query = update.callback_query
    await query.answer()
    auth = await _approval_callback_auth(update, context)
    if auth is None:
        await query.edit_message_text("Approval unavailable: verified tenant/chat binding required.")
        return
    try:
        parts = query.data.split(":", 2)
        if len(parts) == 3 and parts[0] == "approvalbatch":
            _, action_token, batch_ref_or_key = parts
            if action_token in {"a", "r"}:
                from app.telegram_bot.keyboards import is_approval_batch_callback_ref

                if not is_approval_batch_callback_ref(batch_ref_or_key):
                    raise ValueError("approval_batch_reference_invalid")
                from app.core.control_plane import resolve_approval_batch_reference

                action = "approve" if action_token == "a" else "reject"
                resolve_batch = resolve_approval_batch_reference
                batch_key = batch_ref_or_key
            elif action_token in {"approve", "reject"}:
                if not batch_ref_or_key or len(batch_ref_or_key) > 200:
                    raise ValueError("approval_batch_key_invalid")
                from app.core.control_plane import resolve_approval_batch

                action = action_token
                resolve_batch = resolve_approval_batch
                batch_key = batch_ref_or_key
            else:
                raise ValueError("approval_batch_action_invalid")

            decision = "approved" if action == "approve" else "rejected"
            resolution = await resolve_batch(
                batch_key,
                decision,
                note=f"Via Telegram owner {auth.actor_id}",
                organization_id=auth.organization_id,
                audit_actor_id=auth.actor_id,
                audit_source="telegram",
                emit_events=False,
                return_details=True,
            )
            if resolution.decision_count == 0:
                if resolution.expired_count:
                    decision_word = "approved" if action == "approve" else "rejected"
                    await query.edit_message_text(
                        f"No approvals were {decision_word}; {resolution.expired_count} expired; no action executed."
                    )
                else:
                    await query.edit_message_text(
                        "No pending approvals found for this organization."
                    )
            else:
                decision_label = "Approved" if action == "approve" else "Rejected"
                approval_word = "approval" if resolution.decision_count == 1 else "approvals"
                expired_suffix = (
                    f"; {resolution.expired_count} expired"
                    if resolution.expired_count
                    else ""
                )
                await query.edit_message_text(
                    f"{decision_label} {resolution.decision_count} {approval_word}"
                    f"{expired_suffix}; no action executed."
                )
            return
        if len(parts) == 3 and parts[0] == "approval":
            _, action, raw_id = parts
        elif len(parts) == 2:
            action, raw_id = parts
        else:
            raise ValueError("approval_callback_format_invalid")
        if action not in {"approve", "reject"}:
            raise ValueError("approval_action_invalid")
        request_id = UUID(raw_id)
        from app.core.control_plane import ApprovalAlreadyProcessedError, resolve_approval_request
        try:
            approval = await resolve_approval_request(
                request_id, "approved" if action == "approve" else "rejected",
                note=f"Via Telegram owner {auth.actor_id}",
                organization_id=auth.organization_id,
                audit_actor_id=UUID(auth.actor_id),
                emit_events=False,
                update_related_subject=True,
            )
        except ApprovalAlreadyProcessedError:
            await query.edit_message_text("Approval already processed; no action executed.")
            return
        if approval is None:
            await query.edit_message_text("Approval not found for this organization.")
            return
        if approval.status != "approved":
            await query.edit_message_text(f"Decision: {approval.status}; no action executed.")
            return
        await query.edit_message_text("Approved; action not executed; no message sent.")
    except Exception as exc:
        logger.warning("Approval callback outcome unverified: %s", type(exc).__name__)
        await query.edit_message_text("Approval outcome unverified; no automatic retry.")


async def _execute_approved_action(approval: ApprovalRequest) -> bool:
    """Fail closed until approval delivery has a consent-aware service API.

    The Telegram approval payload contains free-form recipient and body fields.
    Calling a provider adapter directly would bypass centralized recipient
    consent and provider-send policy. Keep the decision persisted, but do not
    send until an approved service API can enforce both gates.
    """
    return False


async def send_message(
    text: str,
    parse_mode: str | None = None,
    reply_markup: Any | None = None,
    *,
    chat_id: str | int | None = None,
) -> bool:
    """
    Send message to user via Telegram.
    
    Args:
        text: Message text
        parse_mode: Parse mode (None sends plain text)
    
    Returns:
        True if sent successfully
    """
    if not settings.HAS_REAL_TELEGRAM_TOKEN:
        logger.warning("Telegram credentials not configured; message not sent")
        return False

    target_chat_id: str | int | None
    if chat_id is None:
        if not settings.HAS_REAL_TELEGRAM_CHAT_ID:
            logger.warning("Telegram credentials not configured; message not sent")
            return False
        target_chat_id = settings.TELEGRAM_CHAT_ID
    else:
        raw_chat_id = str(chat_id).strip()
        if not raw_chat_id.isdecimal() or int(raw_chat_id) <= 0:
            logger.warning("Invalid private Telegram chat target; message not sent")
            return False
        target_chat_id = raw_chat_id

    if not target_chat_id:
        logger.warning("Telegram chat ID not set; message not sent")
        return False

    try:
        # Fresh client per send: a pooled httpx client stays bound to the event loop
        # that created it, and each Celery task runs in its own asyncio.run() loop.
        async with Bot(token=settings.TELEGRAM_BOT_TOKEN) as bot:
            await bot.send_message(
                chat_id=target_chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
        return True
    except Exception as exc:
        logger.error("Failed to send Telegram message: error=%s", type(exc).__name__)
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
    except Exception as exc:
        logger.error("Failed to send approval request: error=%s", type(exc).__name__)
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
    _app.add_handler(CommandHandler("pair", pair_command))
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


def get_application() -> Application | None:
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
                logger.warning(
                    "Telegram polling conflict detected; retrying (error=%s)",
                    type(exc).__name__,
                )
                await asyncio.sleep(60)
                continue
            logger.error(
                "Telegram polling crashed; restarting (error=%s)",
                type(exc).__name__,
            )
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
