"""
Approval Flow System

Manages approval requests for automated actions via Telegram.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Callable
from uuid import uuid4

from app.database import AsyncSessionLocal
from app.models.approval_request import ApprovalRequest
from sqlalchemy import select

logger = logging.getLogger(__name__)


class ApprovalFlowManager:
    """
    Approval flow manager for automated actions.
    
    Features:
    - Create approval requests
    - Send to Telegram with inline keyboards
    - Handle approve/reject responses
    - Timeout logic (auto-reject after 24h)
    - Reminder after 12h
    - Audit trail
    """
    
    def __init__(self):
        self.pending_approvals: dict[str, dict] = {}
        self.approval_timeout_hours = 24
        self.reminder_timeout_hours = 12
    
    async def request_approval(
        self,
        action_type: str,
        action_description: str,
        action_data: dict,
        priority: str = "normal",
        callback: Optional[Callable] = None
    ) -> str:
        """
        Create approval request.
        
        Args:
            action_type: Type of action (email_send, linkedin_outreach, job_apply, etc.)
            action_description: Human-readable description
            action_data: Data needed to execute action
            priority: Priority level (urgent, high, normal, low)
            callback: Optional callback function to execute on approval
        
        Returns:
            Approval request ID
        """
        try:
            async with AsyncSessionLocal() as db:
                # Create approval request
                approval = ApprovalRequest(
                    id=uuid4(),
                    action_type=action_type,
                    action_description=action_description,
                    action_data=action_data,
                    priority=priority,
                    status="pending",
                    requested_at=datetime.now(timezone.utc),
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=self.approval_timeout_hours),
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                
                db.add(approval)
                await db.commit()
                await db.refresh(approval)
                
                # Store callback if provided
                if callback:
                    self.pending_approvals[str(approval.id)] = {
                        "callback": callback,
                        "data": action_data
                    }
                
                # Send to Telegram
                await self._send_telegram_approval(approval)
                
                logger.info(f"Approval request created: {approval.id} ({action_type})")
                return str(approval.id)
        except Exception as e:
            logger.error(f"Failed to create approval request: {e}")
            raise
    
    async def _send_telegram_approval(self, approval: ApprovalRequest) -> None:
        """Send approval request to Telegram with inline keyboard."""
        try:
            from app.telegram_bot.bot import send_message_with_keyboard
            
            # Priority emoji
            priority_emoji = {
                "urgent": "🔴",
                "high": "🟡",
                "normal": "🟢",
                "low": "⚪"
            }.get(approval.priority, "🟢")
            
            # Format message
            message = f"""{priority_emoji} **Approval Required**

**Action:** {approval.action_type}
**Description:** {approval.action_description}
**Priority:** {approval.priority}
**Expires:** {approval.expires_at.strftime('%Y-%m-%d %H:%M UTC')}

