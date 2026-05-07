"""
Test Campaign Service
Verify revenue campaign management and budget tracking
"""
import pytest
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..services.campaign_service import RevenueCampaignService
from ..models import RevenueCampaign, AttributionEvent, IncidentEvent
from ..enums import CampaignStatus, IncidentSeverity


@pytest.mark.asyncio
async def test_create_campaign(db_session: AsyncSession):
    """Test creating a revenue campaign."""
    campaign = await RevenueCampaignService.create_campaign(
        db=db_session,
        name="Test Campaign",
        slug="test-campaign",
        objective="lead_to_sale",
        budget_cents=100000,  # 1000 THB
        target_revenue_cents=500000,  # 5000 THB
        utm_source="google",
        utm_medium="cpc",
        utm_campaign="test-campaign",
    )
    
    assert campaign.id is not None
    assert campaign.name == "Test Campaign"
    assert campaign.status == CampaignStatus.DRAFT
    assert campaign.budget_cents == 100000
    assert campaign.target_revenue_cents == 500000


@pytest.mark.asyncio
async def test_pause_campaign(db_session: AsyncSession):
    """Test pausing a campaign."""
    # Create campaign
    campaign = await RevenueCampaignService.create_campaign(
        db=db_session,
        name="Pause Test",
        slug="pause-test",
        budget_cents=100000,
    )
    
    # Set to active first
    campaign.status = CampaignStatus.ACTIVE
    await db_session.commit()
    
    # Pause campaign
    paused = await RevenueCampaignService.pause_campaign(
        db=db_session,
        campaign_id=campaign.id,
        reason="Budget exceeded",
    )
    
    assert paused.status == CampaignStatus.PAUSED
    assert paused.paused_reason == "Budget exceeded"


@pytest.mark.asyncio
async def test_resume_campaign(db_session: AsyncSession):
    """Test resuming a paused campaign."""
    # Create and pause campaign
    campaign = await RevenueCampaignService.create_campaign(
        db=db_session,
        name="Resume Test",
        slug="resume-test",
        budget_cents=100000,
    )
    
    campaign.status = CampaignStatus.PAUSED
    campaign.paused_reason = "Test pause"
    await db_session.commit()
    
    # Resume campaign
    resumed = await RevenueCampaignService.resume_campaign(
        db=db_session,
        campaign_id=campaign.id,
    )
    
    assert resumed.status == CampaignStatus.ACTIVE
    assert resumed.paused_reason is None


@pytest.mark.asyncio
async def test_update_campaign_metrics(db_session: AsyncSession):
    """Test updating campaign metrics from attribution events."""
    # Create campaign
    campaign = await RevenueCampaignService.create_campaign(
        db=db_session,
        name="Metrics Test",
        slug="metrics-test",
        budget_cents=100000,
    )
    
    # Create attribution events
    events = [
        AttributionEvent(
            campaign_id=campaign.id,
            event_type="sale",
            value_cents=5000,
        ),
        AttributionEvent(
            campaign_id=campaign.id,
            event_type="sale",
            value_cents=3000,
        ),
        AttributionEvent(
            campaign_id=campaign.id,
            event_type="click",
            value_cents=100,
        ),
    ]
    
    for event in events:
        db_session.add(event)
    
    await db_session.commit()
    
    # Update metrics
    updated = await RevenueCampaignService.update_campaign_metrics(
        db=db_session,
        campaign_id=campaign.id,
    )
    
    assert updated.actual_revenue_cents == 8000  # 5000 + 3000
    assert updated.spend_cents == 100
    assert updated.metrics["roas"] == 80.0  # 8000 / 100


@pytest.mark.asyncio
async def test_check_campaign_budget_ok(db_session: AsyncSession):
    """Test budget check when budget is OK."""
    # Create campaign with budget
    campaign = await RevenueCampaignService.create_campaign(
        db=db_session,
        name="Budget OK",
        slug="budget-ok",
        budget_cents=100000,
    )
    
    campaign.spend_cents = 50000  # 50% used
    await db_session.commit()
    
    # Check budget
    status = await RevenueCampaignService.check_campaign_budget(
        db=db_session,
        campaign_id=campaign.id,
    )
    
    assert status["status"] == "ok"
    assert status["should_pause"] is False
    assert status["budget_used_ratio"] == 0.5


