import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

from app.config import settings
from app.core.auth import get_password_hash
from app.middleware.auth import AuthLevel, classify_route, role_satisfies
from app.models.invitation import Invitation
from app.models.organization import Organization
from app.models.user import User
from app.services.invitation_service import (
    consume_invitation,
    issue_invitation,
    revoke_invitation,
)
from app.services.session_service import (
    SessionService,
    _memory_sessions,
    reset_session_service_state,
)


def test_unclassified_route_is_denied_by_default():
    assert classify_route("GET", "/unlisted/path") == AuthLevel.BLOCKED


@pytest.mark.parametrize("role", ["user", "operator", "owner", "admin"])
def test_writer_roles_pass_authenticated_routes(role):
    assert role_satisfies(AuthLevel.AUTHENTICATED, role, safe_method=False)


def test_viewer_is_read_only_on_authenticated_routes():
    assert role_satisfies(AuthLevel.AUTHENTICATED, "viewer", safe_method=True)
    assert not role_satisfies(AuthLevel.AUTHENTICATED, "viewer", safe_method=False)


@pytest.mark.parametrize("role", ["", "guest"])
def test_unknown_role_is_denied(role):
    assert not role_satisfies(AuthLevel.AUTHENTICATED, role, safe_method=True)


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/v1/auth/invitations"),
        ("DELETE", "/api/v1/auth/invitations/{invitation_id}"),
    ],
)
def test_invitation_routes_require_owner_or_admin(method, path):
    assert classify_route(method, path) == AuthLevel.ADMIN
    assert not role_satisfies(AuthLevel.ADMIN, "operator")
    assert not role_satisfies(AuthLevel.ADMIN, "viewer")
    assert role_satisfies(AuthLevel.ADMIN, "owner")
    assert role_satisfies(AuthLevel.ADMIN, "admin")


def test_every_mounted_route_has_an_explicit_classification():
    from app.main import app

    unclassified = [
        f"{method} {route.path}"
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods - {"HEAD", "OPTIONS"}
        if classify_route(method, route.path) == AuthLevel.BLOCKED
    ]
    assert unclassified == []


@pytest.mark.asyncio
async def test_idle_session_expires_and_is_revoked():
    reset_session_service_state()
    service = SessionService(None)
    session = await service.create_session(
        user_id=str(uuid4()), device_id="device", ip_address="127.0.0.1", user_agent="test"
    )
    _memory_sessions[session.session_id].last_seen = time.time() - settings.SESSION_IDLE_TIMEOUT_HOURS * 3600 - 1

    assert not await service.is_session_active(session.session_id)
    assert (await service.get_session(session.session_id)).revoked


@pytest.mark.asyncio
async def test_absolute_session_lifetime_expires_even_when_active():
    reset_session_service_state()
    service = SessionService(None)
    session = await service.create_session(
        user_id=str(uuid4()), device_id="device", ip_address="127.0.0.1", user_agent="test"
    )
    _memory_sessions[session.session_id].created_at = (
        time.time() - settings.SESSION_ABSOLUTE_TIMEOUT_DAYS * 86400 - 1
    )

    assert not await service.is_session_active(session.session_id)


@pytest.mark.asyncio
async def test_active_session_refreshes_last_seen_and_revoked_session_is_refused():
    reset_session_service_state()
    service = SessionService(None)
    session = await service.create_session(
        user_id=str(uuid4()), device_id="device", ip_address="127.0.0.1", user_agent="test"
    )
    _memory_sessions[session.session_id].last_seen = time.time() - 60

    assert await service.is_session_active(session.session_id)
    assert time.time() - _memory_sessions[session.session_id].last_seen < 5

    await service.invalidate_all_user_sessions(session.user_id, reason="test")
    assert not await service.is_session_active(session.session_id)


