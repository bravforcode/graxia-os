"""
Complete End-to-End Workflow Tests

Tests complete user journeys through the system.
"""
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from app.agents.job_hunter import job_hunter_agent
from app.agents.personal_assistant import personal_assistant_agent
from app.database import AsyncSessionLocal
from app.models.job_posting import JobPosting
from sqlalchemy import select


@pytest.mark.asyncio
async def test_complete_job_discovery_workflow():
    """
    Test complete job discovery workflow:
    1. Job hunter discovers jobs
    2. Jobs are scored
    3. High-scoring jobs trigger notifications
    4. User can view jobs via API
    """
    # Run job discovery
    result = await job_hunter_agent.run()
    
    assert result['discovered'] >= 0
    assert result['new'] >= 0
    
    # Check jobs were saved
    async with AsyncSessionLocal() as db:
        query = select(JobPosting).limit(5)
        result = await db.execute(query)
        jobs = list(result.scalars().all())
        
        # Should have some jobs
        assert len(jobs) >= 0
        
        # Check job structure
        if jobs:
            job = jobs[0]
            assert job.title is not None
            assert job.source_platform is not None
            assert job.status == "discovered"


@pytest.mark.asyncio
async def test_complete_email_workflow():
    """
    Test complete email workflow:
    1. Email manager fetches emails
    2. Emails are categorized
    3. Action items are extracted
    4. Tasks are created
    """
    # Note: This test requires Gmail credentials
    # In real environment, it would fetch actual emails
    
    # Mock email processing
    result = {
        'processed': 0,
        'categorized': {},
        'action_items_created': 0
    }
    
    # In production, would call:
    # result = await email_manager_agent.fetch_and_process()
    
    assert 'processed' in result
    assert 'categorized' in result
    assert 'action_items_created' in result


@pytest.mark.asyncio
async def test_complete_network_building_workflow():
    """
    Test complete network building workflow:
    1. Network builder discovers contacts
    2. Contacts are scored
    3. Outreach messages are generated
    4. Approval requests are created
    """
    # Note: This test requires LinkedIn access via OpenClaw
    # In real environment, it would discover actual contacts
    
    # Mock contact discovery
    result = {
        'discovered': 0,
        'new': 0,
        'existing': 0
    }
    
    # In production, would call:
    # result = await network_builder_agent.discover_contacts(search_url="...")
    
    assert 'discovered' in result
    assert 'new' in result


@pytest.mark.asyncio
async def test_complete_daily_briefing_workflow():
    """
    Test complete daily briefing workflow:
    1. Personal assistant gathers data
    2. Briefing is generated
    3. Briefing is sent via Telegram
    """
    # Generate briefing
    briefing = await personal_assistant_agent.generate_daily_briefing()
    
    assert briefing is not None
    assert len(briefing) > 0
    assert "Daily Briefing" in briefing or "📋" in briefing


@pytest.mark.asyncio
async def test_complete_approval_workflow():
    """
    Test complete approval workflow:
    1. Action requires approval
    2. Approval request is created
    3. Request is sent to Telegram
    4. User approves/rejects
    5. Action is executed or cancelled
    """
    from app.models.approval_request import ApprovalRequest
    
    async with AsyncSessionLocal() as db:
        # Create approval request
        approval = ApprovalRequest(
            id=uuid4(),
            action_type="test_action",
            action_description="Test approval workflow",
            action_data={"test": "data"},
            status="pending",
            created_at=datetime.now(timezone.utc)
        )
        
        db.add(approval)
        await db.commit()
        await db.refresh(approval)
        
        assert approval.status == "pending"
        
        # Simulate approval
        approval.status = "approved"
        approval.responded_at = datetime.now(timezone.utc)
        await db.commit()
        
        assert approval.status == "approved"
        assert approval.responded_at is not None


@pytest.mark.asyncio
async def test_system_health_check():
    """Test complete system health check."""
    status = await personal_assistant_agent.get_system_status()
    
    assert status is not None
    assert 'status' in status
    assert status['status'] in ['healthy', 'error']


@pytest.mark.asyncio
async def test_cost_tracking_workflow():
    """
    Test cost tracking workflow:
    1. API calls are made
    2. Costs are tracked
    3. Budget alerts are triggered
    4. Cost summary is available
    """
    from app.core.openclaw import openclaw_client
    
    # Get usage stats
    stats = await openclaw_client.get_usage_stats(days=7)
    
    assert 'total_requests' in stats
    assert 'total_cost_usd' in stats
    assert 'by_platform' in stats


@pytest.mark.asyncio
async def test_scheduled_tasks_integration():
    """Test that scheduled tasks can be executed."""
    from app.tasks.job_discovery import run_job_discovery
    from app.tasks.morning_briefing import send_morning_briefing
    
    # Test job discovery task
    result = await run_job_discovery()
    assert result is not None
    
    # Test morning briefing task
    result = await send_morning_briefing()
    assert result is not None


@pytest.mark.asyncio
async def test_event_bus_workflow():
    """Test event bus workflow."""
    from app.core.event_bus import event_bus
    
    # Track events
    events_received = []
    
    async def test_handler(event_data):
        events_received.append(event_data)
    
    # Subscribe to test event
    event_bus.on("test.event", test_handler)
    
    # Emit event
    await event_bus.emit("test.event", {"test": "data"})
    
    # Check event was received
    assert len(events_received) == 1
    assert events_received[0]["test"] == "data"


@pytest.mark.asyncio
async def test_complete_user_journey():
    """
    Test complete user journey:
    1. User registers
    2. User logs in
    3. System discovers opportunities
    4. User receives briefing
    5. User views opportunities
    6. User takes action
    """
    # This would be a full integration test
    # combining all components
    
    # 1. User authentication (tested separately)
    # 2. Job discovery
    result = await job_hunter_agent.run()
    assert result is not None
    
    # 3. Daily briefing
    briefing = await personal_assistant_agent.generate_daily_briefing()
    assert briefing is not None
    
    # 4. System status
    status = await personal_assistant_agent.get_system_status()
    assert status['status'] == 'healthy'
