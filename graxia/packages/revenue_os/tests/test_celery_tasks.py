"""
Test Celery Tasks
Integration tests for automation tasks
"""
import pytest
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..celery.tasks.daily_revenue_ops import daily_revenue_ops_with_db
from ..celery.tasks.hourly_monitor import hourly_monitor_with_db
from ..celery.tasks.campaign_engine import campaign_engine_with_db
from ..celery.tasks.send_pending_emails import send_pending_emails_with_db
from ..celery.tasks.weekly_review import weekly_review_with_db
from ..celery.tasks.process_outbox import process_outbox_with_db
from ..models import Lead, Order, RevenueCampaign, EmailOutbox, Approval, OutboxEvent, StrategyLog
from ..enums import LeadStatus, CampaignStatus, EmailStatus, ApprovalStatus, ProductStatus
from ..services.campaign_service import RevenueCampaignService
from ..services.email_service import EmailService


@pytest.mark.asyncio
async def test_daily_revenue_ops_scores_leads(db_session: AsyncSession):
    """Test that daily revenue ops scores new leads."""
    # Create new leads
    for i in range(3):
        lead = Lead(
            email=f"lead{i}@example.com",
            source="organic_search",
            status=LeadStatus.NEW,
        )
        db_session.add(lead)

    await db_session.commit()

    # Run daily revenue ops
    result = await daily_revenue_ops_with_db(db_session)

    assert result["status"] == "completed"
    assert result["metrics"]["leads_scored"] == 3

    # Verify leads were scored
    scored = await db_session.execute(
        select(Lead).where(Lead.status == LeadStatus.NEW)
    )
    new_leads = scored.scalars().all()

    assert len(new_leads) == 3
    for lead in new_leads:
        assert lead.score is not None
        assert lead.score_rationale is not None


@pytest.mark.asyncio
async def test_hourly_monitor_detects_stale_orders(db_session: AsyncSession):
    """Test that hourly monitor detects stale pending orders."""
    # Create stale order (created 1 hour ago)
    stale_order = Order(
        platform="stripe",
        platform_order_id="stale_001",
        customer_email="stale@example.com",
        amount_cents=9900,
        status="pending",
        created_at=datetime.utcnow() - timedelta(hours=1),
    )
    db_session.add(stale_order)
    await db_session.commit()

    # Run hourly monitor
    result = await hourly_monitor_with_db(db_session)

    assert result["status"] == "completed"
    assert result["metrics"]["stale_orders"] == 1


@pytest.mark.asyncio
async def test_hourly_monitor_expires_approvals(db_session: AsyncSession):
    """Test that hourly monitor expires old approvals."""
    # Create expired approval
    expired_approval = Approval(
        object_type="email",
        object_id="00000000-0000-0000-0000-000000000001",
        title="Expired Approval",
        status=ApprovalStatus.PENDING,
        expires_at=datetime.utcnow() - timedelta(hours=1),
    )
    db_session.add(expired_approval)
    await db_session.commit()

    # Run hourly monitor
    result = await hourly_monitor_with_db(db_session)

    assert result["status"] == "completed"
    assert result["metrics"]["expired_approvals"] == 1

    # Verify approval was rejected
    approval_result = await db_session.execute(
        select(Approval).where(Approval.id == expired_approval.id)
    )
    approval = approval_result.scalar_one()

    assert approval.status == ApprovalStatus.REJECTED


@pytest.mark.asyncio
async def test_campaign_engine_pauses_over_budget(db_session: AsyncSession):
    """Test that campaign engine pauses over-budget campaigns."""
    # Create campaign over budget
    campaign = await RevenueCampaignService.create_campaign(
        db=db_session,
        name="Over Budget Campaign",
        slug="over-budget-campaign",
        budget_cents=100000,
    )

    campaign.status = CampaignStatus.ACTIVE
    campaign.spend_cents = 96000  # 96% used
    await db_session.commit()

    # Run campaign engine
    result = await campaign_engine_with_db(db_session)

    assert result["status"] == "completed"
    assert result["metrics"]["campaigns_paused_budget"] == 1

    # Verify campaign was paused
    campaign_result = await db_session.execute(
        select(RevenueCampaign).where(RevenueCampaign.id == campaign.id)
    )
    updated_campaign = campaign_result.scalar_one()

    assert updated_campaign.status == CampaignStatus.PAUSED