async def _make_user(db_session, organization_id, role: str) -> User:
    user = User(
        id=uuid4(),
        email=f"{role}-{uuid4()}@example.com",
        hashed_password=get_password_hash("testpassword123"),
        full_name=role.title(),
        role=role,
        is_active=True,
        organization_id=organization_id,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture()
async def owner(db_session, default_org) -> User:
    return await _make_user(db_session, default_org.id, "owner")


@pytest.mark.asyncio
async def test_operator_cannot_issue_invitations(db_session, default_org):
    operator = await _make_user(db_session, default_org.id, "operator")

    with pytest.raises(HTTPException) as exc:
        await issue_invitation(db_session, operator, "invitee@example.com", "viewer")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_invitation_is_bound_to_email_and_single_use(db_session, owner):
    _, token = await issue_invitation(db_session, owner, "Invitee@Example.com", "viewer")
    await db_session.commit()

    with pytest.raises(HTTPException) as wrong_email:
        await consume_invitation(db_session, token, "other@example.com")
    assert wrong_email.value.status_code == 403

    consumed = await consume_invitation(db_session, token, "invitee@example.com")
    await db_session.commit()
    assert consumed.role == "viewer"
    assert consumed.organization_id == owner.organization_id

    with pytest.raises(HTTPException) as reused:
        await consume_invitation(db_session, token, "invitee@example.com")
    assert reused.value.status_code == 403


@pytest.mark.asyncio
async def test_expired_invitation_is_refused(db_session, owner):
    invitation, token = await issue_invitation(db_session, owner, "late@example.com", "operator")
    await db_session.execute(
        update(Invitation)
        .where(Invitation.id == invitation.id)
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await consume_invitation(db_session, token, "late@example.com")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_revoked_invitation_is_refused(db_session, owner):
    invitation, token = await issue_invitation(db_session, owner, "revoked@example.com", "viewer")
    await db_session.commit()
    await revoke_invitation(db_session, owner, invitation.id)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await consume_invitation(db_session, token, "revoked@example.com")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_invitation_is_refused_when_organization_is_suspended(db_session, owner, default_org):
    _, token = await issue_invitation(db_session, owner, "blocked@example.com", "viewer")
    await db_session.execute(
        update(Organization).where(Organization.id == default_org.id).values(status="suspended")
    )
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await consume_invitation(db_session, token, "blocked@example.com")
    assert exc.value.status_code == 403


async def _client_for_app() -> AsyncClient:
    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


@pytest.mark.asyncio
async def test_registration_requires_an_invitation_and_grants_the_invited_role(async_client):
    invitee_email = f"invitee-{uuid4()}@example.com"

    refused = await async_client.post(
        "/api/v1/auth/register",
        json={"email": invitee_email, "password": "a-long-password-1"},
    )
    assert refused.status_code == 403
    assert "PASSWORD_REGISTRATION_DISABLED" in refused.text

    issued = await async_client.post(
        "/api/v1/auth/invitations", json={"email": invitee_email, "role": "operator"}
    )
    assert issued.status_code == 201
    token = issued.json()["invite_token"]

    async with await _client_for_app() as invitee:
        registered = await invitee.post(
            "/api/v1/auth/register",
            json={
                "email": invitee_email,
                "password": "a-long-password-1",
                "invite_token": token,
            },
        )
        assert registered.status_code == 201
        assert registered.json()["user"]["role"] == "operator"

        reused = await invitee.post(
            "/api/v1/auth/register",
            json={
                "email": invitee_email,
                "password": "a-long-password-1",
                "invite_token": token,
            },
        )
        assert reused.status_code in (400, 403)


@pytest.mark.asyncio
async def test_operator_is_refused_invitation_routes_end_to_end(async_client):
    invitee_email = f"operator-{uuid4()}@example.com"
    issued = await async_client.post(
        "/api/v1/auth/invitations", json={"email": invitee_email, "role": "operator"}
    )
    token = issued.json()["invite_token"]

    async with await _client_for_app() as operator:
        await operator.post(
            "/api/v1/auth/register",
            json={"email": invitee_email, "password": "a-long-password-1", "invite_token": token},
        )
        csrf = {"X-CSRF-Token": operator.cookies.get(settings.CSRF_COOKIE_NAME, "")}

        attempt = await operator.post(
            "/api/v1/auth/invitations",
            json={"email": f"third-{uuid4()}@example.com", "role": "viewer"},
            headers=csrf,
        )
        assert attempt.status_code == 403
        assert attempt.json()["detail"] == "Forbidden"


@pytest.mark.asyncio
async def test_viewer_reads_but_cannot_write_end_to_end(async_client):
    invitee_email = f"viewer-{uuid4()}@example.com"
    issued = await async_client.post(
        "/api/v1/auth/invitations", json={"email": invitee_email, "role": "viewer"}
    )
    token = issued.json()["invite_token"]

    async with await _client_for_app() as viewer:
        await viewer.post(
            "/api/v1/auth/register",
            json={"email": invitee_email, "password": "a-long-password-1", "invite_token": token},
        )
        csrf = {"X-CSRF-Token": viewer.cookies.get(settings.CSRF_COOKIE_NAME, "")}

        read = await viewer.get("/api/v1/auth/me")
        assert read.status_code == 200

        write = await viewer.post(
            "/api/v1/auth/change-password",
            json={"current_password": "a-long-password-1", "new_password": "another-long-password-2"},
            headers=csrf,
        )
        assert write.status_code == 403
        assert write.json()["detail"] == "Forbidden"


@pytest.mark.asyncio
async def test_internal_routes_refuse_requests_without_internal_key(public_async_client):
    response = await public_async_client.get("/internal/queue-status")
    assert response.status_code in (401, 403, 422)
