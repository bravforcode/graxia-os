"""
Revenue OS Email Service
Email queue management with retry logic and Resend integration
"""
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta
import asyncio
import structlog

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import OperationalError, TimeoutError as SQLTimeoutError

from ..models import EmailOutbox, Order, Customer, Approval, DeliveryEvent
from ..enums import EmailStatus, ApprovalStatus, DeliveryStatus
from ..constants import MAX_EMAIL_ATTEMPTS
from ..core.db_ops import atomic_operation
from ..core.validators import (
    validate_email,
    validate_string_length,
    sanitize_html,
    ValidationError,
)

logger = structlog.get_logger()


# Exponential backoff configuration
RETRY_BASE_DELAY = 2  # seconds
RETRY_MAX_DELAY = 300  # 5 minutes
RETRY_MULTIPLIER = 2


class EmailService:
    """
    Email queue management service with retry logic.
    Integrates with Resend API for actual email delivery.
    """
    
    @staticmethod
    async def queue_email(
        db: AsyncSession,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        text_body: Optional[str] = None,
        from_email: Optional[str] = None,
        reply_to: Optional[str] = None,
        order_id: Optional[UUID] = None,
        customer_id: Optional[UUID] = None,
        approval_id: Optional[UUID] = None,
        email_key: Optional[str] = None,
        scheduled_at: Optional[datetime] = None,
        to_name: Optional[str] = None,
    ) -> EmailOutbox:
        """
        Queue an email for delivery.
        
        Args:
            db: Database session
            to_email: Recipient email
            subject: Email subject
            body: Email body (used if html_body/text_body not provided)
            html_body: HTML version of email
            text_body: Plain text version
            from_email: Sender email
            reply_to: Reply-to email
            order_id: Optional order reference
            customer_id: Optional customer reference
            approval_id: Optional approval reference (blocks sending until approved)
            email_key: Optional unique key for idempotency
            scheduled_at: Optional scheduled send time
            to_name: Optional recipient name
        
        Returns:
            EmailOutbox: Queued email record
        
        Raises:
            ValidationError: If input validation fails
        """
        # Validate inputs
        try:
            validate_email(to_email)
            validate_string_length(subject, "subject", max_length=255)
            validate_string_length(body, "body", max_length=100000)
            
            if from_email:
                validate_email(from_email)
            if reply_to:
                validate_email(reply_to)
            if to_name:
                validate_string_length(to_name, "to_name", max_length=255)
            if email_key:
                validate_string_length(email_key, "email_key", max_length=255)
            
            # Sanitize HTML to prevent XSS
            if html_body:
                html_body = sanitize_html(html_body)
            else:
                html_body = sanitize_html(body)
                
        except ValidationError as e:
            logger.error(
                "email_validation_failed",
                error=str(e),
                to_email=to_email,
            )
            raise
        
        async with atomic_operation(db):
            # Check for duplicate email_key
            if email_key:
                result = await db.execute(
                    select(EmailOutbox).where(EmailOutbox.email_key == email_key)
                )
                existing = result.scalar_one_or_none()
                if existing:
                    logger.info(
                        "email_already_queued",
                        email_key=email_key,
                        email_id=str(existing.id),
                    )
                    return existing
            
            email = EmailOutbox(
                to_email=to_email,
                to_name=to_name,
                subject=subject,
                body=body,
                html_body=html_body,
                text_body=text_body or body,
                from_email=from_email,
                reply_to=reply_to,
                order_id=order_id,
                customer_id=customer_id,
                approval_id=approval_id,
                email_key=email_key,
                scheduled_at=scheduled_at,
                status=EmailStatus.PENDING,
            )
            db.add(email)
            await db.flush()
            
            logger.info(
                "email_queued",
                email_id=str(email.id),
                to_email=to_email,
                subject=subject,
                has_approval=approval_id is not None,
            )
            
            return email
    
    @staticmethod
    def _calculate_retry_delay(attempt: int) -> int:
        """
        Calculate exponential backoff delay for retry.
        
        Args:
            attempt: Current attempt number (0-indexed)
        
        Returns:
            int: Delay in seconds
        """
        delay = RETRY_BASE_DELAY * (RETRY_MULTIPLIER ** attempt)
        return min(delay, RETRY_MAX_DELAY)
    
    @staticmethod
    async def send_email(
        db: AsyncSession,
        email_id: UUID,
        resend_client,
    ) -> bool:
        """
        Send a queued email via Resend API.
        
        Args:
            db: Database session
            email_id: Email ID to send
            resend_client: Resend API client
        
        Returns:
            bool: True if sent successfully, False otherwise
        """
        result = await db.execute(
            select(EmailOutbox).where(EmailOutbox.id == email_id)
        )
        email = result.scalar_one_or_none()
        
        if not email:
            logger.error("email_not_found", email_id=str(email_id))
            return False
        
        # Check if email requires approval
        if email.approval_id:
            approval_result = await db.execute(
                select(Approval).where(Approval.id == email.approval_id)
            )
            approval = approval_result.scalar_one_or_none()
            
            if not approval or approval.status != ApprovalStatus.APPROVED:
                logger.info(
                    "email_blocked_pending_approval",
                    email_id=str(email_id),
                    approval_status=approval.status.value if approval else "not_found",
                )
                return False
        
        # Check if already sent
        if email.status == EmailStatus.SENT:
            logger.info("email_already_sent", email_id=str(email_id))
            return True
        
        # Check retry limit
        if email.attempts >= MAX_EMAIL_ATTEMPTS:
            email.status = EmailStatus.FAILED
            await db.commit()
            logger.error(
                "email_max_attempts_exceeded",
                email_id=str(email_id),
                attempts=email.attempts,
            )
            return False
        
        try:
            # Update status to sending
            email.status = EmailStatus.SENDING
            email.attempts += 1
            await db.commit()
            
            # Calculate retry delay for rate limiting
            if email.attempts > 1:
                retry_delay = EmailService._calculate_retry_delay(email.attempts - 1)
                logger.info(
                    "email_retry_with_backoff",
                    email_id=str(email_id),
                    attempt=email.attempts,
                    delay_seconds=retry_delay,
                )
                await asyncio.sleep(retry_delay)
            
            # Send via Resend with timeout
            try:
                response = await asyncio.wait_for(
                    resend_client.emails.send({
                        "from": email.from_email or "noreply@graxia.ai",
                        "to": [email.to_email],
                        "subject": email.subject,
                        "html": email.html_body,
                        "text": email.text_body,
                        "reply_to": email.reply_to,
                    }),
                    timeout=30.0,  # 30 second timeout
                )
            except asyncio.TimeoutError:
                raise Exception("Resend API timeout after 30 seconds")
            except Exception as api_error:
                # Check for rate limit error
                error_msg = str(api_error).lower()
                if "rate limit" in error_msg or "429" in error_msg:
                    logger.warning(
                        "resend_rate_limit",
                        email_id=str(email_id),
                        attempt=email.attempts,
                    )
                    raise Exception("Resend API rate limit exceeded") from api_error
                raise
            
            # Update status to sent
            email.status = EmailStatus.SENT
            email.sent_at = datetime.utcnow()
            email.resend_message_id = response.get("id")
            await db.commit()
            
            logger.info(
                "email_sent",
                email_id=str(email_id),
                to_email=email.to_email,
                resend_id=email.resend_message_id,
                attempts=email.attempts,
            )
            
            return True
            
        except (OperationalError, SQLTimeoutError) as e:
            # Database error
            await db.rollback()
            logger.error(
                "email_database_error",
                email_id=str(email_id),
                error=str(e),
                error_type=type(e).__name__,
            )
            return False
            
        except Exception as e:
            # Update error status
            email.status = EmailStatus.PENDING  # Back to pending for retry
            email.last_error = str(e)
            await db.commit()
            
            logger.error(
                "email_send_failed",
                email_id=str(email_id),
                error=str(e),
                attempts=email.attempts,
            )
            
            return False
    
    @staticmethod
    async def get_pending_emails(
        db: AsyncSession,
        limit: int = 50,
    ) -> list[EmailOutbox]:
        """
        Get pending emails ready to send.
        
        Args:
            db: Database session
            limit: Maximum number of emails to return
        
        Returns:
            list[EmailOutbox]: List of pending emails
        """
        now = datetime.utcnow()
        
        # Get emails that are:
        # 1. Status = PENDING
        # 2. Either no approval_id OR approval is APPROVED
        # 3. Either no scheduled_at OR scheduled_at <= now
        # 4. attempts < MAX_EMAIL_ATTEMPTS
        
        result = await db.execute(
            select(EmailOutbox)
            .where(
                and_(
                    EmailOutbox.status == EmailStatus.PENDING,
                    EmailOutbox.attempts < MAX_EMAIL_ATTEMPTS,
                    (EmailOutbox.scheduled_at.is_(None)) | (EmailOutbox.scheduled_at <= now),
                )
            )
            .limit(limit)
        )
        
        emails = result.scalars().all()
        
        # Filter by approval status
        approved_emails = []
        for email in emails:
            if email.approval_id:
                approval_result = await db.execute(
                    select(Approval).where(Approval.id == email.approval_id)
                )
                approval = approval_result.scalar_one_or_none()
                if approval and approval.status == ApprovalStatus.APPROVED:
                    approved_emails.append(email)
            else:
                approved_emails.append(email)
        
        return approved_emails
    
    @staticmethod
    async def retry_failed_emails(
        db: AsyncSession,
        resend_client,
        max_retries: int = 10,
    ) -> int:
        """
        Retry failed emails that haven't exceeded max attempts.
        
        Args:
            db: Database session
            resend_client: Resend API client
            max_retries: Maximum number of emails to retry
        
        Returns:
            int: Number of emails successfully retried
        """
        result = await db.execute(
            select(EmailOutbox)
            .where(
                and_(
                    EmailOutbox.status == EmailStatus.PENDING,
                    EmailOutbox.attempts > 0,
                    EmailOutbox.attempts < MAX_EMAIL_ATTEMPTS,
                )
            )
            .limit(max_retries)
        )
        
        failed_emails = result.scalars().all()
        success_count = 0
        
        for email in failed_emails:
            if await EmailService.send_email(db, email.id, resend_client):
                success_count += 1
        
        logger.info(
            "failed_emails_retried",
            total=len(failed_emails),
            succeeded=success_count,
        )
        
        return success_count
    
    @staticmethod
    async def cancel_email(
        db: AsyncSession,
        email_id: UUID,
    ) -> bool:
        """
        Cancel a queued email.
        
        Args:
            db: Database session
            email_id: Email ID to cancel
        
        Returns:
            bool: True if cancelled, False if already sent
        """
        result = await db.execute(
            select(EmailOutbox).where(EmailOutbox.id == email_id)
        )
        email = result.scalar_one_or_none()
        
        if not email:
            return False
        
        if email.status == EmailStatus.SENT:
            logger.warning("cannot_cancel_sent_email", email_id=str(email_id))
            return False
        
        email.status = EmailStatus.CANCELLED
        await db.commit()
        
        logger.info("email_cancelled", email_id=str(email_id))
        return True
    
    @staticmethod
    async def queue_delivery_email(
        db: AsyncSession,
        order_id: UUID,
        product_name: str,
        fulfillment_url: Optional[str] = None,
        fulfillment_instructions: Optional[str] = None,
    ) -> EmailOutbox:
        """
        Queue a product delivery email for an order.
        
        Args:
            db: Database session
            order_id: Order ID
            product_name: Product name
            fulfillment_url: Optional fulfillment URL
            fulfillment_instructions: Optional instructions
        
        Returns:
            EmailOutbox: Queued delivery email
        """
        # Get order details
        order_result = await db.execute(
            select(Order).where(Order.id == order_id)
        )
        order = order_result.scalar_one_or_none()
        
        if not order:
            raise ValueError(f"Order {order_id} not found")
        
        # Generate email key for idempotency
        email_key = f"delivery:{order_id}"
        
        # Build email content
        subject = f"Your {product_name} is ready!"
        
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <h2>Thank you for your purchase!</h2>
    <p>Hi {order.customer_name or 'there'},</p>
    <p>Your order for <strong>{product_name}</strong> is ready.</p>