@pytest.mark.asyncio
async def test_send_pending_emails_processes_queue(db_session: AsyncSession, mock_resend_client):
    """Test that send_pending_emails processes email queue."""
    # Queue emails
    for i in range(3):
        await EmailService.queue_email(
            db=db_session,
            to_email=f"test{i}@example.com",
            subject=f"Test Email {i}",
            body="Test body",
        )

    # Run send pending emails
    result = await send_pending_emails_with_db(db_session, mock_resend_client)

    assert result["status"] == "completed"
    assert result["metrics"]["emails_processed"] == 3
    assert result["metrics"]["emails_sent"] == 3

    # Verify emails were sent
    sent_result = await db_session.execute(
        select(EmailOutbox).where(EmailOutbox.status == EmailStatus.SENT)
    )
    sent_emails = sent_result.scalars().all()

    assert len(sent_emails) == 3


@pytest.mark.asyncio
async def test_weekly_review_generates_summary(db_session: AsyncSession):
    """Test that weekly review generates strategy summary."""
    # Create some orders for the week
    for i in range(5):
        order = Order(
            platform="stripe",
            platform_order_id=f"week_order_{i}",
            customer_email=f"customer{i}@example.com",
            amount_cents=10000,
        )
        db_session.add(order)

    await db_session.commit()

    # Run weekly review
    result = await weekly_review_with_db(db_session)

    assert result["status"] == "completed"
    assert result["metrics"]["total_orders"] == 5
    assert result["metrics"]["total_revenue_cents"] == 50000
    assert result["strategy_log_id"]

    # Verify StrategyLog was created
    log_result = await db_session.execute(select(StrategyLog))
    logs = log_result.scalars().all()

    assert len(logs) == 1
    assert str(logs[0].id) == result["strategy_log_id"]


@pytest.mark.asyncio
async def test_concurrent_email_sending(db_session: AsyncSession, mock_resend_client):
    """Test concurrent email sending doesn't cause issues."""
    import asyncio

    # Queue multiple emails
    email_ids = []
    for i in range(10):
        email = await EmailService.queue_email(
            db=db_session,
            to_email=f"concurrent{i}@example.com",
            subject=f"Concurrent Test {i}",
            body="Test body",
        )
        email_ids.append(email.id)

    # Send all emails concurrently
    tasks = [
        EmailService.send_email(db_session, email_id, mock_resend_client)
        for email_id in email_ids
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # All should succeed
    successful = [r for r in results if r is True]
    assert len(successful) == 10


@pytest.mark.asyncio
async def test_campaign_budget_auto_pause_integration(db_session: AsyncSession):
    """Integration test for campaign budget auto-pause."""
    # Create multiple campaigns with different budget statuses
    campaigns = []

    # Campaign 1: Under budget (OK)
    c1 = await RevenueCampaignService.create_campaign(
        db=db_session,
        name="Under Budget",
        slug="under-budget",
        budget_cents=100000,
    )
    c1.status = CampaignStatus.ACTIVE
    c1.spend_cents = 50000  # 50% used
    campaigns.append(c1)

    # Campaign 2: Over budget (should pause)
    c2 = await RevenueCampaignService.create_campaign(
        db=db_session,
        name="Over Budget",
        slug="over-budget",
        budget_cents=100000,
    )
    c2.status = CampaignStatus.ACTIVE
    c2.spend_cents = 96000  # 96% used
    campaigns.append(c2)

    await db_session.commit()

    # Run auto-pause
    paused_count = await RevenueCampaignService.auto_pause_over_budget_campaigns(
        db=db_session,
    )

    assert paused_count == 1

    # Verify correct campaign was paused
    result = await db_session.execute(
        select(RevenueCampaign).where(RevenueCampaign.slug == "over-budget")
    )
    over_budget_campaign = result.scalar_one()

    assert over_budget_campaign.status == CampaignStatus.PAUSED


@pytest.mark.asyncio
async def test_commerce_ops_task_respects_lock(db_session: AsyncSession):
    from ..core.db_ops import acquire_automation_lock
    from ..celery.tasks.commerce_ops import commerce_ops_with_db

    async with acquire_automation_lock(db_session, "commerce_ops", ttl_seconds=300):
        result = await commerce_ops_with_db(db_session)
    assert result.get("skipped") is True
    assert "lock" in result.get("reason", "")


# ── Lock-skip (fail-closed) branches ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_daily_revenue_ops_skips_when_lock_held(db_session: AsyncSession):
    from ..core.db_ops import acquire_automation_lock

    async with acquire_automation_lock(db_session, "daily_revenue_ops", ttl_seconds=300):
        result = await daily_revenue_ops_with_db(db_session)
    assert result["status"] == "skipped"
    assert "lock" in result["reason"]


@pytest.mark.asyncio
async def test_hourly_monitor_skips_when_lock_held(db_session: AsyncSession):
    from ..core.db_ops import acquire_automation_lock

    async with acquire_automation_lock(db_session, "hourly_monitor", ttl_seconds=300):
        result = await hourly_monitor_with_db(db_session)
    assert result["status"] == "skipped"
    assert "lock" in result["reason"]


@pytest.mark.asyncio
async def test_campaign_engine_skips_when_lock_held(db_session: AsyncSession):
    from ..core.db_ops import acquire_automation_lock

    async with acquire_automation_lock(db_session, "campaign_engine", ttl_seconds=300):
        result = await campaign_engine_with_db(db_session)
    assert result["status"] == "skipped"
    assert "lock" in result["reason"]


@pytest.mark.asyncio
async def test_send_pending_emails_skips_when_lock_held(db_session: AsyncSession, mock_resend_client):
    from ..core.db_ops import acquire_automation_lock

    async with acquire_automation_lock(db_session, "send_pending_emails", ttl_seconds=300):
        result = await send_pending_emails_with_db(db_session, mock_resend_client)
    assert result["status"] == "skipped"
    assert "lock" in result["reason"]


@pytest.mark.asyncio
async def test_weekly_review_skips_when_lock_held(db_session: AsyncSession):
    from ..core.db_ops import acquire_automation_lock

    async with acquire_automation_lock(db_session, "weekly_review", ttl_seconds=300):
        result = await weekly_review_with_db(db_session)
    assert result["status"] == "skipped"
    assert "lock" in result["reason"]


# ── Process outbox ────────────────────────────────────────────────────────────


class MockRedis:
    """Minimal Redis Streams mock."""

    def __init__(self, fail=False):
        self.published = []
        self.fail = fail

    async def xadd(self, key, message):
        if self.fail:
            raise ConnectionError("redis down")
        self.published.append((key, message))


@pytest.mark.asyncio
async def test_process_outbox_publishes_events(db_session: AsyncSession):
    """Test that process_outbox publishes unprocessed events to Redis."""
    redis_client = MockRedis()

    for i in range(2):
        db_session.add(OutboxEvent(
            aggregate_type="order",
            aggregate_id=f"order-{i}",
            event_type="order.created",
            payload={"order_id": f"order-{i}"},
        ))
    await db_session.commit()

    result = await process_outbox_with_db(db_session, redis_client)

    assert result["status"] == "completed"
    assert result["metrics"]["processed"] == 2
    assert len(redis_client.published) == 2

    # Verify events marked processed
    events_result = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.processed == True)  # noqa: E712
    )
    processed_events = events_result.scalars().all()
    assert len(processed_events) == 2