@pytest.mark.asyncio
async def test_check_campaign_budget_warning(db_session: AsyncSession):
    """Test budget check when budget is at warning threshold."""
    # Create campaign
    campaign = await RevenueCampaignService.create_campaign(
        db=db_session,
        name="Budget Warning",
        slug="budget-warning",
        budget_cents=100000,
    )
    
    campaign.spend_cents = 85000  # 85% used (warning threshold)
    await db_session.commit()
    
    # Check budget
    status = await RevenueCampaignService.check_campaign_budget(
        db=db_session,
        campaign_id=campaign.id,
    )
    
    assert status["status"] == "warning"
    assert status["should_pause"] is False


@pytest.mark.asyncio
async def test_check_campaign_budget_critical(db_session: AsyncSession):
    """Test budget check when budget is at critical threshold."""
    # Create campaign
    campaign = await RevenueCampaignService.create_campaign(
        db=db_session,
        name="Budget Critical",
        slug="budget-critical",
        budget_cents=100000,
    )
    
    campaign.spend_cents = 96000  # 96% used (critical threshold)
    await db_session.commit()
    
    # Check budget
    status = await RevenueCampaignService.check_campaign_budget(
        db=db_session,
        campaign_id=campaign.id,
    )
    
    assert status["status"] == "critical"
    assert status["should_pause"] is True


@pytest.mark.asyncio
async def test_auto_pause_over_budget_campaigns(db_session: AsyncSession):
    """Test auto-pausing campaigns that exceeded budget."""
    # Create campaign over budget
    campaign = await RevenueCampaignService.create_campaign(
        db=db_session,
        name="Over Budget",
        slug="over-budget",
        budget_cents=100000,
    )
    
    campaign.status = CampaignStatus.ACTIVE
    campaign.spend_cents = 96000  # 96% used
    await db_session.commit()
    
    # Auto-pause over budget campaigns
    paused_count = await RevenueCampaignService.auto_pause_over_budget_campaigns(
        db=db_session,
    )
    
    assert paused_count == 1
    
    # Verify campaign was paused
    result = await db_session.execute(
        select(RevenueCampaign).where(RevenueCampaign.id == campaign.id)
    )
    paused_campaign = result.scalar_one()
    
    assert paused_campaign.status == CampaignStatus.PAUSED
    assert "Budget" in paused_campaign.paused_reason


@pytest.mark.asyncio
async def test_auto_pause_campaigns_with_critical_incidents(db_session: AsyncSession):
    """Test auto-pausing campaigns with critical incidents."""
    # Create campaign
    campaign = await RevenueCampaignService.create_campaign(
        db=db_session,
        name="Incident Test",
        slug="incident-test",
        budget_cents=100000,
    )
    
    campaign.status = CampaignStatus.ACTIVE
    await db_session.commit()
    
    # Create critical incident
    incident = IncidentEvent(
        affected_campaign_id=campaign.id,
        severity=IncidentSeverity.CRITICAL,
        title="Critical Issue",
        description="Something went wrong",
        status="open",
    )
    db_session.add(incident)
    await db_session.commit()
    
    # Auto-pause campaigns with incidents
    paused_count = await RevenueCampaignService.auto_pause_campaigns_with_critical_incidents(
        db=db_session,
    )
    
    assert paused_count == 1
    
    # Verify campaign was paused
    result = await db_session.execute(
        select(RevenueCampaign).where(RevenueCampaign.id == campaign.id)
    )
    paused_campaign = result.scalar_one()
    
    assert paused_campaign.status == CampaignStatus.PAUSED
    assert "incident" in paused_campaign.paused_reason.lower()


@pytest.mark.asyncio
async def test_get_active_campaigns(db_session: AsyncSession):
    """Test getting all active campaigns."""
    # Create multiple campaigns
    for i in range(3):
        campaign = await RevenueCampaignService.create_campaign(
            db=db_session,
            name=f"Campaign {i}",
            slug=f"campaign-{i}",
            budget_cents=100000,
        )
        campaign.status = CampaignStatus.ACTIVE
    
    await db_session.commit()
    
    # Get active campaigns
    active = await RevenueCampaignService.get_active_campaigns(db_session)
    
    assert len(active) == 3
    assert all(c.status == CampaignStatus.ACTIVE for c in active)
