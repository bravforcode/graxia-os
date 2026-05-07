"""
Personal Assistant Agent

Provides daily briefings, task management, notifications,
and cost monitoring. Acts as the central coordinator.
"""
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, func, select

from app.agents.base import BaseAgent
from app.database import AsyncSessionLocal
from app.models.assistant_task import AssistantTask
from app.models.contact import Contact
from app.models.email_thread import EmailThread
from app.models.job_posting import JobPosting
from app.models.openclaw_usage import OpenClawUsage

logger = logging.getLogger(__name__)


class PersonalAssistantAgent(BaseAgent):
    """
    Personal Assistant Agent - central coordinator and user interface.
    
    Features:
    - Daily briefings (morning summary)
    - Task management and reminders
    - Cost monitoring and alerts
    - Notification rate limiting (max 10/hour)
    - Telegram command handlers
    - System health monitoring
    
    Commands:
    - /status - System status and today's summary
    - /jobs - Top job opportunities
    - /contacts - Top contacts
    - /tasks - Pending tasks
    - /costs - Cost breakdown
    - /briefing - Generate daily briefing
    """
    
    name = "personal_assistant"
    
    def __init__(self):
        super().__init__()
        self.max_notifications_per_hour = 10
        self._notification_count = 0
        self._notification_reset_time = datetime.now(UTC)
    
    async def generate_daily_briefing(self) -> str:
        """
        Generate comprehensive daily briefing.
        
        Includes:
        - Top 5 job opportunities
        - Urgent tasks and deadlines
        - Important emails
        - Top contacts to reach out to
        - Yesterday's activity summary
        - Cost summary
        """
        logger.info("PersonalAssistant: generating daily briefing")
        
        try:
            briefing_parts = []
            
            # Header
            today = datetime.now(UTC).strftime("%A, %B %d, %Y")
            briefing_parts.append(f"📋 Daily Briefing - {today}\n")
            
            # 1. Top Jobs
            jobs_section = await self._get_jobs_section()
            briefing_parts.append(jobs_section)
            
            # 2. Urgent Tasks
            tasks_section = await self._get_tasks_section()
            briefing_parts.append(tasks_section)
            
            # 3. Important Emails
            emails_section = await self._get_emails_section()
            briefing_parts.append(emails_section)
            
            # 4. Top Contacts
            contacts_section = await self._get_contacts_section()
            briefing_parts.append(contacts_section)
            
            # 5. Yesterday's Activity
            activity_section = await self._get_activity_section()
            briefing_parts.append(activity_section)
            
            # 6. Cost Summary
            cost_section = await self._get_cost_section()
            briefing_parts.append(cost_section)
            
            # 7. Recommendations
            recommendations = await self._get_recommendations()
            briefing_parts.append(recommendations)
            
            briefing = "\n".join(briefing_parts)
            
            await self.log_audit(
                action="personal_assistant.daily_briefing",
                details={"length": len(briefing)},
                success=True
            )
            
            return briefing
        except Exception as e:
            logger.error(f"Daily briefing generation failed: {e}")
            return "❌ Failed to generate daily briefing. Please check logs."
    
    async def _get_jobs_section(self) -> str:
        """Get top 5 jobs section."""
        try:
            async with AsyncSessionLocal() as db:
                query = (
                    select(JobPosting)
                    .where(JobPosting.status == "discovered")
                    .where(JobPosting.match_score >= Decimal("7.0"))
                    .order_by(JobPosting.match_score.desc())
                    .limit(5)
                )
                result = await db.execute(query)
                jobs = list(result.scalars().all())
                
                if not jobs:
                    return "\n🎯 Top Jobs: No new high-scoring jobs today.\n"
                
                section = ["\n🎯 Top Jobs:"]
                for i, job in enumerate(jobs, 1):
                    score = float(job.match_score) if job.match_score else 0
                    section.append(
                        f"{i}. {job.title} at {job.company} "
                        f"({job.source_platform}) - Score: {score:.1f}/10"
                    )
                
                return "\n".join(section) + "\n"
        except Exception as e:
            logger.error(f"Jobs section failed: {e}")
            return "\n🎯 Top Jobs: Error loading jobs.\n"
    
    async def _get_tasks_section(self) -> str:
        """Get urgent and overdue tasks."""
        try:
            async with AsyncSessionLocal() as db:
                now = datetime.now(UTC)
                
                # Overdue tasks
                overdue_query = (
                    select(AssistantTask)
                    .where(AssistantTask.status == "pending")
                    .where(AssistantTask.due_date < now)
                    .order_by(AssistantTask.priority.desc())
                    .limit(5)
                )
                overdue_result = await db.execute(overdue_query)
                overdue = list(overdue_result.scalars().all())
                
                # Urgent tasks (due today or tomorrow)
                tomorrow = now + timedelta(days=1)
                urgent_query = (
                    select(AssistantTask)
                    .where(AssistantTask.status == "pending")
                    .where(and_(
                        AssistantTask.due_date >= now,
                        AssistantTask.due_date <= tomorrow
                    ))
                    .order_by(AssistantTask.priority.desc())
                    .limit(5)
                )
                urgent_result = await db.execute(urgent_query)
                urgent = list(urgent_result.scalars().all())
                
                section = ["\n📌 Tasks:"]
                
                if overdue:
                    section.append("⚠️ Overdue:")
                    for task in overdue:
                        section.append(f"  - {task.title} (Priority: {task.priority})")
                
                if urgent:
                    section.append("🔥 Due Soon:")
                    for task in urgent:
                        due_str = task.due_date.strftime("%b %d") if task.due_date else "No date"
                        section.append(f"  - {task.title} (Due: {due_str})")
                
                if not overdue and not urgent:
                    section.append("✅ No urgent tasks!")
                
                return "\n".join(section) + "\n"
        except Exception as e:
            logger.error(f"Tasks section failed: {e}")
            return "\n📌 Tasks: Error loading tasks.\n"
    
    async def _get_emails_section(self) -> str:
        """Get important unread emails."""
        try:
            async with AsyncSessionLocal() as db:
                query = (
                    select(EmailThread)
                    .where(EmailThread.status == "unread")
                    .where(EmailThread.category.in_(["urgent", "important"]))
                    .order_by(EmailThread.priority.desc())
                    .limit(5)
                )
                result = await db.execute(query)
                emails = list(result.scalars().all())
                
                if not emails:
                    return "\n📧 Emails: No urgent emails.\n"
                
                section = ["\n📧 Important Emails:"]
                for email in emails:
                    category_emoji = "🔴" if email.category == "urgent" else "🟡"
                    section.append(f"{category_emoji} {email.subject[:50]}...")
                
                return "\n".join(section) + "\n"
        except Exception as e:
            logger.error(f"Emails section failed: {e}")
            return "\n📧 Emails: Error loading emails.\n"
    
    async def _get_contacts_section(self) -> str:
        """Get top contacts to reach out to."""
        try:
            async with AsyncSessionLocal() as db:
                # Contacts with no recent interaction
                week_ago = datetime.now(UTC).date() - timedelta(days=7)
                query = (
                    select(Contact)
                    .where(Contact.value_score >= 7)
                    .where(Contact.is_deleted.is_(False))
                    .where(
                        (Contact.last_contacted_at == None) |
                        (Contact.last_contacted_at < week_ago)
                    )
                    .order_by(Contact.value_score.desc())
                    .limit(3)
                )
                result = await db.execute(query)
                contacts = list(result.scalars().all())
                
                if not contacts:
                    return "\n👥 Contacts: Network is up to date!\n"
                
                section = ["\n👥 Contacts to Reach Out:"]
                for contact in contacts:
                    score = float(contact.value_score) if contact.value_score else 0
                    role = contact.role or "Unknown role"
                    company = contact.company or "Unknown company"
                    section.append(
                        f"  - {contact.name} ({role} at {company}) "
                        f"- Score: {score:.1f}/10"
                    )
                
                return "\n".join(section) + "\n"
        except Exception as e:
            logger.error(f"Contacts section failed: {e}")
            return "\n👥 Contacts: Error loading contacts.\n"
    
    async def _get_activity_section(self) -> str:
        """Get yesterday's activity summary."""
        try:
            async with AsyncSessionLocal() as db:
                yesterday = datetime.now(UTC) - timedelta(days=1)
                today = datetime.now(UTC)
                
                # Jobs discovered
                jobs_query = select(func.count(JobPosting.id)).where(
                    and_(
                        JobPosting.created_at >= yesterday,
                        JobPosting.created_at < today
                    )
                )
                jobs_result = await db.execute(jobs_query)
                jobs_count = jobs_result.scalar() or 0
                
                # Contacts added
                contacts_query = select(func.count(Contact.id)).where(
                    and_(
                        Contact.is_deleted.is_(False),
                        Contact.created_at >= yesterday,
                        Contact.created_at < today
                    )
                )
                contacts_result = await db.execute(contacts_query)
                contacts_count = contacts_result.scalar() or 0
                
                # Tasks completed
                tasks_query = select(func.count(AssistantTask.id)).where(
                    and_(
                        AssistantTask.completed_at >= yesterday,
                        AssistantTask.completed_at < today
                    )
                )
                tasks_result = await db.execute(tasks_query)
                tasks_count = tasks_result.scalar() or 0
                
                section = [
                    "\n📊 Yesterday's Activity:",
                    f"  - Jobs discovered: {jobs_count}",
                    f"  - Contacts added: {contacts_count}",
                    f"  - Tasks completed: {tasks_count}"
                ]
                
                return "\n".join(section) + "\n"
        except Exception as e:
            logger.error(f"Activity section failed: {e}")
            return "\n📊 Yesterday's Activity: Error loading stats.\n"
    
    async def _get_cost_section(self) -> str:
        """Get cost summary."""
        try:
            async with AsyncSessionLocal() as db:
                today = datetime.now(UTC).date()
                
                # Today's cost
                today_query = select(func.sum(OpenClawUsage.cost_usd)).where(
                    func.date(OpenClawUsage.created_at) == today
                )
                today_result = await db.execute(today_query)
                today_cost = float(today_result.scalar() or 0)
                
                # Month's cost
                month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0)
                month_query = select(func.sum(OpenClawUsage.cost_usd)).where(
                    OpenClawUsage.created_at >= month_start
                )
                month_result = await db.execute(month_query)
                month_cost = float(month_result.scalar() or 0)
                
                # Budget limits
                daily_limit = 1.67  # $50/month ≈ $1.67/day
                monthly_limit = 50.0
                
                daily_pct = (today_cost / daily_limit) * 100 if daily_limit > 0 else 0
                monthly_pct = (month_cost / monthly_limit) * 100 if monthly_limit > 0 else 0
                
                section = [
                    "\n💰 Cost Summary:",
                    f"  - Today: ${today_cost:.2f} / ${daily_limit:.2f} ({daily_pct:.0f}%)",
                    f"  - Month: ${month_cost:.2f} / ${monthly_limit:.2f} ({monthly_pct:.0f}%)"
                ]
                
                # Warning if over 80%
                if daily_pct >= 80:
                    section.append("  ⚠️ Daily budget warning!")
                if monthly_pct >= 80:
                    section.append("  ⚠️ Monthly budget warning!")
                
                return "\n".join(section) + "\n"
        except Exception as e:
            logger.error(f"Cost section failed: {e}")
            return "\n💰 Cost Summary: Error loading costs.\n"
    
    async def _get_recommendations(self) -> str:
        """Get AI-powered recommendations."""
        try:
            # Get current state
            async with AsyncSessionLocal() as db:
                # Count pending tasks
                tasks_query = select(func.count(AssistantTask.id)).where(
                    AssistantTask.status == "pending"
                )
                tasks_result = await db.execute(tasks_query)
                pending_tasks = tasks_result.scalar() or 0
                
                # Count unread emails
                emails_query = select(func.count(EmailThread.id)).where(
                    EmailThread.status == "unread"
                )
                emails_result = await db.execute(emails_query)
                unread_emails = emails_result.scalar() or 0
                
                recommendations = ["\n💡 Recommendations:"]
                
                if pending_tasks > 10:
                    recommendations.append("  - You have many pending tasks. Consider prioritizing top 3.")
                
                if unread_emails > 20:
                    recommendations.append("  - Inbox needs attention. Process urgent emails first.")
                
                # Always add a positive note
                recommendations.append("  - Keep up the great work! 🚀")
                
                return "\n".join(recommendations) + "\n"
        except Exception as e:
            logger.error(f"Recommendations failed: {e}")
            return "\n💡 Recommendations: Stay focused!\n"
    
    async def send_notification(
        self,
        message: str,
        priority: str = "normal"
    ) -> bool:
        """
        Send notification via Telegram with rate limiting.
        
        Args:
            message: Notification message
            priority: Priority level (urgent, normal, low)
        
        Returns:
            True if sent, False if rate limited
        """
        # Check rate limit
        now = datetime.now(UTC)
        if now - self._notification_reset_time > timedelta(hours=1):
            self._notification_count = 0
            self._notification_reset_time = now
        
        # Allow urgent notifications to bypass limit
        if priority != "urgent" and self._notification_count >= self.max_notifications_per_hour:
            logger.warning("Notification rate limit reached")
            return False
        
        try:
            from app.telegram_bot.bot import send_message
            await send_message(message)
            
            self._notification_count += 1
            return True
        except Exception as e:
            logger.error(f"Notification failed: {e}")
            return False
    
    async def get_system_status(self) -> dict:
        """Get comprehensive system status."""
        try:
            async with AsyncSessionLocal() as db:
                # Jobs stats
                jobs_query = select(func.count(JobPosting.id))
                jobs_result = await db.execute(jobs_query)
                total_jobs = jobs_result.scalar() or 0
                
                # Contacts stats
                contacts_query = select(func.count(Contact.id))
                contacts_query = contacts_query.where(Contact.is_deleted.is_(False))
                contacts_result = await db.execute(contacts_query)
                total_contacts = contacts_result.scalar() or 0
                
                # Tasks stats
                tasks_query = select(func.count(AssistantTask.id)).where(
                    AssistantTask.status == "pending"
                )
                tasks_result = await db.execute(tasks_query)
                pending_tasks = tasks_result.scalar() or 0
                
                # Emails stats
                emails_query = select(func.count(EmailThread.id)).where(
                    EmailThread.status == "unread"
                )
                emails_result = await db.execute(emails_query)
                unread_emails = emails_result.scalar() or 0
                
                return {
                    "status": "healthy",
                    "total_jobs": total_jobs,
                    "total_contacts": total_contacts,
                    "pending_tasks": pending_tasks,
                    "unread_emails": unread_emails,
                    "timestamp": datetime.now(UTC).isoformat()
                }
        except Exception as e:
            logger.error(f"System status failed: {e}")
            return {"status": "error", "error": str(e)}


# Global instance
personal_assistant_agent = PersonalAssistantAgent()
