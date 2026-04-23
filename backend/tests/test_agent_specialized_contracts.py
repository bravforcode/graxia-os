import base64
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.agents.email_manager import EmailManagerAgent
from app.agents.job_hunter import JobHunterAgent
from app.agents.network_builder import NetworkBuilderAgent
from app.agents.personal_assistant import PersonalAssistantAgent
from app.core.event_bus import event_bus
from app.core.time_utils import business_today
from app.models.assistant_task import AssistantTask
from app.models.audit import AuditLog
from app.models.contact import Contact
from app.models.email_message import EmailMessage
from app.models.email_thread import EmailThread
from app.models.job_posting import JobPosting
from app.models.network_interaction import NetworkInteraction
from app.models.openclaw_usage import OpenClawUsage


@pytest_asyncio.fixture()
async def specialized_session_factory(session_factory, monkeypatch):
    monkeypatch.setattr("app.database.AsyncSessionLocal", session_factory)
    monkeypatch.setattr("app.agents.job_hunter.AsyncSessionLocal", session_factory)
    monkeypatch.setattr("app.agents.network_builder.AsyncSessionLocal", session_factory)
    monkeypatch.setattr("app.agents.email_manager.AsyncSessionLocal", session_factory)
    monkeypatch.setattr("app.agents.personal_assistant.AsyncSessionLocal", session_factory)
    yield session_factory


class _FakeJobScraper:
    source_name = "linkedin"

    async def run(self):
        return [
            {
                "title": "Senior FastAPI Engineer",
                "company": "Signal Forge",
                "source_platform": "linkedin",
                "source_url": "https://example.com/jobs/1",
                "location": "Remote",
                "job_type": "job",
                "description": "Build Python and FastAPI systems for enterprise clients.",
                "required_skills": ["python", "fastapi"],
                "source_hash": "job-1",
                "raw_data": {"id": 1},
            },
            {
                "title": "Senior FastAPI Engineer",
                "company": "Signal Forge",
                "source_platform": "linkedin",
                "source_url": "https://example.com/jobs/1",
                "location": "Remote",
                "job_type": "job",
                "description": "Duplicate row from scraper pagination.",
                "required_skills": ["python", "fastapi"],
                "source_hash": "job-1",
                "raw_data": {"id": 2},
            },
        ]


@pytest.mark.asyncio
async def test_job_hunter_run_persists_scores_and_emits_scored_payload(
    specialized_session_factory, monkeypatch
):
    monkeypatch.setattr(
        "app.core.llm.llm_client.complete_json",
        AsyncMock(
            return_value={
                "score": 8.4,
                "summary": "Strong fit for Python backend delivery.",
                "matched_skills": ["python", "fastapi"],
                "skill_gaps": ["kubernetes"],
            }
        ),
    )
    emit = AsyncMock()
    monkeypatch.setattr(event_bus, "emit", emit)

    agent = JobHunterAgent()
    agent.scrapers = [_FakeJobScraper()]

    result = await agent.run()

    assert result == {"discovered": 2, "new": 1, "duplicates": 1, "errors": []}

    async with specialized_session_factory() as db:
        job = (await db.execute(select(JobPosting))).scalar_one()
        audit = (
            await db.execute(
                select(AuditLog).where(AuditLog.action == "job_hunter.run")
            )
        ).scalar_one()

    assert float(job.match_score) == pytest.approx(8.4)
    assert job.fit_summary == "Strong fit for Python backend delivery."
    assert job.matched_skills == ["python", "fastapi"]
    assert job.skill_gap_list == ["kubernetes"]
    assert audit.triggered_by == "job_hunter"
    emit.assert_awaited_once()
    emitted_event, payload = emit.await_args.args
    assert emitted_event == "job.found"
    assert payload["title"] == "Senior FastAPI Engineer"
    assert payload["match_score"] == pytest.approx(8.4)


