import hashlib
import secrets
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.auth import decode_access_token, extract_bearer_token
from app.main import app as fastapi_app
from app.models.approval_request import ApprovalRequest
from app.models.automation_run import AutomationRun
from app.models.funnel import DeliveryAccess, DeliveryAsset, DigitalProduct, FunnelOrder
from app.models.skill_profile import SkillProfile
from app.models.user import User


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
    now = datetime.now(UTC)
    token = extract_bearer_token(async_client.headers.get("Authorization"))
    assert token is not None
    organization_id = UUID(decode_access_token(token)["organization_id"])
    approval = ApprovalRequest(
        organization_id=organization_id,
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

    duplicate_approve_response = await async_client.patch(
        f"/api/v1/approvals/{approval.id}/approve",
        params={"note": "Double click"},
    )
    assert duplicate_approve_response.status_code == 409
    duplicate_approve_payload = duplicate_approve_response.json()
    assert duplicate_approve_payload["error"]["code"] == "CONFLICT"
    assert duplicate_approve_payload["error"]["message"] == "Approval already processed"

    reject_after_approve_response = await async_client.patch(
        f"/api/v1/approvals/{approval.id}/reject",
        params={"note": "Changed mind"},
    )
    assert reject_after_approve_response.status_code == 409
    reject_after_approve_payload = reject_after_approve_response.json()
    assert reject_after_approve_payload["error"]["code"] == "CONFLICT"
    assert reject_after_approve_payload["error"]["message"] == "Approval already processed"

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


@pytest.mark.asyncio
async def test_delivery_opened_persists_open_state(
    public_async_client, db_session, default_org
):
    raw_token = secrets.token_urlsafe(32)
    organization_id = default_org.id
    product = DigitalProduct(
        id=uuid4(),
        organization_id=organization_id,
        name="Delivery Product",
        slug=f"delivery-product-{uuid4()}",
        price_amount=Decimal("10.00"),
        currency="THB",
        status="published",
    )
    asset = DeliveryAsset(
        id=uuid4(),
        organization_id=organization_id,
        product_id=product.id,
        title="Delivery Asset",
        asset_type="text",
        content_body="customer payload",
        is_active=True,
    )
    order = FunnelOrder(
        id=uuid4(),
        organization_id=organization_id,
        status="paid",
        subtotal_amount=Decimal("10.00"),
        total_amount=Decimal("10.00"),
        currency="THB",
    )
    access = DeliveryAccess(
        id=uuid4(),
        organization_id=organization_id,
        order_id=order.id,
        product_id=product.id,
        asset_id=asset.id,
        access_token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        status="active",
        max_downloads=10,
        download_count=0,
        open_count=0,
    )
    db_session.add_all([product, asset, order, access])
    await db_session.commit()

    response = await public_async_client.post(
        "/api/v1/funnel/events/delivery-opened",
        params={"access_token": raw_token},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "tracked", "access_id": str(access.id)}
    await db_session.refresh(access)
    assert access.open_count == 1
    assert access.first_opened_at is not None
    assert access.last_opened_at is not None
    assert access.download_count == 1


@pytest.mark.asyncio
async def test_gdpr_export_requires_auth_and_audits_tenant_session(
    async_client, public_async_client, monkeypatch
):
    audit = AsyncMock()
    monkeypatch.setattr("app.api.auth.log_audit_event", audit)

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as anonymous_client:
        unauthenticated = await anonymous_client.get("/api/v1/auth/me/export")
    assert unauthenticated.status_code in (401, 403)

    token = extract_bearer_token(async_client.headers.get("Authorization"))
    assert token is not None
    payload = decode_access_token(token)

    response = await async_client.get("/api/v1/auth/me/export")

    assert response.status_code == 200
    exported = response.json()
    assert exported["export_metadata"]["user_id"] == payload["sub"]
    assert exported["organization"]["organization_id"] == payload["organization_id"]
    audit.assert_awaited_once()
    audit_kwargs = audit.await_args.kwargs
    assert audit_kwargs["action"] == "auth.data_export"
    assert audit_kwargs["user_id"] == payload["sub"]
    assert audit_kwargs["session_id"] == payload["session_id"]


@pytest.mark.asyncio
async def test_gdpr_delete_soft_deletes_revokes_sessions_and_audits(
    async_client, db_session, monkeypatch
):
    audit = AsyncMock()
    invalidate_all = AsyncMock()
    monkeypatch.setattr("app.api.auth.log_audit_event", audit)
    monkeypatch.setattr(
        "app.api.auth.SessionService.invalidate_all_user_sessions",
        invalidate_all,
    )
    token = extract_bearer_token(async_client.headers.get("Authorization"))
    assert token is not None
    payload = decode_access_token(token)
    user_id = UUID(payload["sub"])

    response = await async_client.delete("/api/v1/auth/me")

    assert response.status_code == 204
    stored_user = await db_session.scalar(select(User).where(User.id == user_id))
    assert stored_user is not None
    assert stored_user.is_active is False
    assert stored_user.email == f"deleted-{user_id}@deleted.graxia.io"
    invalidate_all.assert_awaited_once_with(str(user_id), reason="account_deleted")
    audit.assert_awaited_once()
    audit_kwargs = audit.await_args.kwargs
    assert audit_kwargs["action"] == "auth.account_delete"
    assert audit_kwargs["user_id"] == str(user_id)
    assert audit_kwargs["session_id"] == payload["session_id"]
