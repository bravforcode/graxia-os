"""
Email Manager Agent

Manages email inbox: fetches, categorizes, extracts action items,
and generates auto-reply drafts.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from app.agents.base import BaseAgent
from app.core.google_workspace import google_workspace
from app.core.tracking import verify_token
from app.database import AsyncSessionLocal
from app.models.email_thread import EmailThread
from app.models.email_message import EmailMessage
from app.models.assistant_task import AssistantTask
from app.services.audit_service import log_audit_event
from sqlalchemy import select

logger = logging.getLogger(__name__)


class EmailManagerAgent(BaseAgent):
    """
    Email Manager Agent - intelligent email management.
    
    Features:
    - Gmail integration (fetch, parse)
    - Email categorization (urgent, important, normal, spam, newsletter)
    - Action item extraction (NER)
    - Auto-reply draft generation
    - Email threading
    - Priority scoring
    
    Categories:
    - urgent: Requires immediate action
    - important: High-value emails (jobs, networking, clients)
    - normal: Regular emails
    - spam: Promotional/spam
    - newsletter: Newsletters and updates
    """
    
    name = "email_manager"
    
    async def fetch_and_process(
        self,
        max_emails: int = 50,
        query: str = "is:unread"
    ) -> dict:
        """
        Fetch and process emails from Gmail.
        
        Args:
            max_emails: Maximum emails to fetch
            query: Gmail search query
        
        Returns:
            dict with processed, categorized, action_items counts
        """
        logger.info(f"EmailManager: fetching emails with query='{query}'")
        
        processed = 0
        categorized = {"urgent": 0, "important": 0, "normal": 0, "spam": 0, "newsletter": 0}
        action_items_created = 0
        
        try:
            # Fetch emails from Gmail
            messages = await google_workspace.list_messages(
                max_results=max_emails,
                query=query
            )
            
            for msg_data in messages:
                try:
                    # Get full message
                    full_msg = await google_workspace.get_message(msg_data["id"])
                    
                    # Process email
                    thread = await self._process_email(full_msg)
                    if thread:
                        processed += 1
                        categorized[thread.category] = categorized.get(thread.category, 0) + 1
                        
                        # Extract action items
                        actions = await self._extract_action_items(thread)
                        action_items_created += len(actions)
                        
                        # Emit event
                        await self.bus.emit("email.received", {
                            "thread_id": str(thread.id),
                            "subject": thread.subject,
                            "category": thread.category,
                            "priority": thread.priority,
                            "action_items": len(actions)
                        })
                except Exception as e:
                    logger.error(f"Failed to process email {msg_data.get('id')}: {e}")
                    continue
        except Exception as e:
            logger.error(f"EmailManager: fetch failed: {e}")
        
        result = {
            "processed": processed,
            "categorized": categorized,
            "action_items_created": action_items_created
        }
        
        await self.log_audit(
            action="email_manager.fetch_and_process",
            details=result,
            success=True
        )
        
        return result
    
    async def _process_email(self, msg_data: dict) -> Optional[EmailThread]:
        """Process single email message."""
        try:
            # Extract email data
            headers = {h["name"]: h["value"] for h in msg_data.get("payload", {}).get("headers", [])}
            
            thread_id = msg_data.get("threadId")
            subject = headers.get("Subject", "(No Subject)")
            from_email = headers.get("From", "")
            to_email = headers.get("To", "")
            date_str = headers.get("Date", "")
            
            # Get or create thread
            thread = await self._get_or_create_thread(thread_id, subject)
            
            # Parse email body
            body = self._extract_body(msg_data.get("payload", {}))

            try:
                token = headers.get("X-Outreach-Token") or ""
                if not token and "<!--" in (body or ""):
                    marker = "<!--OUTREACH:"
                    if marker in body:
                        token = body.split(marker, 1)[1].split("-->", 1)[0].strip()
                payload = verify_token(token) if token else None
                if payload and payload.get("contact_id"):
                    await log_audit_event(
                        db=None,
                        action="outreach.reply",
                        event_type="email",
                        event_category="outreach",
                        severity="INFO",
                        outcome="success",
                        metadata={"payload": payload, "from": from_email, "subject": subject},
                        entity_type="contact",
                        entity_id=str(payload.get("contact_id")),
                    )
            except Exception:
                pass
            
            # Categorize email
            category = await self._categorize_email(subject, body, from_email)
            
            # Calculate priority
            priority = self._calculate_priority(category, subject, body)
            
            # Update thread
            async with AsyncSessionLocal() as db:
                query = select(EmailThread).where(EmailThread.thread_id == thread_id)
                result = await db.execute(query)
                thread_obj = result.scalar_one_or_none()
                
                if thread_obj:
                    thread_obj.category = category
                    thread_obj.priority = priority
                    thread_obj.last_message_at = datetime.now(timezone.utc)
                    thread_obj.unread_count = thread_obj.unread_count + 1
                    thread_obj.updated_at = datetime.now(timezone.utc)
                    
                    # Add participant if not exists
                    participants = thread_obj.participants or []
                    from_addr = self._extract_email_address(from_email)
                    if from_addr and not any(p.get("email") == from_addr for p in participants):
                        participants.append({
                            "email": from_addr,
                            "name": self._extract_name(from_email)
                        })
                        thread_obj.participants = participants
                    
                    await db.commit()
                    await db.refresh(thread_obj)
                    
                    # Save message
                    await self._save_message(thread_obj.id, msg_data, body)
                    
                    return thread_obj
        except Exception as e:
            logger.error(f"Email processing failed: {e}")
        
        return None
    
    async def _get_or_create_thread(self, thread_id: str, subject: str) -> EmailThread:
        """Get existing thread or create new one."""
        async with AsyncSessionLocal() as db:
            query = select(EmailThread).where(EmailThread.thread_id == thread_id)
            result = await db.execute(query)
            thread = result.scalar_one_or_none()
            
            if not thread:
                thread = EmailThread(
                    id=uuid4(),
                    thread_id=thread_id,
                    subject=subject,
                    participants=[],
                    category="normal",
                    priority=5,
                    unread_count=0,
                    has_attachments=False,
                    action_items=[],
                    status="unread",
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                db.add(thread)
                await db.commit()
                await db.refresh(thread)
            
            return thread
    
    def _extract_body(self, payload: dict) -> str:
        """Extract email body from payload."""
        try:
            if "parts" in payload:
                for part in payload["parts"]:
                    if part.get("mimeType") == "text/plain":
                        import base64
                        data = part.get("body", {}).get("data", "")
                        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            elif "body" in payload:
                import base64
                data = payload["body"].get("data", "")
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        except Exception as e:
            logger.warning(f"Body extraction failed: {e}")
        
        return ""
    
    async def _categorize_email(self, subject: str, body: str, from_email: str) -> str:
        """
        Categorize email using AI.
        
        Categories: urgent, important, normal, spam, newsletter
        """
        try:
            # Quick heuristics first
            subject_lower = subject.lower()
            body_lower = body[:500].lower()
            
            # Spam/newsletter patterns
            spam_keywords = ["unsubscribe", "click here", "limited time", "act now", "free"]
            if any(kw in subject_lower or kw in body_lower for kw in spam_keywords):
                return "newsletter"
            
            # Urgent patterns
            urgent_keywords = ["urgent", "asap", "immediate", "deadline", "emergency"]
            if any(kw in subject_lower for kw in urgent_keywords):
                return "urgent"
            
            # Important patterns (jobs, clients, networking)
            important_keywords = ["interview", "offer", "proposal", "contract", "meeting", "opportunity"]
            if any(kw in subject_lower or kw in body_lower for kw in important_keywords):
                return "important"
            
            # Use AI for ambiguous cases
            system = """Categorize emails into: urgent, important, normal, spam, newsletter.