@pytest.mark.asyncio
async def test_network_builder_discovers_scores_and_generates_outreach(
    specialized_session_factory, monkeypatch
):
    monkeypatch.setattr(
        "app.core.openclaw.openclaw_client.extract_contacts",
        AsyncMock(
            return_value=[
                {
                    "name": "Jane Doe",
                    "title": "CTO",
                    "company": "Acme Health",
                    "location": "Bangkok",
                    "profile_url": "https://linkedin.com/in/jane-doe",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        "app.core.llm.llm_client.complete_json",
        AsyncMock(
            return_value={
                "score": 8,
                "summary": "Strong operator with relevant healthtech network.",
                "outreach_angle": "Mention shared interest in AI operations.",
            }
        ),
    )
    monkeypatch.setattr(
        "app.core.llm.llm_client.complete",
        AsyncMock(return_value="Hi Jane, I liked your work in healthtech ops."),
    )
    emit = AsyncMock()
    monkeypatch.setattr(event_bus, "emit", emit)

    agent = NetworkBuilderAgent()
    result = await agent.discover_contacts(
        "https://linkedin.com/search/results/people/?keywords=healthtech"
    )

    assert result == {"discovered": 1, "new": 1, "existing": 0}

    async with specialized_session_factory() as db:
        contact = (await db.execute(select(Contact))).scalar_one()
        discover_audit = (
            await db.execute(
                select(AuditLog).where(AuditLog.action == "network_builder.discover")
            )
        ).scalar_one()

    assert contact.name == "Jane Doe"
    assert contact.role == "CTO"
    assert contact.company == "Acme Health"
    assert contact.relationship_strength == 1
    assert contact.value_score == 8
    assert "healthtech network" in (contact.notes or "")
    assert discover_audit.triggered_by == "network_builder"
    emit.assert_awaited_once()
    emitted_event, payload = emit.await_args.args
    assert emitted_event == "contact.discovered"
    assert payload["title"] == "CTO"
    assert payload["value_score"] == 8.0

    message = await agent.generate_outreach(str(contact.id), context="Shared AI ops interest")
    assert message == "Hi Jane, I liked your work in healthtech ops."

    async with specialized_session_factory() as db:
        refreshed_contact = await db.get(Contact, contact.id)
        interaction = (await db.execute(select(NetworkInteraction))).scalar_one()

    assert interaction.interaction_type == "outreach_generated"
    assert refreshed_contact.last_contacted_at == business_today()
    assert refreshed_contact.relationship_strength == 2


@pytest.mark.asyncio
async def test_email_manager_fetch_and_process_persists_thread_message_and_tasks(
    specialized_session_factory, monkeypatch
):
    encoded_body = base64.urlsafe_b64encode(
        b"Please send your updated portfolio by April 10."
    ).decode()
    full_message = {
        "id": "gmail-message-1",
        "threadId": "gmail-thread-1",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Interview next steps"},
                {"name": "From", "value": "Hiring Team <team@example.com>"},
                {"name": "To", "value": "me@example.com"},
                {"name": "Date", "value": "Thu, 09 Apr 2026 10:00:00 +0700"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": encoded_body},
                }
            ],
        },
    }
    monkeypatch.setattr(
        "app.core.google_workspace.google_workspace.list_messages",
        AsyncMock(return_value=[{"id": "gmail-message-1"}]),
    )
    monkeypatch.setattr(
        "app.core.google_workspace.google_workspace.get_message",
        AsyncMock(return_value=full_message),
    )

    async def fake_complete_json(*, system, user, **kwargs):
        if "Extract action items" not in system:
            raise AssertionError("Categorization should use heuristics for interview emails")
        return {
            "action_items": [
                {
                    "task": "Send updated portfolio",
                    "due_date": "2026-04-10T17:00:00+07:00",
                    "priority": 8,
                }
            ]
        }

    monkeypatch.setattr("app.core.llm.llm_client.complete_json", fake_complete_json)
    emit = AsyncMock()
    monkeypatch.setattr(event_bus, "emit", emit)

    result = await EmailManagerAgent().fetch_and_process(max_emails=5)

    assert result["processed"] == 1
    assert result["categorized"]["important"] == 1
    assert result["action_items_created"] == 1

    async with specialized_session_factory() as db:
        thread = (await db.execute(select(EmailThread))).scalar_one()
        message = (await db.execute(select(EmailMessage))).scalar_one()
        task = (await db.execute(select(AssistantTask))).scalar_one()
        audit = (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.action == "email_manager.fetch_and_process"
                )
            )
        ).scalar_one()

    assert thread.subject == "Interview next steps"
    assert thread.category == "important"
    assert thread.priority == 8
    assert thread.unread_count == 1
    assert thread.participants == [{"email": "team@example.com", "name": "Hiring Team"}]
    assert thread.action_items == [{"task": "Send updated portfolio", "priority": 8}]
    assert message.message_id == "gmail-message-1"
    assert "updated portfolio" in (message.body or "")
    assert task.title == "Send updated portfolio"
    assert task.related_entity_type == "email_thread"
    assert task.related_entity_id == thread.id
    assert audit.triggered_by == "email_manager"
    emit.assert_awaited_once()


@pytest.mark.asyncio
async def test_personal_assistant_daily_briefing_uses_current_contact_schema(
    specialized_session_factory,
):
    now = datetime.now(timezone.utc)
    async with specialized_session_factory() as db:
        db.add(
            JobPosting(
                title="Lead Automation Engineer",
                company="Acme Health",
                source_platform="linkedin",
                source_url="https://example.com/jobs/lead-automation",
                location="Remote",
                job_type="job",
                description="Build automation systems.",
                match_score=Decimal("8.90"),
                status="discovered",
                source_hash="briefing-job",
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            AssistantTask(
                title="Reply to hiring manager",
                description="Confirm interview slot.",
                task_type="email",
                priority=9,
                status="pending",
                due_date=now + timedelta(hours=8),
                assigned_to="user",
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            EmailThread(
                thread_id="briefing-thread",
                subject="Interview invitation",
                participants=[{"email": "recruiter@example.com", "name": "Recruiter"}],
                category="urgent",
                priority=9,
                last_message_at=now,
                unread_count=1,
                has_attachments=False,
                action_items=[],
                status="unread",
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            Contact(
                name="Jane Mentor",
                role="CTO",
                company="Acme Health",
                email="jane@example.com",
                relationship_strength=2,
                value_score=8,
                last_contacted_at=business_today() - timedelta(days=10),
            )
        )
        db.add(
            OpenClawUsage(
                platform="linkedin",
                action="extract_contacts",
                cost_usd=Decimal("0.3500"),
                created_at=now,
            )
        )
        await db.commit()

    briefing = await PersonalAssistantAgent().generate_daily_briefing()

    assert "Lead Automation Engineer" in briefing
    assert "Reply to hiring manager" in briefing
    assert "Interview invitation" in briefing
    assert "Jane Mentor" in briefing
    assert "CTO at Acme Health" in briefing
    assert "Error loading contacts" not in briefing

    async with specialized_session_factory() as db:
        audit = (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.action == "personal_assistant.daily_briefing"
                )
            )
        ).scalar_one()

    assert audit.triggered_by == "personal_assistant"
