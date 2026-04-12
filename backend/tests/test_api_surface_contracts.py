from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app.models.approval_request import ApprovalRequest
from app.models.automation_run import AutomationRun
from app.models.skill_profile import SkillProfile


@pytest_asyncio.fixture()
async def api_surface_session_factory(session_factory, monkeypatch):
    monkeypatch.setattr("app.core.control_plane.AsyncSessionLocal", session_factory)
    yield session_factory


@pytest.mark.asyncio
async def test_calendar_inbox_integrations_and_commands_routes_are_mounted(
    async_client, monkeypatch
):
    monkeypatch.setattr(
        "app.api.commands.execute_assistant_command",
        AsyncMock(return_value="System status"),
    )
    monkeypatch.setattr(
        "app.api.calendar.generate_today_calendar_overview",
        AsyncMock(
            return_value={
                "calendar": {"status": "ok", "configured": True, "events": []},
                "suggested_slots": [],
                "meeting_brief": None,
                "best_work_hours": "evening and weekend",
            }
        ),
    )
    monkeypatch.setattr(
        "app.api.inbox.generate_inbox_triage",
        AsyncMock(
            return_value={
                "source": {
                    "status": "ok",
                    "configured": True,
                    "messages": [],
                    "unread_count": 0,
                    "total_count": 0,
                },
                "triage": {"counts": {"action_needed": 0, "fyi": 0, "archive": 0}},
            }
        ),
    )
    monkeypatch.setattr(
        "app.core.google_workspace.google_workspace.health",
        AsyncMock(return_value={"status": "ok", "configured": True}),
    )
    monkeypatch.setattr(
        "app.core.google_workspace.google_workspace.get_gmail_inbox_summary",
        AsyncMock(
            return_value={
                "status": "ok",
                "configured": True,
                "messages": [],
                "unread_count": 0,
                "total_count": 0,
            }
        ),
    )
    monkeypatch.setattr(
        "app.core.google_workspace.google_workspace.get_calendar_day_summary",
        AsyncMock(
            return_value={
                "status": "ok",
                "configured": True,
                "date": "2026-04-09",
                "events": [],
            }
        ),
    )

    command_response = await async_client.post(
        "/api/v1/commands/execute",
        json={"text": "/status"},
    )
    assert command_response.status_code == 200
    assert command_response.json()["text"] == "System status"

    calendar_response = await async_client.get("/api/v1/calendar/today")
    assert calendar_response.status_code == 200
    assert calendar_response.json()["calendar"]["status"] == "ok"

    inbox_response = await async_client.get("/api/v1/inbox/triage")
    assert inbox_response.status_code == 200
    assert inbox_response.json()["source"]["configured"] is True

    health_response = await async_client.get("/api/v1/integrations/google/health")
    assert health_response.status_code == 200
    assert health_response.json()["status"] == "ok"

    gmail_response = await async_client.get("/api/v1/integrations/google/gmail/inbox-summary")
    assert gmail_response.status_code == 200
    assert gmail_response.json()["status"] == "ok"

    today_response = await async_client.get("/api/v1/integrations/google/calendar/today")
    assert today_response.status_code == 200
    assert today_response.json()["date"] == "2026-04-09"


@pytest.mark.asyncio
async def test_approvals_runs_and_skills_routes_are_mounted_and_work(
    async_client, db_session, monkeypatch, api_surface_session_factory
):
    now = datetime.now(timezone.utc)
    approval = ApprovalRequest(
        title="Approve application",
        action_type="job_apply_submit",
        subject_type="job_posting",
        status="pending",
        policy_class="high_impact_external",
        requested_by="jobs_api",
        details={"job_type": "freelance"},
        preview={"match_score": 82},
        batch_key="job_apply_submit:job_posting:jobs",
    )
    run = AutomationRun(
        name="Daily scan",
        task_type="daily_scan",
        trigger_source="scheduler",
        status="queued",
        context={"source": "test"},
        result={},
        queued_at=now,
        updated_at=now,
    )
    skill = SkillProfile(
        name="FastAPI",
        normalized_name="fastapi",
        category="technical",
        level="advanced",
        years_experience=Decimal("2.5"),
        aliases=["fastapi"],
        evidence=["client dashboard"],
        source="identity_profile",
        is_active=True,
    )
    db_session.add_all([approval, run, skill])
    await db_session.commit()

    monkeypatch.setattr(
        "app.api.skills.ensure_skill_profiles_seeded",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(
        "app.api.skills.bootstrap_skill_profiles",
        AsyncMock(return_value={"inserted": 0, "updated": 1, "total": 1}),
    )

    list_approvals_response = await async_client.get("/api/v1/approvals")
    assert list_approvals_response.status_code == 200
    assert list_approvals_response.json()["total"] == 1

    approval_detail_response = await async_client.get(f"/api/v1/approvals/{approval.id}")
    assert approval_detail_response.status_code == 200
    assert approval_detail_response.json()["title"] == "Approve application"

    approve_response = await async_client.patch(
        f"/api/v1/approvals/{approval.id}/approve",
        params={"note": "Ship it"},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"

    runs_response = await async_client.get("/api/v1/runs")
    assert runs_response.status_code == 200
    assert runs_response.json()["total"] == 1
    assert runs_response.json()["items"][0]["id"] == str(run.id)

    run_detail_response = await async_client.get(f"/api/v1/runs/{run.id}")
    assert run_detail_response.status_code == 200
    assert run_detail_response.json()["name"] == "Daily scan"

    skills_response = await async_client.get("/api/v1/skills")
    assert skills_response.status_code == 200
    assert skills_response.json()["total"] == 1
    assert skills_response.json()["items"][0]["normalized_name"] == "fastapi"

    bootstrap_response = await async_client.post("/api/v1/skills/bootstrap")
    assert bootstrap_response.status_code == 200
    assert bootstrap_response.json() == {"inserted": 0, "updated": 1, "total": 1}
