"""
Test Email Service
Verify email queue management and delivery
"""
import pytest
from uuid import uuid4
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..services.email_service import EmailService
from ..models import EmailOutbox, Product, Order
from ..enums import EmailStatus, ProductStatus


@pytest.mark.asyncio
async def test_queue_email(db_session: AsyncSession):
    """Test queuing an email."""
    email = await EmailService.queue_email(
        db=db_session,
        to_email="test@example.com",
        subject="Test Email",
        body="Test body",
        html_body="<p>Test body</p>",
    )
    
    assert email.id is not None
    assert email.to_email == "test@example.com"
    assert email.status == EmailStatus.PENDING
    assert email.attempts == 0


@pytest.mark.asyncio
async def test_queue_email_idempotency(db_session: AsyncSession):
    """Test that queuing same email twice returns same record."""
    email_key = "test_email_001"
    
    email1 = await EmailService.queue_email(
        db=db_session,
        to_email="test@example.com",
        subject="Test Email",
        body="Test body",
        email_key=email_key,
    )
    
    email2 = await EmailService.queue_email(
        db=db_session,
        to_email="test@example.com",
        subject="Test Email",
        body="Test body",
        email_key=email_key,
    )
    
    assert email1.id == email2.id


@pytest.mark.asyncio
async def test_send_email_success(db_session: AsyncSession, mock_resend_client):
    """Test successful email sending."""
    # Queue email
    email = await EmailService.queue_email(
        db=db_session,
        to_email="success@example.com",
        subject="Success Test",
        body="Test body",
    )
    
    # Send email
    success = await EmailService.send_email(
        db=db_session,
        email_id=email.id,
        resend_client=mock_resend_client,
    )
    
    assert success is True
    
    # Verify email status
    result = await db_session.execute(
        select(EmailOutbox).where(EmailOutbox.id == email.id)
    )
    sent_email = result.scalar_one()
    
    assert sent_email.status == EmailStatus.SENT
    assert sent_email.sent_at is not None
    assert sent_email.resend_message_id == "mock_resend_id_123"


@pytest.mark.asyncio
async def test_send_email_already_sent(db_session: AsyncSession, mock_resend_client):
    """Test that sending already-sent email returns True."""
    # Queue and send email
    email = await EmailService.queue_email(
        db=db_session,
        to_email="already@example.com",
        subject="Already Sent",
        body="Test body",
    )
    
    await EmailService.send_email(db_session, email.id, mock_resend_client)
    
    # Try sending again
    success = await EmailService.send_email(db_session, email.id, mock_resend_client)
    
    assert success is True


@pytest.mark.asyncio
async def test_get_pending_emails(db_session: AsyncSession):
    """Test getting pending emails."""
    # Queue multiple emails
    for i in range(5):
        await EmailService.queue_email(
            db=db_session,
            to_email=f"test{i}@example.com",
            subject=f"Test {i}",
            body="Test body",
        )
    
    # Get pending emails
    pending = await EmailService.get_pending_emails(db_session, limit=10)
    
    assert len(pending) == 5
    assert all(e.status == EmailStatus.PENDING for e in pending)


@pytest.mark.asyncio
async def test_get_pending_emails_excludes_scheduled(db_session: AsyncSession):
    """Test that scheduled emails are not returned until scheduled time."""
    # Queue email scheduled for future
    future_time = datetime.utcnow() + timedelta(hours=1)
    
    await EmailService.queue_email(
        db=db_session,
        to_email="future@example.com",
        subject="Future Email",
        body="Test body",
        scheduled_at=future_time,
    )
    
    # Get pending emails
    pending = await EmailService.get_pending_emails(db_session)
    
    assert len(pending) == 0


@pytest.mark.asyncio
async def test_cancel_email(db_session: AsyncSession):
    """Test cancelling a queued email."""
    # Queue email
    email = await EmailService.queue_email(
        db=db_session,
        to_email="cancel@example.com",
        subject="Cancel Test",
        body="Test body",
    )
    
    # Cancel email
    success = await EmailService.cancel_email(db_session, email.id)
    
    assert success is True
    
    # Verify status
    result = await db_session.execute(
        select(EmailOutbox).where(EmailOutbox.id == email.id)
    )
    cancelled_email = result.scalar_one()
    
    assert cancelled_email.status == EmailStatus.CANCELLED


@pytest.mark.asyncio
async def test_queue_delivery_email(db_session: AsyncSession):
    """Test queuing a product delivery email."""
    # Create product and order
    product = Product(
        name="Test Product",
        slug="test-product",
        price_cents=9900,
        status=ProductStatus.PUBLISHED,
        fulfillment_url="https://example.com/access",
        fulfillment_instructions="Click the link to access your product",
    )
    db_session.add(product)
    await db_session.flush()
    
    order = Order(
        platform="stripe",
        platform_order_id="delivery_test_001",
        customer_email="delivery@example.com",
        customer_name="Test Customer",
        product_id=product.id,
        amount_cents=9900,
    )
    db_session.add(order)
    await db_session.commit()
    
    # Queue delivery email
    email = await EmailService.queue_delivery_email(
        db=db_session,
        order_id=order.id,
        product_name=product.name,
        fulfillment_url=product.fulfillment_url,
        fulfillment_instructions=product.fulfillment_instructions,
    )
    
    assert email.to_email == "delivery@example.com"
    assert email.order_id == order.id
    assert "Test Product" in email.subject
    assert "https://example.com/access" in email.html_body


@pytest.mark.asyncio
async def test_retry_failed_emails(db_session: AsyncSession, mock_resend_client):
    """Test retrying failed emails."""
    # Queue email and mark as failed
    email = await EmailService.queue_email(
        db=db_session,
        to_email="retry@example.com",
        subject="Retry Test",
        body="Test body",
    )
    
    # Simulate failed attempt
    email.attempts = 1
    email.last_error = "Connection timeout"
    await db_session.commit()
    
    # Retry failed emails
    success_count = await EmailService.retry_failed_emails(
        db=db_session,
        resend_client=mock_resend_client,
        max_retries=10,
    )
    
    assert success_count == 1
