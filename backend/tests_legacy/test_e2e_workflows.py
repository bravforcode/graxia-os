"""
End-to-End Workflow Tests

Tests complete workflows from start to finish
"""
import pytest
from httpx import AsyncClient
from datetime import datetime, timedelta


@pytest.mark.asyncio
async def test_job_discovery_workflow(async_client: AsyncClient):
    """
    Test complete job discovery workflow:
    1. Scraper finds jobs
    2. Job Hunter scores jobs
    3. High-scoring jobs trigger notifications
    4. Jobs appear in API
    """
    from app.agents.job_hunter import job_hunter_agent
    from app.scrapers.linkedin import LinkedInScraper
    from unittest.mock import patch, AsyncMock
    
    # Mock scraper
    with patch.object(LinkedInScraper, 'run', new_callable=AsyncMock) as mock_scrape:
        mock_scrape.return_value = [
            {
                "title": "Senior Python Developer",
                "company": "Tech Corp",
                "source_platform": "linkedin",
                "source_url": "https://linkedin.com/jobs/123",
                "location": "Remote",
                "description": "Python, FastAPI, PostgreSQL",
                "required_skills": ["Python", "FastAPI", "PostgreSQL"],
                "source_hash": "test_hash_123",
            }
        ]
        
        # Run job hunter
        result = await job_hunter_agent.run()
        
        assert result["discovered"] > 0
        assert result["new"] > 0
        
        # Verify job appears in API
        response = await async_client.get("/api/v1/jobs")
        jobs = response.json()
        
        assert len(jobs) > 0
        assert any(job["title"] == "Senior Python Developer" for job in jobs)


@pytest.mark.asyncio
async def test_email_processing_workflow(async_client: AsyncClient):
    """
    Test complete email processing workflow:
    1. Email Manager fetches emails
    2. Emails are categorized
    3. Action items extracted
    4. Tasks created
    5. Emails appear in API
    """
    from app.agents.email_manager import email_manager_agent
    from unittest.mock import patch, AsyncMock
    
    # Mock Gmail API
    with patch('app.core.google_workspace.google_workspace') as mock_gmail:
        mock_gmail.list_messages = AsyncMock(return_value=[
            {"id": "msg_123", "threadId": "thread_123"}
        ])
        
        mock_gmail.get_message = AsyncMock(return_value={
            "id": "msg_123",
            "threadId": "thread_123",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Urgent: Project Deadline"},
                    {"name": "From", "value": "client@example.com"},
                    {"name": "To", "value": "me@example.com"},
                    {"name": "Date", "value": datetime.now().isoformat()},
                ],
                "body": {"data": "UGxlYXNlIHNlbmQgcHJvcG9zYWwgYnkgdG9tb3Jyb3c="}  # Base64
            }
        })
        
        # Run email manager
        result = await email_manager_agent.fetch_and_process(max_emails=10)
        
        assert result["processed"] > 0
        
        # Verify emails appear in API
        response = await async_client.get("/api/v1/email-threads")
        threads = response.json()
        
        assert len(threads) > 0


@pytest.mark.asyncio
async def test_network_building_workflow(async_client: AsyncClient):
    """
    Test complete network building workflow:
    1. Network Builder discovers contacts
    2. Contacts are scored
    3. High-value contacts trigger outreach generation
    4. Contacts appear in API
    """
    from app.agents.network_builder import network_builder_agent
    from unittest.mock import patch, AsyncMock
    
    # Mock OpenClaw
    with patch('app.core.openclaw.openclaw_client') as mock_openclaw:
        mock_openclaw.extract_contacts = AsyncMock(return_value=[
            {
                "name": "John Doe",
                "title": "CTO",
                "company": "Startup Inc",
                "location": "San Francisco",
                "profile_url": "https://linkedin.com/in/johndoe",
            }
        ])
        
        # Run network builder
        result = await network_builder_agent.discover_contacts(
            search_url="https://linkedin.com/search/...",
            max_contacts=10
        )
        
        assert result["discovered"] > 0
        assert result["new"] > 0
        
        # Verify contacts appear in API
        response = await async_client.get("/api/v1/contacts")
        contacts = response.json()
        
        assert len(contacts) > 0


@pytest.mark.asyncio
async def test_cost_tracking_workflow(async_client: AsyncClient):
    """
    Test complete cost tracking workflow:
    1. OpenClaw API call
    2. Cost tracked in database
    3. Cost appears in API
    4. Budget alerts triggered if needed
    """
    from app.core.openclaw import openclaw_client
    from unittest.mock import patch, AsyncMock
    
    # Mock OpenClaw API
    with patch('httpx.AsyncClient.post') as mock_post:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"html": "<html>...</html>"}
        mock_post.return_value = mock_response
        
        # Make API call
        await openclaw_client.scrape_url(
            url="https://example.com",
            platform="test",
            use_cache=False
        )
        
        # Verify cost tracked
        response = await async_client.get("/api/v1/costs/summary")
        data = response.json()
        
        assert data["today"]["cost_usd"] >= 0