@pytest.mark.asyncio
async def test_process_outbox_retries_failed_publish(db_session: AsyncSession):
    """Test that process_outbox increments retry_count on publish failure."""
    redis_client = MockRedis(fail=True)

    db_session.add(OutboxEvent(
        aggregate_type="order",
        aggregate_id="order-1",
        event_type="order.created",
        payload={"order_id": "order-1"},
    ))
    await db_session.commit()

    result = await process_outbox_with_db(db_session, redis_client)

    assert result["status"] == "completed"
    assert result["metrics"]["failed"] == 1
    assert result["metrics"]["processed"] == 0

    # Verify event not processed, retry_count incremented
    events_result = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.aggregate_id == "order-1")
    )
    event = events_result.scalar_one()

    assert event.processed is False
    assert event.retry_count == 1
    assert event.last_error is not None


@pytest.mark.asyncio
async def test_process_outbox_skips_max_retries(db_session: AsyncSession):
    """Test that process_outbox skips events past max retries."""
    redis_client = MockRedis()

    db_session.add(OutboxEvent(
        aggregate_type="order",
        aggregate_id="order-1",
        event_type="order.created",
        payload={"order_id": "order-1"},
        retry_count=3,  # At max retries — should be skipped
    ))
    await db_session.commit()

    result = await process_outbox_with_db(db_session, redis_client)

    assert result["status"] == "completed"
    assert result["metrics"]["processed"] == 0
    assert len(redis_client.published) == 0


@pytest.mark.asyncio
async def test_process_outbox_skips_when_lock_held(db_session: AsyncSession):
    from ..core.db_ops import acquire_automation_lock

    async with acquire_automation_lock(db_session, "process_outbox", ttl_seconds=300):
        result = await process_outbox_with_db(db_session, MockRedis())
    assert result["status"] == "skipped"
    assert "lock" in result["reason"]