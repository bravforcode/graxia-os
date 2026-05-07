"""
Email Business Agent - Automated Email Management
"""

from datetime import datetime
from typing import Any

from structlog import get_logger

from app.core.tool_permission_policy import (
    ApprovalRequiredError,
    ToolExecutionRequest,
    ToolPermissionPolicy,
)

from .base_business_agent import BaseBusinessAgent

logger = get_logger(__name__)


class EmailAgent(BaseBusinessAgent):
    """
    Email management agent that handles:
    - Inbox monitoring and categorization
    - Auto-reply to common queries
    - Draft composition
    - Email scheduling
    - Priority flagging
    - Follow-up reminders
    """

    # Required attributes for BaseSocialAgent
    name = "email_agent"
    agent_name = "Email Agent"
    platform = "email"

    def __init__(self):
        # Call BaseSocialAgent directly with correct signature
        from app.agents.social.base_social_agent import BaseSocialAgent
        from app.core.agent_identity import AgentCapability

        BaseSocialAgent.__init__(
            self,
            agent_name="Email Agent",
            platform="email",
            bio="Professional email assistant that manages inbox, drafts responses, and schedules communications",
            capabilities=[
                AgentCapability(name="send_email", description="Send emails", skill_level=8),
                AgentCapability(
                    name="read_email", description="Read and categorize emails", skill_level=8
                ),
            ],
        )
        # Initialize BaseBusinessAgent attributes
        self.operation_log: list[dict] = []
        self.pending_approvals: list[dict] = []

        self.connected_email: str | None = None
        self.inbox_categories = {
            "urgent": [],
            "important": [],
            "normal": [],
            "newsletter": [],
            "spam": [],
        }
        self.drafts: list[dict] = []
        self.scheduled_emails: list[dict] = []

    async def connect_email(self, email_address: str, credentials: dict[str, str]) -> bool:
        """Connect to email account (Gmail, Outlook, etc.)"""
        try:
            # Store credentials securely
            from app.core.agent_identity import PlatformType, identity_manager

            if self.identity:
                await identity_manager.add_account(
                    agent_id=self.identity.agent_id,
                    platform=PlatformType.EMAIL,
                    account_id=email_address,
                    credentials=credentials,
                )

            self.connected_email = email_address
            self.enabled = True

            await self.log_operation(
                "email_connected",
                {"email": email_address, "provider": credentials.get("provider", "unknown")},
            )

            logger.info(f"Email connected: {email_address}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect email: {e}")
            return False

    async def fetch_emails(self, folder: str = "inbox", limit: int = 50) -> list[dict]:
        """Fetch emails from connected account (Database)"""
        from sqlalchemy import desc, select

        from app.database import AsyncSessionLocal
        from app.models.email_thread import EmailThread

        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(EmailThread).order_by(desc(EmailThread.created_at)).limit(limit)
                )
                threads = list(result.scalars().all())

            real_emails = []
            for t in threads:
                # Fallback safely if participants list is empty or malformed
                sender = "unknown"
                if t.participants and isinstance(t.participants, list) and len(t.participants) > 0:
                    first_p = t.participants[0]
                    if isinstance(first_p, dict):
                        sender = first_p.get("email", "unknown")
                
                real_emails.append({
                    "id": str(t.id),
                    "from": sender,
                    "subject": t.subject or "No Subject",
                    "body": "Content available in message view",
                    "received_at": t.created_at.isoformat() if t.created_at else datetime.now().isoformat(),
                    "read": getattr(t, 'unread_count', 0) == 0,
                    "priority": "high" if getattr(t, 'priority', 0) > 0 else "normal",
                })

            await self.log_operation("fetch_emails", {"folder": folder, "count": len(real_emails)})
            return real_emails
        except Exception as e:
            logger.error(f"Failed to fetch emails from database: {e}")
            return []

    async def categorize_email(self, email: dict[str, Any]) -> str:
        """AI-powered email categorization"""
        content = f"{email.get('subject', '')} {email.get('body', '')}"

        # Simple keyword-based categorization (would use AI in production)
        urgent_keywords = ["urgent", "asap", "immediately", "emergency", "deadline today"]
        important_keywords = ["important", "action required", "meeting", "proposal"]
        newsletter_keywords = ["newsletter", "update", "digest", "weekly", "monthly"]

        content_lower = content.lower()

        if any(kw in content_lower for kw in urgent_keywords):
            return "urgent"
        elif any(kw in content_lower for kw in important_keywords):
            return "important"
        elif any(kw in content_lower for kw in newsletter_keywords):
            return "newsletter"
        else:
            return "normal"

    async def draft_reply(self, email: dict[str, Any], tone: str = "professional") -> str:
        """Draft AI-powered reply to email"""
        # In production, this would call LLM
        subject = email.get("subject", "")

        draft = f"""Dear {email.get("from", "Sir/Madam")},

Thank you for your email regarding "{subject}".

[AI-generated response based on content analysis]

Best regards,
{self.name}
"""

        draft_entry = {
            "id": f"draft_{datetime.now().timestamp()}",
            "original_email": email,
            "draft_content": draft,
            "tone": tone,
            "created_at": datetime.now().isoformat(),
            "status": "draft",
        }

        self.drafts.append(draft_entry)

        await self.log_operation("draft_created", {"email_id": email.get("id"), "tone": tone})

        return draft

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: list[str] | None = None,
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Send email (REQUIRES server-side approval for all sends).

        CRITICAL: This tool requires valid approval_id. Call request_approval() first.
        """
        email_data = {
            "to": to,
            "subject": subject,
            "body": body,
            "cc": cc or [],
            "from": self.connected_email or "agent@graxia.os",
        }

        # ENFORCE: Server-side approval via ToolPermissionPolicy
        policy = ToolPermissionPolicy()
        try:
            await policy.assert_can_execute(
                ToolExecutionRequest(
                    user_id=self.identity.agent_id if self.identity else "unknown",
                    agent_id=self.name or "email_agent",
                    tool_name="send_email",
                    payload=email_data,
                    approval_id=approval_id,
                )
            )
        except ApprovalRequiredError as e:
            logger.warning(
                "Email send blocked - approval required",
                to=to,
                subject=subject,
                error=str(e),
            )
            return {
                "status": "blocked",
                "error": "Approval required",
                "message": str(e),
            }

        # If no approval_id provided, queue for approval (legacy path)
        if not approval_id:
            approval_id = await self.request_approval(
                action="send_email", details=email_data, priority="normal"
            )
            return {
                "status": "pending_approval",
                "approval_id": approval_id,
                "message": "Email queued for approval",
            }

        # Actually send email (would integrate with email provider)
        await self.log_operation(
            "email_sent", {"to": to, "subject": subject, "approval_id": approval_id}
        )

        return {
            "status": "sent",
            "message_id": f"msg_{datetime.now().timestamp()}",
            "timestamp": datetime.now().isoformat(),
            "approval_id": approval_id,
        }

    async def schedule_email(self, to: str, subject: str, body: str, send_at: datetime) -> str:
        """Schedule email for later sending"""
        schedule_id = f"scheduled_{datetime.now().timestamp()}"

        scheduled = {
            "id": schedule_id,
            "to": to,
            "subject": subject,
            "body": body,
            "send_at": send_at.isoformat(),
            "status": "scheduled",
        }

        self.scheduled_emails.append(scheduled)

        await self.log_operation(
            "email_scheduled", {"to": to, "subject": subject, "send_at": send_at.isoformat()}
        )

        return schedule_id

    async def process_operation(self, operation: dict[str, Any]) -> dict[str, Any]:
        """Process email operation"""
        op_type = operation.get("type")

        if op_type == "send":
            return await self.send_email(
                to=operation["to"],
                subject=operation["subject"],
                body=operation["body"],
                approval_id=operation.get("approval_id"),
            )
        elif op_type == "draft":
            draft = await self.draft_reply(
                operation["email"], operation.get("tone", "professional")
            )
            return {"status": "drafted", "draft": draft}
        elif op_type == "fetch":
            emails = await self.fetch_emails(operation.get("folder", "inbox"))
            return {"status": "fetched", "emails": emails}
        else:
            return {"status": "error", "message": f"Unknown operation: {op_type}"}

    async def get_stats(self) -> dict[str, Any]:
        """Get email agent statistics"""
        base_stats = await self.get_operation_stats()

        return {
            **base_stats,
            "connected_email": self.connected_email,
            "drafts_count": len(self.drafts),
            "scheduled_count": len(self.scheduled_emails),
            "pending_approvals": len(self.pending_approvals),
            "inbox_categories": {k: len(v) for k, v in self.inbox_categories.items()},
        }

    # Abstract method implementations (required by BaseSocialAgent)
    async def connect(self) -> bool:
        """Connect to email platform."""
        # Email agent uses connect_email() instead
        return True

    async def disconnect(self) -> bool:
        """Disconnect from email platform."""
        self.connected_email = None
        return True

    async def send_message(self, recipient_id: str, message: Any) -> bool:
        """Send message (social agent interface)."""
        # Delegate to send_email for consistency
        result = await self.send_email(
            to=recipient_id,
            subject=getattr(message, "subject", "No subject"),
            body=getattr(message, "content", str(message)),
        )
        return result.get("status") in ("sent", "pending_approval")


# Singleton instance
email_agent = EmailAgent()
