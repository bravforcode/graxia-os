from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest
from sqlalchemy import select
from app.api import auth as auth_api


def _confirmed_social_user(subject: str, email: str, name: str = "Social User") -> dict:
    return {
        "id": subject,
        "email": email,
        "email_confirmed_at": "2026-01-01T00:00:00Z",
        "app_metadata": {"provider": "google", "providers": ["google"]},
        "user_metadata": {"full_name": name},
    }


def _mock_social_identity(monkeypatch, claims: dict, canonical_user: dict):
    monkeypatch.setattr(auth_api.settings, "SUPABASE_JWT_SECRET", "offline-test-secret")
    monkeypatch.setattr(
        jwt,
        "decode",
        lambda *args, **kwargs: claims,
    )
    provider_lookup = AsyncMock(return_value=canonical_user)
    monkeypatch.setattr(auth_api, "_fetch_supabase_user", provider_lookup)
    return provider_lookup


@pytest.fixture(autouse=True)
def suppress_welcome_automation(monkeypatch):
    monkeypatch.setattr(
        "app.services.automation_email_service.AutomationEmailService.trigger_welcome",
        AsyncMock(),
    )


@pytest.mark.asyncio
async def test_login_me_and_refresh_contract_for_existing_password_account(
    public_async_client, db_session
):
    from app.core.auth import get_password_hash
    from app.models.organization import Organization
    from app.models.user import User

    organization = Organization(
        name="Existing Password Workspace",
        slug=f"existing-password-{uuid4().hex}",
    )
    user = User(
        id=uuid4(),
        email="operator@example.com",
        hashed_password=get_password_hash("correct-horse-battery"),
        full_name="System Operator",
        role="user",
        organization=organization,
    )
    db_session.add(user)
    await db_session.commit()

    login_response = await public_async_client.post(
        "/api/v1/auth/login",
        data={"username": "operator@example.com", "password": "correct-horse-battery"},
    )
    assert login_response.status_code == 200
    logged_in = login_response.json()
    assert logged_in["token_type"] == "bearer"
    assert logged_in["access_token"]
    assert logged_in["refresh_token"]
    assert logged_in["user"]["email"] == "operator@example.com"
    assert logged_in["user"]["role"] == "user"
    assert login_response.cookies.get("access_token")
    assert login_response.cookies.get("refresh_token")
    assert login_response.cookies.get("csrf_token")

    public_async_client.headers["X-CSRF-Token"] = login_response.cookies.get("csrf_token") or ""
    me_response = await public_async_client.get("/api/v1/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "operator@example.com"

    refresh_response = await public_async_client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 200
    refreshed = refresh_response.json()
    assert refreshed["token_type"] == "bearer"
    assert refreshed["access_token"]
    assert refreshed["refresh_token"]


@pytest.mark.asyncio
async def test_password_registration_is_stably_disabled_without_side_effects(
    public_async_client, db_session, monkeypatch
):
    from app.models.organization import Organization
    from app.models.user import User

    limiter_calls = []
    original_limiter = auth_api._check_rate_limit

    def track_rate_limit(identifier):
        limiter_calls.append(identifier)
        original_limiter(identifier)

    monkeypatch.setattr(auth_api, "_check_rate_limit", track_rate_limit)
    lookup = AsyncMock(side_effect=AssertionError("registration must not query users"))
    monkeypatch.setattr(auth_api, "_lookup_user_by_email", lookup)
    session_constructor = AsyncMock(side_effect=AssertionError("registration must not issue a session"))
    monkeypatch.setattr(auth_api, "SessionService", session_constructor)
    welcome_email = AsyncMock(side_effect=AssertionError("registration must not send email"))
    monkeypatch.setattr(
        "app.services.automation_email_service.AutomationEmailService.trigger_welcome",
        welcome_email,
    )

    users_before = set((await db_session.scalars(select(User.id))).all())
    organizations_before = set((await db_session.scalars(select(Organization.id))).all())
    responses = [
        await public_async_client.post(
            "/api/v1/auth/register",
            json={"email": "disabled@example.com", "password": "a-valid-long-password"},
        )
        for _ in range(2)
    ]

    assert [response.status_code for response in responses] == [403, 403]
    errors = [response.json()["error"] for response in responses]
    assert {error["code"] for error in errors} == {"PASSWORD_REGISTRATION_DISABLED"}
    assert len({error["message"] for error in errors}) == 1
    assert limiter_calls == ["register:disabled@example.com"] * 2
    lookup.assert_not_awaited()
    session_constructor.assert_not_awaited()
    welcome_email.assert_not_awaited()
    assert all(not response.cookies for response in responses)
    assert set((await db_session.scalars(select(User.id))).all()) == users_before
    assert set((await db_session.scalars(select(Organization.id))).all()) == organizations_before


async def _issue_social_invitation(db_session, organization_id, email: str) -> str:
    from app.models.user import User
    from app.services.invitation_service import issue_invitation

    owner = User(
        id=uuid4(),
        email=f"owner-{uuid4().hex}@example.com",
        hashed_password="offline-hash",
        organization_id=organization_id,
        role="owner",
        is_active=True,
    )
    db_session.add(owner)
    await db_session.commit()
    _, token = await issue_invitation(db_session, owner, email, "viewer")
    await db_session.commit()
    return token


@pytest.mark.asyncio
async def test_social_signup_requires_invitation_and_joins_inviting_organization(
    public_async_client, db_session, default_org, monkeypatch
):
    from app.models.user import User

    token_payloads = {}
    canonical_users = {}

    def decode_social_token(token, *args, **kwargs):
        return token_payloads[token]

    monkeypatch.setattr(jwt, "decode", decode_social_token)
    monkeypatch.setattr(auth_api.settings, "SUPABASE_JWT_SECRET", "offline-test-secret")
    provider_lookup = AsyncMock(side_effect=lambda token: canonical_users[token])
    monkeypatch.setattr(auth_api, "_fetch_supabase_user", provider_lookup)

    async def social_login(email, name, invite_token=None):
        token = f"offline-social-token-{uuid4().hex}"
        subject = f"social-{uuid4().hex}"
        token_payloads[token] = {
            "sub": subject,
            "email": "untrusted-token-email@example.invalid",
        }
        canonical_users[token] = _confirmed_social_user(subject, email, name)
        body = {"token": token, "provider": "google"}
        if invite_token is not None:
            body["invite_token"] = invite_token
        return await public_async_client.post("/api/v1/auth/social-login", json=body)

    uninvited_email = f"social_{uuid4().hex}@example.com"
    refused = await social_login(uninvited_email, "Uninvited Social User")
    assert refused.status_code == 403
    assert "INVITATION_REQUIRED" in refused.text
    assert await db_session.scalar(select(User).where(User.email == uninvited_email)) is None

    emails = [f"social_{uuid4().hex}@example.com" for _ in range(2)]
    invite_tokens = [
        await _issue_social_invitation(db_session, default_org.id, email) for email in emails
    ]
    responses = [
        await social_login(email, "Social User", invite_token=invite_token)
        for email, invite_token in zip(emails, invite_tokens)
    ]
    assert [response.status_code for response in responses] == [200, 200]

    users_result = await db_session.scalars(select(User).where(User.email.in_(emails)))
    users = {user.email: user for user in users_result.all()}
    assert set(users) == set(emails)
    assert {user.organization_id for user in users.values()} == {default_org.id}
    assert provider_lookup.await_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("subject_matches", [True, False])
async def test_social_signup_email_race_reuses_only_matching_subject(
    public_async_client, db_session, monkeypatch, subject_matches
):
    from app.models.organization import Organization
    from app.models.user import User

    subject = f"supabase-{uuid4().hex}"
    stored_subject = subject if subject_matches else f"other-{uuid4().hex}"
    email = f"social-race-{uuid4().hex}@example.com"
    organization = Organization(
        name="Concurrent Social Workspace",
        slug=f"concurrent-social-{uuid4().hex}",
    )
    db_session.add(organization)
    await db_session.flush()
    winner = User(
        id=uuid4(),
        email=email,
        hashed_password="test-hash",
        full_name="Concurrent Social User",
        organization_id=organization.id,
        provider="google",
        provider_id=stored_subject,
    )
    db_session.add(winner)
    await db_session.commit()
    organization_id = winner.organization_id
    _mock_social_identity(
        monkeypatch,
        {"sub": subject, "email": "untrusted-token-email@example.invalid"},
        _confirmed_social_user(subject, email),
    )
    organization_ids_before = set(
        (await db_session.scalars(select(Organization.id))).all()
    )
    response = await public_async_client.post(
        "/api/v1/auth/social-login",
        json={"token": "offline-social-token", "provider": "google"},
    )

    assert response.status_code == (200 if subject_matches else 409), response.text
    if not subject_matches:
        error = response.json()["error"]
        assert error["code"] == "SOCIAL_ACCOUNT_LINK_REQUIRED"
        assert error["message"] == "This social account is not linked to the account that owns this email."
    await db_session.refresh(winner)
    assert winner.organization_id == organization_id
    assert winner.provider == "google"
    assert winner.provider_id == stored_subject
    organization_ids_after = set(
        (await db_session.scalars(select(Organization.id))).all()
    )
    assert organization_ids_after == organization_ids_before


@pytest.mark.asyncio
@pytest.mark.parametrize("subject", [None, "", 123])
async def test_social_login_rejects_missing_or_invalid_subject_without_writes(
    public_async_client, db_session, monkeypatch, subject
):
    from app.models.organization import Organization
    from app.models.user import User

    claims = {"email": f"invalid-sub-{uuid4().hex}@example.com"}
    if subject is not None:
        claims["sub"] = subject
    monkeypatch.setattr(jwt, "decode", lambda *args, **kwargs: claims)
    provider_lookup = AsyncMock(
        side_effect=AssertionError("invalid subjects must be rejected before provider lookup")
    )
    monkeypatch.setattr(auth_api, "_fetch_supabase_user", provider_lookup)
    monkeypatch.setattr(auth_api.settings, "SUPABASE_JWT_SECRET", "offline-test-secret")

    users_before = set((await db_session.scalars(select(User.id))).all())
    organizations_before = set(
        (await db_session.scalars(select(Organization.id))).all()
    )
    response = await public_async_client.post(
        "/api/v1/auth/social-login",
        json={"token": "offline-social-token", "provider": "google"},
    )

    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "AUTH_INVALID"
    assert error["message"] == "Authentication required"
    assert set((await db_session.scalars(select(User.id))).all()) == users_before
    assert set(
        (await db_session.scalars(select(Organization.id))).all()
    ) == organizations_before
    provider_lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_social_login_accepts_existing_user_only_for_matching_subject(
    public_async_client, db_session, monkeypatch
):
    from app.models.organization import Organization
    from app.models.user import User

    subject = f"supabase-{uuid4().hex}"
    email = f"social-match-{uuid4().hex}@example.com"
    organization = Organization(
        name="Existing Social Workspace",
        slug=f"existing-social-{uuid4().hex}",
    )
    db_session.add(organization)
    await db_session.flush()
    existing_user = User(
        id=uuid4(),
        email=email,
        hashed_password="test-hash",
        full_name="Existing Social User",
        organization_id=organization.id,
        provider="google",
        provider_id=subject,
        avatar_url="https://example.com/existing-avatar.png",
    )
    db_session.add(existing_user)
    await db_session.commit()
    user_id = existing_user.id
    organization_id = existing_user.organization_id
    canonical_email = f"social-match-updated-{uuid4().hex}@example.com"

    _mock_social_identity(
        monkeypatch,
        {
            "sub": subject,
            "email": "untrusted-token-email@example.invalid",
            "user_metadata": {"avatar_url": "https://example.com/attacker-avatar.png"},
        },
        {
            **_confirmed_social_user(subject, canonical_email, "Provider Supplied Name"),
            "user_metadata": {
                "full_name": "Provider Supplied Name",
                "avatar_url": "https://example.com/other-avatar.png",
            },
        },
    )
    response = await public_async_client.post(
        "/api/v1/auth/social-login",
        json={"token": "offline-social-token", "provider": "google"},
    )

    assert response.status_code == 200, response.text
    await db_session.refresh(existing_user)
    assert existing_user.email == canonical_email
    assert existing_user.id == user_id
    assert existing_user.organization_id == organization_id
    assert existing_user.provider == "google"
    assert existing_user.provider_id == subject
    assert existing_user.avatar_url == "https://example.com/existing-avatar.png"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stored_provider", "stored_subject"),
    [("google", "different-subject"), (None, None)],
)
async def test_social_login_rejects_unbound_email_without_mutation(
    public_async_client, db_session, monkeypatch, stored_provider, stored_subject
):
    from app.models.organization import Organization
    from app.models.user import User

    subject = f"supabase-{uuid4().hex}"
    email = f"social-unbound-{uuid4().hex}@example.com"
    organization = Organization(
        name="Existing Account Workspace",
        slug=f"existing-account-{uuid4().hex}",
    )
    db_session.add(organization)
    await db_session.flush()
    existing_user = User(
        id=uuid4(),
        email=email,
        hashed_password="test-hash",
        full_name="Existing Account User",
        organization_id=organization.id,
        provider=stored_provider,
        provider_id=stored_subject,
        avatar_url="https://example.com/original-avatar.png",
    )
    db_session.add(existing_user)
    await db_session.commit()
    original_state = (
        existing_user.organization_id,
        existing_user.provider,
        existing_user.provider_id,
        existing_user.avatar_url,
        existing_user.last_login_at,
        existing_user.full_name,
    )

    _mock_social_identity(
        monkeypatch,
        {
            "sub": subject,
            "email": email,
            "user_metadata": {
                "full_name": "Caller Supplied Name",
                "avatar_url": "https://example.com/attacker-avatar.png",
            },
        },
        _confirmed_social_user(subject, email, "Provider Supplied Name"),
    )
    response = await public_async_client.post(
        "/api/v1/auth/social-login",
        json={"token": "offline-social-token", "provider": "google"},
    )

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "SOCIAL_ACCOUNT_LINK_REQUIRED"
    assert error["message"] == "This social account is not linked to the account that owns this email."
    await db_session.refresh(existing_user)
    assert (
        existing_user.organization_id,
        existing_user.provider,
        existing_user.provider_id,
        existing_user.avatar_url,
        existing_user.last_login_at,
        existing_user.full_name,
    ) == original_state