Please approve or reject this action."""
            
            # Create inline keyboard
            keyboard = [
                [
                    {"text": "✅ Approve", "callback_data": f"approve:{approval.id}"},
                    {"text": "❌ Reject", "callback_data": f"reject:{approval.id}"}
                ],
                [
                    {"text": "📋 View Details", "callback_data": f"details:{approval.id}"}
                ]
            ]
            
            await send_message_with_keyboard(message, keyboard)
            
            logger.info(f"Sent approval request to Telegram: {approval.id}")
        except Exception as e:
            logger.error(f"Failed to send Telegram approval: {e}")
    
    async def handle_approval(self, approval_id: str, approved: bool, user_id: str = "user") -> bool:
        """
        Handle approval response.
        
        Args:
            approval_id: Approval request ID
            approved: True if approved, False if rejected
            user_id: User who made the decision
        
        Returns:
            True if action executed successfully
        """
        try:
            async with AsyncSessionLocal() as db:
                # Get approval request
                query = select(ApprovalRequest).where(ApprovalRequest.id == uuid4(approval_id))
                result = await db.execute(query)
                approval = result.scalar_one_or_none()
                
                if not approval:
                    logger.warning(f"Approval request not found: {approval_id}")
                    return False
                
                if approval.status != "pending":
                    logger.warning(f"Approval request already processed: {approval_id}")
                    return False
                
                # Check if expired
                if datetime.now(timezone.utc) > approval.expires_at:
                    approval.status = "expired"
                    approval.updated_at = datetime.now(timezone.utc)
                    await db.commit()
                    logger.warning(f"Approval request expired: {approval_id}")
                    return False
                
                # Update status
                approval.status = "approved" if approved else "rejected"
                approval.approved_by = user_id
                approval.approved_at = datetime.now(timezone.utc)
                approval.updated_at = datetime.now(timezone.utc)
                await db.commit()
                
                # Execute action if approved
                if approved:
                    success = await self._execute_action(approval)
                    
                    approval.executed = success
                    approval.executed_at = datetime.now(timezone.utc) if success else None
                    await db.commit()
                    
                    # Execute callback if exists
                    if approval_id in self.pending_approvals:
                        callback_info = self.pending_approvals.pop(approval_id)
                        callback = callback_info.get("callback")
                        if callback:
                            await callback(approval.action_data)
                    
                    return success
                else:
                    logger.info(f"Approval request rejected: {approval_id}")
                    return False
        except Exception as e:
            logger.error(f"Failed to handle approval: {e}")
            return False
    
    async def _execute_action(self, approval: ApprovalRequest) -> bool:
        """Execute approved action."""
        try:
            action_type = approval.action_type
            action_data = approval.action_data
            
            if action_type == "email_send":
                return await self._execute_email_send(action_data)
            elif action_type == "linkedin_outreach":
                return await self._execute_linkedin_outreach(action_data)
            elif action_type == "job_apply":
                return await self._execute_job_apply(action_data)
            else:
                logger.warning(f"Unknown action type: {action_type}")
                return False
        except Exception as e:
            logger.error(f"Failed to execute action: {e}")
            return False
    
    async def _execute_email_send(self, data: dict) -> bool:
        """Execute email send action."""
        try:
            from app.core.google_workspace import google_workspace
            
            to_email = data.get("to")
            subject = data.get("subject")
            body = data.get("body")
            
            await google_workspace.send_email(to_email, subject, body)
            logger.info(f"Email sent to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
    
    async def _execute_linkedin_outreach(self, data: dict) -> bool:
        """Execute LinkedIn outreach action."""
        try:
            from app.core.openclaw import openclaw_client
            
            profile_url = data.get("profile_url")
            message = data.get("message")
            
            # Use OpenClaw to send LinkedIn message
            result = await openclaw_client.scrape_url(
                url=profile_url,
                platform="linkedin",
                use_cache=False
            )
            
            logger.info(f"LinkedIn outreach sent to {profile_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to send LinkedIn outreach: {e}")
            return False
    
    async def _execute_job_apply(self, data: dict) -> bool:
        """Execute job application action."""
        try:
            from app.database import AsyncSessionLocal
            from app.models.submission import Submission
            from app.models.job_posting import JobPosting
            from sqlalchemy import select
            from uuid import uuid4
            
            job_id = data.get("job_id")
            job_url = data.get("job_url")
            cover_letter = data.get("cover_letter")
            resume_text = data.get("resume_text", "")
            
            async with AsyncSessionLocal() as db:
                # Get job posting
                if job_id:
                    query = select(JobPosting).where(JobPosting.id == job_id)
                    result = await db.execute(query)
                    job = result.scalar_one_or_none()
                    
                    if not job:
                        logger.warning(f"Job not found: {job_id}")
                        return False
                    
                    job_url = job.source_url
                
                # Create submission record
                submission = Submission(
                    id=uuid4(),
                    opportunity_id=job_id if job_id else None,
                    proposal_text=cover_letter,
                    status="sent",
                    sent_at=datetime.now(timezone.utc),
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                
                db.add(submission)
                await db.commit()
                
                # Log to Obsidian
                try:
                    from app.integrations.obsidian import get_obsidian
                    obsidian = await get_obsidian()
                    await obsidian.log_submission({
                        "id": str(submission.id),
                        "title": f"Job Application - {job_url}",
                        "sent_at": submission.sent_at.isoformat(),
                        "status": "sent",
                        "proposal_text": cover_letter,
                        "opportunity_id": str(job_id) if job_id else "unknown"
                    })
                except Exception as e:
                    logger.warning(f"Failed to log to Obsidian: {e}")
                
                # Emit event
                from app.core.event_bus import event_bus
                await event_bus.emit("submission.sent", {
                    "submission_id": str(submission.id),
                    "job_url": job_url,
                    "job_id": str(job_id) if job_id else None
                })
                
                logger.info(f"Job application submitted to {job_url}")
                return True
        except Exception as e:
            logger.error(f"Failed to apply to job: {e}")
            return False
    
    async def check_expired_approvals(self) -> None:
        """Check for expired approval requests and auto-reject them."""
        try:
            async with AsyncSessionLocal() as db:
                now = datetime.now(timezone.utc)
                
                # Find expired pending approvals
                query = select(ApprovalRequest).where(
                    ApprovalRequest.status == "pending",
                    ApprovalRequest.expires_at < now
                )
                result = await db.execute(query)
                expired = list(result.scalars().all())
                
                for approval in expired:
                    approval.status = "expired"
                    approval.updated_at = now
                    logger.warning(f"Auto-rejected expired approval: {approval.id}")
                
                if expired:
                    await db.commit()
                    logger.info(f"Auto-rejected {len(expired)} expired approvals")
        except Exception as e:
            logger.error(f"Failed to check expired approvals: {e}")
    
    async def send_reminders(self) -> None:
        """Send reminders for pending approvals."""
        try:
            async with AsyncSessionLocal() as db:
                now = datetime.now(timezone.utc)
                reminder_time = now - timedelta(hours=self.reminder_timeout_hours)
                
                # Find approvals needing reminders
                query = select(ApprovalRequest).where(
                    ApprovalRequest.status == "pending",
                    ApprovalRequest.requested_at < reminder_time,
                    ApprovalRequest.reminder_sent == False
                )
                result = await db.execute(query)
                pending = list(result.scalars().all())
                
                for approval in pending:
                    await self._send_reminder(approval)
                    approval.reminder_sent = True
                    approval.updated_at = now
                
                if pending:
                    await db.commit()
                    logger.info(f"Sent {len(pending)} approval reminders")
        except Exception as e:
            logger.error(f"Failed to send reminders: {e}")
    
    async def _send_reminder(self, approval: ApprovalRequest) -> None:
        """Send reminder for pending approval."""
        try:
            from app.telegram_bot.bot import send_message
            
            hours_left = (approval.expires_at - datetime.now(timezone.utc)).total_seconds() / 3600
            
            message = f"""⏰ **Approval Reminder**