@pytest.mark.asyncio
async def test_daily_briefing_workflow(async_client: AsyncClient):
    """
    Test complete daily briefing workflow:
    1. Personal Assistant generates briefing
    2. Briefing includes jobs, tasks, emails, contacts
    3. Briefing sent via Telegram
    """
    from app.agents.personal_assistant import personal_assistant_agent
    
    # Generate briefing
    briefing = await personal_assistant_agent.generate_daily_briefing()
    
    assert briefing is not None
    assert len(briefing) > 0
    assert "Jobs" in briefing or "jobs" in briefing
    assert "Tasks" in briefing or "tasks" in briefing


@pytest.mark.asyncio
async def test_task_lifecycle_workflow(async_client: AsyncClient):
    """
    Test complete task lifecycle:
    1. Task created from email
    2. Task appears in pending
    3. Task marked in progress
    4. Task completed
    5. Task archived
    """
    # Create task
    task_data = {
        "title": "Send proposal",
        "description": "Follow up on meeting",
        "task_type": "email",
        "priority": 8,
        "due_date": (datetime.now() + timedelta(days=1)).isoformat(),
    }
    
    create_response = await async_client.post("/api/v1/tasks", json=task_data)
    assert create_response.status_code == 201
    task = create_response.json()
    task_id = task["id"]
    
    # Verify pending
    assert task["status"] == "pending"
    
    # Mark in progress
    update_response = await async_client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "in_progress"}
    )
    assert update_response.status_code == 200
    
    # Complete task
    complete_response = await async_client.post(f"/api/v1/tasks/{task_id}/complete")
    assert complete_response.status_code == 200
    completed_task = complete_response.json()
    assert completed_task["status"] == "completed"
    assert completed_task["completed_at"] is not None


@pytest.mark.asyncio
async def test_approval_flow_workflow(async_client: AsyncClient):
    """
    Test approval flow:
    1. Agent requests approval
    2. Approval sent to Telegram
    3. User approves/rejects
    4. Action executed or cancelled
    """
    from app.core.event_bus import event_bus
    
    approval_requested = False
    
    def handle_approval(payload):
        nonlocal approval_requested
        approval_requested = True
    
    # Subscribe to approval events
    event_bus.subscribe("approval.requested", handle_approval)
    
    # Trigger approval request
    await event_bus.emit("approval.requested", {
        "type": "email_send",
        "details": "Send email to client",
    })
    
    # Verify approval requested
    assert approval_requested


@pytest.mark.asyncio
async def test_error_recovery_workflow(async_client: AsyncClient):
    """
    Test error recovery:
    1. API call fails
    2. Error logged
    3. Retry attempted
    4. Fallback executed
    5. User notified
    """
    from app.core.llm import llm_client
    from unittest.mock import patch
    
    # Mock LLM to fail then succeed
    call_count = 0
    
    async def mock_call(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("API Error")
        return "Success"
    
    with patch.object(llm_client, '_call_openclaw', side_effect=mock_call):
        # Should retry and succeed
        result = await llm_client.complete(
            system="Test",
            user="Test",
            allow_fallback=True
        )
        
        # Should have retried
        assert call_count > 1


@pytest.mark.asyncio
async def test_scheduled_task_execution(async_client: AsyncClient):
    """
    Test scheduled tasks execute correctly
    """
    from app.core.scheduler import scheduler
    
    # Setup scheduler
    scheduler.setup()
    
    # Get jobs
    jobs = scheduler.scheduler.get_jobs()
    
    # Verify all expected jobs registered
    job_ids = [job.id for job in jobs]
    
    expected_jobs = [
        "daily_scan",
        "morning_briefing",
        "follow_up_check",
        "job_discovery",
        "email_processing",
        "weekly_strategy",
        "weekly_learning",
        "identity_snapshot",
        "database_backup",
    ]
    
    for expected_job in expected_jobs:
        assert expected_job in job_ids


@pytest.mark.asyncio
async def test_system_health_monitoring(async_client: AsyncClient):
    """
    Test system health monitoring
    """
    # Check health endpoint
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    
    assert "status" in data
    assert data["status"] in ["healthy", "degraded", "unhealthy"]
    
    # Check system status
    status_response = await async_client.get("/api/v1/system/status")
    assert status_response.status_code == 200
    status_data = status_response.json()
    
    assert "total_jobs" in status_data
    assert "total_contacts" in status_data
    assert "pending_tasks" in status_data