urgent: Requires immediate action (deadlines, emergencies)
important: High-value (jobs, clients, networking, opportunities)
normal: Regular correspondence
spam: Promotional, marketing
newsletter: Newsletters, updates

Return JSON: {"category": "important", "reason": "Job interview invitation"}"""
            
            user = f"""Subject: {subject}
From: {from_email}
Body: {body[:300]}

Categorize this email."""
            
            result = await self.llm.complete_json(
                system=system,
                user=user,
                task_class="classification",
                complexity=2
            )
            
            return result.get("category", "normal")
        except Exception as e:
            logger.error(f"Email categorization failed: {e}")
            return "normal"
    
    def _calculate_priority(self, category: str, subject: str, body: str) -> int:
        """Calculate priority score (1-10)."""
        # Base priority by category
        priority_map = {
            "urgent": 9,
            "important": 7,
            "normal": 5,
            "newsletter": 3,
            "spam": 1
        }
        
        priority = priority_map.get(category, 5)
        
        # Adjust based on keywords
        high_priority_keywords = ["deadline", "today", "tomorrow", "interview", "offer"]
        if any(kw in subject.lower() for kw in high_priority_keywords):
            priority = min(10, priority + 1)
        
        return priority
    
    async def _extract_action_items(self, thread: EmailThread) -> list[AssistantTask]:
        """Extract action items from email thread."""
        tasks = []
        
        try:
            # Get latest message
            async with AsyncSessionLocal() as db:
                query = (
                    select(EmailMessage)
                    .where(EmailMessage.thread_id == thread.id)
                    .order_by(EmailMessage.received_at.desc())
                    .limit(1)
                )
                result = await db.execute(query)
                message = result.scalar_one_or_none()
                
                if not message:
                    return tasks
                
                # Extract action items using AI
                system = """Extract action items from emails. Look for:
- Explicit requests ("please send", "can you", "need you to")
- Deadlines and dates
- Questions requiring response
- Meeting requests

Return JSON: {"action_items": [{"task": "Send proposal", "due_date": "2024-01-20", "priority": 8}]}"""
                
                user = f"""Subject: {thread.subject}
Body: {message.body[:500]}

Extract action items."""
                
                result = await self.llm.complete_json(
                    system=system,
                    user=user,
                    task_class="extraction",
                    complexity=3
                )
                
                # Create tasks
                for item in result.get("action_items", []):
                    task = AssistantTask(
                        id=uuid4(),
                        title=item.get("task"),
                        description=f"From email: {thread.subject}",
                        task_type="email",
                        priority=item.get("priority", 5),
                        status="pending",
                        due_date=self._parse_date(item.get("due_date")),
                        related_entity_type="email_thread",
                        related_entity_id=thread.id,
                        assigned_to="user",
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc)
                    )
                    
                    db.add(task)
                    tasks.append(task)
                
                await db.commit()
                
                # Persist the extracted action items on the canonical thread row.
                thread_query = select(EmailThread).where(EmailThread.id == thread.id)
                thread_result = await db.execute(thread_query)
                thread_obj = thread_result.scalar_one_or_none()
                if thread_obj:
                    thread_obj.action_items = [
                    {"task": t.title, "priority": t.priority}
                    for t in tasks
                    ]
                    await db.commit()
        except Exception as e:
            logger.error(f"Action item extraction failed: {e}")
        
        return tasks
    
    async def _save_message(self, thread_id: uuid4, msg_data: dict, body: str) -> None:
        """Save email message to database."""
        try:
            headers = {h["name"]: h["value"] for h in msg_data.get("payload", {}).get("headers", [])}
            
            async with AsyncSessionLocal() as db:
                message = EmailMessage(
                    id=uuid4(),
                    thread_id=thread_id,
                    message_id=msg_data.get("id"),
                    from_email=headers.get("From", ""),
                    to_email=headers.get("To", ""),
                    subject=headers.get("Subject", ""),
                    body=body,
                    received_at=datetime.now(timezone.utc),
                    is_read=False,
                    created_at=datetime.now(timezone.utc)
                )
                
                db.add(message)
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to save message: {e}")
    
    def _extract_email_address(self, email_str: str) -> Optional[str]:
        """Extract email address from 'Name <email@example.com>' format."""
        match = re.search(r'<(.+?)>', email_str)
        if match:
            return match.group(1)
        return email_str if "@" in email_str else None
    
    def _extract_name(self, email_str: str) -> Optional[str]:
        """Extract name from 'Name <email@example.com>' format."""
        match = re.match(r'(.+?)\s*<', email_str)
        if match:
            return match.group(1).strip('"')
        return None
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse date string to datetime."""
        if not date_str:
            return None
        
        try:
            from dateutil import parser
            return parser.parse(date_str)
        except Exception:
            return None


# Global instance
email_manager_agent = EmailManagerAgent()
