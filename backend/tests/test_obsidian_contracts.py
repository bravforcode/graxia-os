from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest

from app.agents.obsidian_sync import obsidian_sync_agent
from app.core.bootstrap import wire_event_handlers
from app.core.event_bus import event_bus
from app.integrations.obsidian import ObsidianConnector
from app.models.assistant_task import AssistantTask
from app.models.contact import Contact
from app.models.knowledge import KnowledgeItem
from app.models.opportunity import Opportunity
from app.models.skill_profile import SkillProfile
from app.models.submission import Submission


def _fake_profile() -> dict:
    return {
        "personal": {
            "name": "Phirawit Jitnarong",
            "bio_short_en": "Builder of systems that remove manual work.",
        },
        "current_status": {
            "role": "Founder",
            "current_positioning": "full-stack developer & systems architect",
        },
        "goals": {
            "north_star": "Run a disciplined software business backed by reusable systems.",
        },
        "projects": [
            {
                "name": "Testlyn",
                "tagline": "Hospital management platform",
                "description": "Digitises clinic operations and patient workflows.",
                "tech_stack": ["FastAPI", "React", "PostgreSQL"],
                "github_url": "https://github.com/bravforcode/testlyn",
                "live_url": "https://testlyn.example.com",
                "best_for": ["startup_pitch", "freelance_portfolio"],
            }
        ],
        "skills": {
            "technical": [
                {"name": "FastAPI", "level": "advanced", "years": 2},
                {"name": "React", "level": "advanced", "years": 2},
            ],
            "soft": ["systems thinker"],
        },
    }


@pytest.mark.asyncio
async def test_second_brain_bootstrap_creates_single_vault_scaffold(tmp_path: Path):
    connector = ObsidianConnector(
        vault_path=str(tmp_path),
        root_folder="Second Brain",
    )

    result = await connector.bootstrap_second_brain(
        profile=_fake_profile(),
        skill_inventory=[
            {
                "name": "FastAPI",
                "category": "technical",
                "level": "advanced",
                "years_experience": "2.0",
                "evidence": ["Testlyn"],
            },
            {
                "name": "React",
                "category": "technical",
                "level": "advanced",
                "years_experience": "2.0",
                "evidence": ["Testlyn"],
            },
        ],
    )

    second_brain_root = tmp_path / "Second Brain"
    assert result["root_folder"] == "Second Brain"
    assert result["project_count"] == 1
    assert result["skill_count"] >= 2
    assert (second_brain_root / "Atlas.md").exists()
    assert (second_brain_root / "Dashboard.md").exists()
    assert (second_brain_root / "Projects" / "Index.md").exists()
    assert (second_brain_root / "Projects" / "testlyn" / "Overview.md").exists()
    assert (second_brain_root / "Projects" / "testlyn" / "Context.md").exists()
    assert (second_brain_root / "Projects" / "testlyn" / "Activity Log.md").exists()
    assert (second_brain_root / "Projects" / "testlyn" / "Tasks.md").exists()
    assert (second_brain_root / "Projects" / "testlyn" / "Skills.md").exists()
    assert (second_brain_root / "Skills" / "Index.md").exists()
    assert (second_brain_root / "Skills" / "Technical" / "fastapi.md").exists()

    atlas = (second_brain_root / "Atlas.md").read_text(encoding="utf-8")
    overview = (
        second_brain_root / "Projects" / "testlyn" / "Overview.md"
    ).read_text(encoding="utf-8")
    skill_note = (
        second_brain_root / "Skills" / "Technical" / "fastapi.md"
    ).read_text(encoding="utf-8")

    assert "[[Dashboard]]" in atlas
    assert "Hospital management platform" in overview
    assert "Testlyn" in skill_note