"""
        
        if fulfillment_url:
            html_body += f"""
    <p style="margin: 30px 0;">
        <a href="{fulfillment_url}" style="background-color: #4CAF50; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; display: inline-block;">
            Access Your Product
        </a>
    </p>
"""
        
        if fulfillment_instructions:
            html_body += f"""
    <div style="background-color: #f5f5f5; padding: 15px; border-radius: 4px; margin: 20px 0;">
        <h3 style="margin-top: 0;">Instructions:</h3>
        <p>{fulfillment_instructions}</p>
    </div>
"""
        
        html_body += """
    <p>If you have any questions, please reply to this email.</p>
    <p>Best regards,<br>Graxia Team</p>
</body>
</html>
"""
        
        text_body = f"""
Thank you for your purchase!

Hi {order.customer_name or 'there'},

Your order for {product_name} is ready.

{f'Access your product: {fulfillment_url}' if fulfillment_url else ''}

{f'Instructions: {fulfillment_instructions}' if fulfillment_instructions else ''}

If you have any questions, please reply to this email.

Best regards,
Graxia Team
"""
        
        return await EmailService.queue_email(
            db=db,
            to_email=order.customer_email,
            to_name=order.customer_name,
            subject=subject,
            body=text_body,
            html_body=html_body,
            text_body=text_body,
            order_id=order_id,
            customer_id=order.customer_id,
            email_key=email_key,
        )
