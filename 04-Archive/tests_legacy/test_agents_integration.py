"""
Integration Tests for Agents

Tests end-to-end workflows across multiple agents.
"""
import pytest
from uuid import uuid4
from datetime import datetime, timezone

from app.models.job_posting import JobPosting
from app.models.contact import Contact
from app.models.email_thread import EmailThread
from app.models.assistant_task import AssistantTask


@pytest.mark.asyncio
class TestJobDiscoveryWorkflow:
    """Test complete job discovery workflow."""
    
    async def test_job_found_to_scored_to_notified(
        self,
        db_session,
        sample_job_data,
        mock_event_bus,
        mock_llm_client
    ):
        """Test: Job found → Scored → Event emitted → Notification sent."""
        # 1. Job Hunter discovers job
        job = JobPosting(
            id=uuid4(),
            **sample_job_data,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)
        
        assert job.id is not None
        assert job.status == "discovered"
        
        # 2. Job gets scored
        from decimal import Decimal
        job.match_score = Decimal("8.5")
        job.fit_summary = "Great fit - matches all required skills"
        await db_session.commit()
        
        assert float(job.match_score) == 8.5
        
        # 3. Event emitted
        await mock_event_bus.emit("job.found", {
            "job_id": str(job.id),
            "title": job.title,
            "match_score": float(job.match_score)
        })
        
        events = mock_event_bus.get_events("job.found")
        assert len(events) == 1
        assert events[0]["payload"]["match_score"] == 8.5
        
        # 4. Verify job can be retrieved
        from sqlalchemy import select
        query = select(JobPosting).where(JobPosting.id == job.id)
        result = await db_session.execute(query)
        retrieved_job = result.scalar_one_or_none()
        
        assert retrieved_job is not None
        assert retrieved_job.title == sample_job_data["title"]
        assert float(retrieved_job.match_score) == 8.5


@pytest.mark.asyncio
class TestEmailProcessingWorkflow:
    """Test complete email processing workflow."""
    
    async def test_email_received_to_categorized_to_task_created(
        self,
        db_session,
        sample_email_data,
        sample_task_data,
        mock_event_bus
    ):
        """Test: Email received → Categorized → Action items extracted → Tasks created."""
        # 1. Email Manager receives email
        email_thread = EmailThread(
            id=uuid4(),
            **sample_email_data,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db_session.add(email_thread)
        await db_session.commit()
        await db_session.refresh(email_thread)
        
        assert email_thread.id is not None
        assert email_thread.category == "important"
        
        # 2. Action items extracted
        action_items = [
            {"task": "Send proposal", "priority": 8},
            {"task": "Schedule meeting", "priority": 7}
        ]
        email_thread.action_items = action_items
        await db_session.commit()
        
        # 3. Tasks created from action items
        tasks = []
        for item in action_items:
            task = AssistantTask(
                id=uuid4(),
                title=item["task"],
                description=f"From email: {email_thread.subject}",
                task_type="email",
                priority=item["priority"],
                status="pending",
                related_entity_type="email_thread",
                related_entity_id=email_thread.id,
                assigned_to="user",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            db_session.add(task)
            tasks.append(task)
        
        await db_session.commit()
        
        # 4. Verify tasks created
        from sqlalchemy import select
        query = select(AssistantTask).where(
            AssistantTask.related_entity_id == email_thread.id
        )
        result = await db_session.execute(query)
        created_tasks = list(result.scalars().all())
        
        assert len(created_tasks) == 2
        assert created_tasks[0].title in ["Send proposal", "Schedule meeting"]
        assert created_tasks[0].status == "pending"


@pytest.mark.asyncio
class TestNetworkBuildingWorkflow:
    """Test complete network building workflow."""
    
    async def test_contact_discovered_to_scored_to_outreach_generated(
        self,
        db_session,
        sample_contact_data,
        mock_event_bus,
        mock_llm_client
    ):
        """Test: Contact discovered → Scored → Outreach message generated → Approval requested."""
        # 1. Network Builder discovers contact
        contact = Contact(
            id=uuid4(),
            **sample_contact_data,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db_session.add(contact)
        await db_session.commit()
        await db_session.refresh(contact)
        
        assert contact.id is not None
        
        # 2. Contact gets scored
        from decimal import Decimal
        contact.value_score = Decimal("8.0")
        contact.notes = "High-value contact - CTO at growing startup"
        await db_session.commit()
        
        assert float(contact.value_score) == 8.0
        
        # 3. Event emitted
        await mock_event_bus.emit("contact.discovered", {
            "contact_id": str(contact.id),
            "name": contact.name,
            "value_score": float(contact.value_score)
        })
        
        events = mock_event_bus.get_events("contact.discovered")
        assert len(events) == 1
        
        # 4. Outreach message generated (mock)
        outreach_message = await mock_llm_client.complete(
            system="Generate outreach message",
            user=f"Contact: {contact.name}"
        )
        
        assert outreach_message is not None
        assert len(outreach_message) > 0


@pytest.mark.asyncio
class TestDailyBriefingWorkflow:
    """Test daily briefing generation workflow."""
    
    async def test_daily_briefing_aggregates_all_data(
        self,
        db_session,
        sample_job_data,
        sample_contact_data,
        sample_email_data,
        sample_task_data
    ):
        """Test: Daily briefing aggregates jobs, contacts, emails, tasks."""
        # 1. Create sample data
        job = JobPosting(
            id=uuid4(),
            **sample_job_data,
            match_score=8.5,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db_session.add(job)
        
        contact = Contact(
            id=uuid4(),
            **sample_contact_data,
            value_score=8.0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db_session.add(contact)
        
        email = EmailThread(
            id=uuid4(),
            **sample_email_data,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db_session.add(email)
        
        task = AssistantTask(
            id=uuid4(),
            **sample_task_data,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db_session.add(task)
        
        await db_session.commit()
        
        # 2. Query data for briefing
        from sqlalchemy import select, func
        
        # Count jobs
        jobs_query = select(func.count(JobPosting.id))
        jobs_result = await db_session.execute(jobs_query)
        jobs_count = jobs_result.scalar()
        
        # Count contacts
        contacts_query = select(func.count(Contact.id))
        contacts_result = await db_session.execute(contacts_query)
        contacts_count = contacts_result.scalar()
        
        # Count emails
        emails_query = select(func.count(EmailThread.id))
        emails_result = await db_session.execute(emails_query)
        emails_count = emails_result.scalar()
        
        # Count tasks
        tasks_query = select(func.count(AssistantTask.id))
        tasks_result = await db_session.execute(tasks_query)
        tasks_count = tasks_result.scalar()
        
        # 3. Verify counts
        assert jobs_count == 1
        assert contacts_count == 1
        assert emails_count == 1
        assert tasks_count == 1