@pytest.mark.asyncio
async def test_login_rejects_invalid_credentials(public_async_client):
    response = await public_async_client.post(
        "/api/v1/auth/login",
        data={"username": "login@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"
    assert response.json()["error"]["message"] == "Authentication required"


@pytest.mark.asyncio
async def test_register_returns_disabled_even_if_database_lookup_would_fail(
    public_async_client, monkeypatch
):
    monkeypatch.setattr(
        "app.api.auth._lookup_user_by_email",
        AsyncMock(side_effect=PermissionError("database connect blocked")),
    )

    response = await public_async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "db-down@example.com",
            "password": "correct-horse-battery",
            "full_name": "DB Down",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PASSWORD_REGISTRATION_DISABLED"


@pytest.mark.asyncio
async def test_social_login_returns_503_when_database_is_unavailable(
    public_async_client, monkeypatch
):
    monkeypatch.setattr(
        auth_api.settings, "SUPABASE_JWT_SECRET", "social-test-secret", raising=False
    )
    monkeypatch.setattr(
        jwt,
        "decode",
        lambda *args, **kwargs: {
            "sub": "supabase-user-id",
            "email": "social-db-down@example.com",
            "user_metadata": {
                "full_name": "Social DB Down",
                "avatar_url": "https://example.com/avatar.png",
            },
        },
    )
    _mock_social_identity(
        monkeypatch,
        {
            "sub": "supabase-user-id",
            "email": "untrusted-token-email@example.invalid",
        },
        _confirmed_social_user("supabase-user-id", "social-db-down@example.com"),
    )
    monkeypatch.setattr(
        "app.api.auth._lookup_user_by_provider_id",
        AsyncMock(side_effect=PermissionError("database connect blocked")),
    )
    response = await public_async_client.post(
        "/api/v1/auth/social-login",
        json={
            "token": jwt.encode({"sub": "unused"}, "social-test-secret", algorithm="HS256"),
            "provider": "google",
        },
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert response.json()["error"]["message"] == "Internal server error"
