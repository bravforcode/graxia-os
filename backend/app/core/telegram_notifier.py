"""
Real-time Telegram Notification Service

Provides comprehensive progress tracking and real-time notifications
to Telegram for all system activities, agent actions, and user operations.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from enum import Enum

from app.config import settings
from app.telegram_bot.bot import send_message
from app.core.event_bus import event_bus

logger = logging.getLogger(__name__)


class NotificationPriority(Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationType(Enum):
    SYSTEM = "system"
    AGENT = "agent"
    JOB = "job"
    CONTACT = "contact"
    TASK = "task"
    EMAIL = "email"
    COST = "cost"
    APPROVAL = "approval"
    PROGRESS = "progress"
    ERROR = "error"
    SUCCESS = "success"


class TelegramNotifier:
    """
    Central notification service for real-time Telegram updates.
    Integrates with event bus to provide comprehensive progress tracking.
    """

    def __init__(self):
        self._initialized = False
        self._notification_count = 0
        self._last_reset = datetime.now(timezone.utc)
        self._rate_limit = 30  # notifications per minute
        self._pending_progress: dict[str, dict] = {}  # Track ongoing operations

    async def initialize(self) -> bool:
        """Initialize the notifier and verify Telegram connectivity."""
        if not settings.HAS_REAL_TELEGRAM_TOKEN or not settings.HAS_REAL_TELEGRAM_CHAT_ID:
            logger.warning("TelegramNotifier: Credentials not configured")
            return False

        # Send startup notification
        startup_msg = f"""
🚀 **Personal OS Started**

⏰ Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
🌐 Environment: {settings.APP_ENV}
🤖 AI Models: OpenClaw + Gemini
📊 Real-time notifications: ACTIVE

System is ready and monitoring your activities.
        """.strip()

        success = await send_message(startup_msg, parse_mode="Markdown")
        if success:
            self._initialized = True
            logger.info("TelegramNotifier: Initialized successfully")
            await self._register_event_handlers()
        else:
            logger.error("TelegramNotifier: Failed to send startup message")

        return self._initialized

    async def _register_event_handlers(self) -> None:
        """Register handlers for system events."""
        event_bus.subscribe("agent.started", self._on_agent_started)
        event_bus.subscribe("agent.completed", self._on_agent_completed)
        event_bus.subscribe("agent.error", self._on_agent_error)
        event_bus.subscribe("job.discovered", self._on_job_discovered)
        event_bus.subscribe("job.scored", self._on_job_scored)
        event_bus.subscribe("contact.added", self._on_contact_added)
        event_bus.subscribe("contact.created", self._on_contact_added)
        event_bus.subscribe("task.created", self._on_task_created)
        event_bus.subscribe("task.completed", self._on_task_completed)
        event_bus.subscribe("email.received", self._on_email_received)
        # Approval requests are delivered directly from control_plane so the
        # inline keyboard payload is preserved without duplicate Telegram pings.
        event_bus.subscribe("approval.resolved", self._on_approval_resolved)
        event_bus.subscribe("cost.threshold", self._on_cost_threshold)
        event_bus.subscribe("system.alert", self._on_system_alert)
        event_bus.subscribe("operation.progress", self._on_progress_update)
        logger.info("TelegramNotifier: Event handlers registered")

    def _check_rate_limit(self) -> bool:
        """Check if we can send another notification."""
        now = datetime.now(timezone.utc)
        if (now - self._last_reset).total_seconds() > 60:
            self._notification_count = 0
            self._last_reset = now
        return self._notification_count < self._rate_limit

    async def notify(
        self,
        message: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        notification_type: NotificationType = NotificationType.SYSTEM,
        parse_mode: str = "Markdown"
    ) -> bool:
        """
        Send a notification with rate limiting and priority handling.

        Args:
            message: The message to send
            priority: Priority level (affects rate limiting)
            notification_type: Type of notification
            parse_mode: Telegram parse mode

        Returns:
            True if sent successfully
        """
        if not settings.HAS_REAL_TELEGRAM_TOKEN:
            return False

        # Urgent messages bypass rate limit
        if priority != NotificationPriority.URGENT and not self._check_rate_limit():
            logger.warning(f"TelegramNotifier: Rate limit reached, skipping {notification_type.value}")
            return False

        # Add emoji prefix based on type
        emoji_map = {
            NotificationType.SYSTEM: "🖥️",
            NotificationType.AGENT: "🤖",
            NotificationType.JOB: "💼",
            NotificationType.CONTACT: "👤",
            NotificationType.TASK: "📌",
            NotificationType.EMAIL: "📧",
            NotificationType.COST: "💰",
            NotificationType.APPROVAL: "🔔",
            NotificationType.PROGRESS: "📊",
            NotificationType.ERROR: "❌",
            NotificationType.SUCCESS: "✅",
        }
        emoji = emoji_map.get(notification_type, "📢")

        formatted_message = f"{emoji} {message}"

        try:
            success = await send_message(formatted_message, parse_mode=parse_mode)
            if success:
                self._notification_count += 1
            return success
        except Exception as e:
            logger.error(f"TelegramNotifier: Failed to send notification: {e}")
            return False

    async def notify_progress_start(
        self,
        operation_id: str,
        title: str,
        total_steps: int = 100,
        description: str = ""
    ) -> None:
        """Start tracking a multi-step operation."""
        self._pending_progress[operation_id] = {
            "title": title,
            "current": 0,
            "total": total_steps,
            "description": description,
            "started_at": datetime.now(timezone.utc),
            "message_id": None,
        }

        msg = f"**{title}**\n⏳ Starting..."
        if description:
            msg += f"\n_{description}_"

        await self.notify(msg, NotificationPriority.NORMAL, NotificationType.PROGRESS)

    async def notify_progress_update(
        self,
        operation_id: str,
        current_step: int,
        message: str = ""
    ) -> None:
        """Update progress on an ongoing operation."""
        if operation_id not in self._pending_progress:
            return

        progress = self._pending_progress[operation_id]
        progress["current"] = current_step

        total = progress["total"]
        percentage = min(100, int((current_step / total) * 100))
        bar_length = 20
        filled = int((percentage / 100) * bar_length)
        bar = "█" * filled + "░" * (bar_length - filled)

        elapsed = (datetime.now(timezone.utc) - progress["started_at"]).total_seconds()

        status_msg = f"""