@pytest.mark.asyncio
async def test_obsidian_sync_agent_supports_current_entity_schemas(
    session_factory, monkeypatch, tmp_path: Path
):
    import app.agents.obsidian_sync as obsidian_sync_module
    import app.integrations.obsidian as obsidian_module

    connector = ObsidianConnector(
        vault_path=str(tmp_path),
        root_folder="Second Brain",
    )
    monkeypatch.setattr(obsidian_module, "obsidian_connector", connector)
    monkeypatch.setattr(obsidian_sync_module.database, "AsyncSessionLocal", session_factory)

    opportunity_id = uuid4()
    submission_id = uuid4()
    contact_id = uuid4()
    task_id = uuid4()
    knowledge_id = uuid4()

    async with session_factory() as session:
        session.add(
            Opportunity(
                id=opportunity_id,
                type="job",
                title="Senior API Platform Engineer",
                description="Build resilient backend systems.",
                source_url="https://example.com/jobs/123",
                source_platform="linkedin",
                total_score=Decimal("8.70"),
                scoring_rationale="Strong technical fit.",
                action_priority="do_now",
                status="found",
                deadline=date(2026, 4, 20),
                tags=["python", "backend"],
                raw_data={"project_slug": "testlyn"},
                found_at=datetime(2026, 4, 10, tzinfo=timezone.utc),
            )
        )
        session.add(
            Submission(
                id=submission_id,
                opportunity_id=opportunity_id,
                title="Testlyn integration proposal",
                status="sent",
                type="proposal",
                content="We can deliver the integration in two phases.",
                sent_at=datetime(2026, 4, 10, 6, 30, tzinfo=timezone.utc),
                outcome_notes="Waiting for reply",
                created_at=datetime(2026, 4, 10, 6, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 4, 10, 6, 30, tzinfo=timezone.utc),
            )
        )
        session.add(
            Contact(
                id=contact_id,
                name="Aom Founder",
                email="aom@example.com",
                company="Testlyn Labs",
                role="Founder",
                linkedin_url="https://linkedin.com/in/aom",
                relationship_strength=4,
                last_contacted_at=date(2026, 4, 9),
                notes="Warm lead.",
            )
        )
        session.add(
            AssistantTask(
                id=task_id,
                title="Prepare Testlyn rollout plan",
                description="Write the migration and rollout checklist.",
                task_type="planning",
                priority=8,
                status="pending",
                assigned_to="user",
                due_date=datetime(2026, 4, 11, 9, 0, tzinfo=timezone.utc),
                created_at=datetime(2026, 4, 10, 7, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 4, 10, 7, 0, tzinfo=timezone.utc),
            )
        )
        session.add(
            SkillProfile(
                name="FastAPI",
                normalized_name="fastapi",
                category="technical",
                level="advanced",
                years_experience=Decimal("2.0"),
                evidence=["Testlyn"],
                aliases=["fastapi"],
                source="identity_profile",
                is_active=True,
            )
        )
        session.add(
            KnowledgeItem(
                id=knowledge_id,
                category="playbook",
                title="How Testlyn wins technical pitches",
                content="Lead with delivery proof and narrow scope early.",
                tags=["playbook", "testlyn"],
                best_for=["startup_pitch"],
                tech_stack=["FastAPI", "React"],
                is_active=True,
            )
        )
        await session.commit()

    await obsidian_sync_agent.sync_opportunity(str(opportunity_id))
    await obsidian_sync_agent.sync_submission(str(submission_id))
    await obsidian_sync_agent.sync_contact(str(contact_id))
    await obsidian_sync_agent.sync_task(str(task_id))
    await obsidian_sync_agent.sync_knowledge_item(str(knowledge_id))

    second_brain_root = tmp_path / "Second Brain"
    opportunity_note = (
        second_brain_root / "Operations" / "Opportunities" / f"OPP-{opportunity_id}.md"
    ).read_text(encoding="utf-8")
    submission_note = (
        second_brain_root / "Operations" / "Submissions" / f"SUB-{submission_id}.md"
    ).read_text(encoding="utf-8")
    contact_note = (
        second_brain_root / "CRM" / "Contacts" / "aom-founder.md"
    ).read_text(encoding="utf-8")
    task_note = (
        second_brain_root / "Operations" / "Tasks" / f"TASK-{task_id}.md"
    ).read_text(encoding="utf-8")
    knowledge_note = (
        second_brain_root / "Knowledge" / "Playbooks" / f"playbook-{knowledge_id}.md"
    ).read_text(encoding="utf-8")

    assert "linkedin" in opportunity_note
    assert "Strong technical fit." in opportunity_note
    assert "Waiting for reply" in submission_note
    assert "Founder" in contact_note
    assert "2026-04-11T09:00:00+00:00" in task_note
    assert "Lead with delivery proof" in knowledge_note


def test_wire_event_handlers_registers_obsidian_automation_once():
    import app.agents.obsidian_sync as obsidian_sync_module

    event_bus.reset()
    wire_event_handlers()
    wire_event_handlers()

    assert (
        event_bus._handlers["opportunity.found"].count(
            obsidian_sync_module.obsidian_sync_agent.handle_opportunity_found
        )
        == 1
    )
    assert (
        event_bus._handlers["submission.sent"].count(
            obsidian_sync_module.obsidian_sync_agent.handle_submission_sent
        )
        == 1
    )
    assert (
        event_bus._handlers["contact.created"].count(
            obsidian_sync_module.obsidian_sync_agent.handle_contact_created
        )
        == 1
    )
    assert (
        event_bus._handlers["task.created"].count(
            obsidian_sync_module.obsidian_sync_agent.handle_task_created
        )
        == 1
    )
    assert (
        event_bus._handlers["knowledge.captured"].count(
            obsidian_sync_module.obsidian_sync_agent.handle_knowledge_captured
        )
        == 1
    )


@pytest.mark.asyncio
async def test_obsidian_api_exposes_bootstrap_and_context_capture_routes(
    async_client, monkeypatch
):
    monkeypatch.setattr(
        "app.api.obsidian.obsidian_sync_agent.bootstrap_second_brain",
        AsyncMock(
            return_value={
                "root_folder": "Second Brain",
                "project_count": 2,
                "skill_count": 6,
            }
        ),
    )
    monkeypatch.setattr(
        "app.api.obsidian.obsidian_sync_agent.capture_context",
        AsyncMock(return_value="Second Brain/Projects/testlyn/Contexts/ctx-note.md"),
    )

    bootstrap_response = await async_client.post("/obsidian/bootstrap")
    assert bootstrap_response.status_code == 200
    assert bootstrap_response.json()["project_count"] == 2

    context_response = await async_client.post(
        "/obsidian/context",
        json={
            "project_key": "Testlyn",
            "title": "Deployment decision",
            "summary": "Keep the hospital rollout feature-flagged for week one.",
            "details": "Roll out to one clinic before opening multi-site support.",
            "tags": ["deployment", "risk"],
            "source_url": "https://github.com/bravforcode/testlyn/pull/42",
            "metadata": {"kind": "decision"},
        },
    )
    assert context_response.status_code == 200
    assert context_response.json()["success"] is True
    assert "ctx-note.md" in context_response.json()["path"]