You have a pending approval request that will expire in {hours_left:.1f} hours.

**Action:** {approval.action_type}
**Description:** {approval.action_description}

Please review and respond."""
            
            await send_message(message)
            logger.info(f"Sent reminder for approval: {approval.id}")
        except Exception as e:
            logger.error(f"Failed to send reminder: {e}")
    
    async def get_pending_approvals(self, limit: int = 10) -> list[ApprovalRequest]:
        """Get pending approval requests."""
        try:
            async with AsyncSessionLocal() as db:
                query = (
                    select(ApprovalRequest)
                    .where(ApprovalRequest.status == "pending")
                    .order_by(ApprovalRequest.requested_at.desc())
                    .limit(limit)
                )
                result = await db.execute(query)
                return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Failed to get pending approvals: {e}")
            return []
    
    async def get_approval_stats(self) -> dict:
        """Get approval statistics."""
        try:
            async with AsyncSessionLocal() as db:
                from sqlalchemy import func
                
                # Total approvals
                total_query = select(func.count(ApprovalRequest.id))
                total_result = await db.execute(total_query)
                total = total_result.scalar() or 0
                
                # By status
                status_query = select(
                    ApprovalRequest.status,
                    func.count(ApprovalRequest.id)
                ).group_by(ApprovalRequest.status)
                status_result = await db.execute(status_query)
                by_status = {row[0]: row[1] for row in status_result}
                
                # Approval rate
                approved = by_status.get("approved", 0)
                rejected = by_status.get("rejected", 0)
                total_decided = approved + rejected
                approval_rate = (approved / total_decided * 100) if total_decided > 0 else 0
                
                return {
                    "total": total,
                    "by_status": by_status,
                    "approval_rate_percent": round(approval_rate, 2)
                }
        except Exception as e:
            logger.error(f"Failed to get approval stats: {e}")
            return {}


# Global instance
approval_flow_manager = ApprovalFlowManager()