**{progress['title']}**
[{bar}] {percentage}%
📊 Step {current_step}/{total}
⏱️ {elapsed:.0f}s elapsed
        """.strip()

        if message:
            status_msg += f"\n📝 {message}"

        # Only send update every 10% or on completion to avoid spam
        if percentage % 10 == 0 or current_step >= total:
            await self.notify(status_msg, NotificationPriority.LOW, NotificationType.PROGRESS)

    async def notify_progress_complete(
        self,
        operation_id: str,
        success: bool = True,
        result_message: str = ""
    ) -> None:
        """Mark an operation as complete."""
        if operation_id not in self._pending_progress:
            return

        progress = self._pending_progress.pop(operation_id)
        elapsed = (datetime.now(timezone.utc) - progress["started_at"]).total_seconds()

        status_emoji = "✅" if success else "❌"
        status_text = "Completed" if success else "Failed"

        msg = f"""
{status_emoji} **{progress['title']}** - {status_text}
⏱️ Duration: {elapsed:.1f}s
        """.strip()

        if result_message:
            msg += f"\n📝 {result_message}"

        await self.notify(msg, NotificationPriority.NORMAL, NotificationType.SUCCESS if success else NotificationType.ERROR)

    # Event handlers
    async def _on_agent_started(self, payload: dict) -> None:
        agent_name = payload.get("agent", "Unknown")
        await self.notify(
            f"🤖 Agent **{agent_name}** started executing",
            NotificationPriority.LOW,
            NotificationType.AGENT
        )

    async def _on_agent_completed(self, payload: dict) -> None:
        agent_name = payload.get("agent", "Unknown")
        duration = payload.get("duration_seconds", 0)
        result_summary = payload.get("result_summary", "")

        msg = f"✅ Agent **{agent_name}** completed"
        if duration:
            msg += f" ({duration:.1f}s)"
        if result_summary:
            msg += f"\n📝 {result_summary}"

        await self.notify(msg, NotificationPriority.NORMAL, NotificationType.AGENT)

    async def _on_agent_error(self, payload: dict) -> None:
        agent_name = payload.get("agent", "Unknown")
        error = payload.get("error", "Unknown error")
        await self.notify(
            f"❌ Agent **{agent_name}** failed\n⚠️ {error[:200]}",
            NotificationPriority.HIGH,
            NotificationType.ERROR
        )

    async def _on_job_discovered(self, payload: dict) -> None:
        count = payload.get("count", 0)
        source = payload.get("source", "Unknown")
        if count > 0:
            await self.notify(
                f"💼 Discovered **{count}** new job(s) from {source}",
                NotificationPriority.LOW,
                NotificationType.JOB
            )

    async def _on_job_scored(self, payload: dict) -> None:
        title = payload.get("title", "Unknown")
        score = payload.get("score", 0)
        company = payload.get("company", "")
        if score >= 8.0:
            await self.notify(
                f"🎯 High-scoring job found!\n💼 {title} at {company}\n⭐ Score: {score:.1f}/10",
                NotificationPriority.HIGH,
                NotificationType.JOB
            )

    async def _on_contact_added(self, payload: dict) -> None:
        name = payload.get("name", "Unknown")
        company = payload.get("company", "")
        score = payload.get("score", 0)
        await self.notify(
            f"👤 New contact added: **{name}**\n🏢 {company}\n⭐ Score: {score:.1f}/10",
            NotificationPriority.LOW,
            NotificationType.CONTACT
        )

    async def _on_task_created(self, payload: dict) -> None:
        title = payload.get("title", "")
        priority = payload.get("priority", 0)
        if priority >= 7:
            await self.notify(
                f"📌 High priority task created: **{title}**\n🔥 Priority: {priority}/10",
                NotificationPriority.HIGH,
                NotificationType.TASK
            )

    async def _on_task_completed(self, payload: dict) -> None:
        title = payload.get("title", "")
        await self.notify(
            f"✅ Task completed: **{title}**",
            NotificationPriority.NORMAL,
            NotificationType.TASK
        )

    async def _on_email_received(self, payload: dict) -> None:
        subject = payload.get("subject", "")
        sender = payload.get("sender", "")
        priority = payload.get("priority", "")
        if priority in ["urgent", "high"]:
            await self.notify(
                f"📧 Priority email from **{sender}**\n📨 {subject[:100]}",
                NotificationPriority.HIGH,
                NotificationType.EMAIL
            )

    async def _on_approval_requested(self, payload: dict) -> None:
        title = payload.get("title", "")
        action_type = payload.get("action_type", "")
        await self.notify(
            f"🔔 Approval requested: **{title}**\n⚡ Type: {action_type}\nReply with /approvals to review",
            NotificationPriority.URGENT,
            NotificationType.APPROVAL
        )

    async def _on_approval_resolved(self, payload: dict) -> None:
        title = payload.get("title", "")
        status = payload.get("status", "")
        resolution_note = payload.get("resolution_note", "")
        msg = f"✅ Approval resolved: **{title}**\n📋 Status: {status}"
        if resolution_note:
            msg += f"\n📝 {resolution_note}"
        await self.notify(
            msg,
            NotificationPriority.NORMAL,
            NotificationType.APPROVAL
        )

    async def _on_cost_threshold(self, payload: dict) -> None:
        threshold = payload.get("threshold", "")
        current = payload.get("current", 0)
        limit = payload.get("limit", 0)
        await self.notify(
            f"💰 Cost alert: **{threshold}** threshold reached\n📊 {current:.2f} / {limit:.2f} USD",
            NotificationPriority.HIGH,
            NotificationType.COST
        )

    async def _on_system_alert(self, payload: dict) -> None:
        level = payload.get("level", "info")
        message = payload.get("message", "")
        priority = NotificationPriority.URGENT if level == "critical" else NotificationPriority.HIGH
        await self.notify(
            f"🚨 System Alert ({level.upper()})\n{message}",
            priority,
            NotificationType.ERROR if level in ["critical", "error"] else NotificationType.SYSTEM
        )

    async def _on_progress_update(self, payload: dict) -> None:
        operation = payload.get("operation", "")
        percent = payload.get("percent", 0)
        message = payload.get("message", "")

        # Only notify on significant progress to avoid spam
        if percent in [25, 50, 75, 100] or (percent < 5 and percent > 0):
            await self.notify(
                f"📊 **{operation}**: {percent}% complete\n{message}",
                NotificationPriority.LOW,
                NotificationType.PROGRESS
            )

    async def send_daily_summary(self) -> None:
        """Send daily activity summary."""
        from app.agents.personal_assistant import personal_assistant_agent

        try:
            briefing = await personal_assistant_agent.generate_daily_briefing()
            await self.notify(
                f"📋 **Daily Briefing**\n\n{briefing[:3000]}",
                NotificationPriority.NORMAL,
                NotificationType.SYSTEM
            )
        except Exception as e:
            logger.error(f"Failed to send daily summary: {e}")

    async def test_connection(self) -> bool:
        """Test Telegram connectivity and return status."""
        if not settings.HAS_REAL_TELEGRAM_TOKEN:
            logger.warning("Telegram: No bot token configured")
            return False

        test_msg = "🔔 **Test Notification**\n✅ Telegram integration is working!"
        success = await send_message(test_msg, parse_mode="Markdown")

        if success:
            logger.info("Telegram: Connection test successful")
        else:
            logger.error("Telegram: Connection test failed")

        return success


# Global instance
telegram_notifier = TelegramNotifier()


async def initialize_notifier() -> bool:
    """Initialize the global notifier instance."""
    return await telegram_notifier.initialize()


async def test_telegram_connection() -> bool:
    """Test Telegram connectivity."""
    return await telegram_notifier.test_connection()
