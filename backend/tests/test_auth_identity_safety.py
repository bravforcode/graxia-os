"""Offline identity and migration contracts for social authentication."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import jwt
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError

from app.api import auth as auth_api
from app.core.errors import AppError


def _canonical_user(subject: str, email: str) -> dict:
    return {
        "id": subject,
        "email": email,
        "email_confirmed_at": "2026-01-01T00:00:00Z",
        "app_metadata": {"provider": "google", "providers": ["google"]},
        "user_metadata": {"full_name": "Verified Person"},
    }


def _mock_social(
    monkeypatch,
    *,
    subject: str,
    canonical_user: dict,
) -> AsyncMock:
    monkeypatch.setattr(auth_api.settings, "SUPABASE_JWT_SECRET", "offline-test-secret")
    monkeypatch.setattr(
        jwt,
        "decode",
        lambda *args, **kwargs: {
            "sub": subject,
            "email": "untrusted-token-email@example.invalid",
            "user_metadata": {"full_name": "Untrusted Name"},
        },
    )
    provider_lookup = AsyncMock(return_value=canonical_user)
    monkeypatch.setattr(auth_api, "_fetch_supabase_user", provider_lookup)
    return provider_lookup


def _load_provider_id_migration():
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "025_unique_social_provider_subject.py"
    )
    spec = importlib.util.spec_from_file_location(
        "migration_025_unique_social_provider_subject", migration_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("canonical_user", "expected_status", "expected_code"),
    [
        (
            {"id": "different-subject", **_canonical_user("different-subject", "person@example.com")},
            401,
            "AUTH_INVALID",
        ),
        (
            {
                **_canonical_user("supabase-subject", "person@example.com"),
                "email_confirmed_at": None,
            },
            403,
            "SOCIAL_EMAIL_UNVERIFIED",
        ),
    ],
)
async def test_social_login_rejects_unverified_canonical_identity_before_database(
    public_async_client,
    db_session,
    monkeypatch,
    canonical_user,
    expected_status,
    expected_code,
):
    from app.models.organization import Organization
    from app.models.user import User

    provider_lookup = _mock_social(
        monkeypatch,
        subject="supabase-subject",
        canonical_user=canonical_user,
    )
    user_lookup = AsyncMock(
        side_effect=AssertionError("identity rejection must precede database lookup")
    )
    monkeypatch.setattr(auth_api, "_lookup_user_by_provider_id", user_lookup)

    users_before = set((await db_session.scalars(select(User.id))).all())
    organizations_before = set(
        (await db_session.scalars(select(Organization.id))).all()
    )
    response = await public_async_client.post(
        "/api/v1/auth/social-login",
        json={"token": "offline-token", "provider": "google"},
    )

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
    provider_lookup.assert_awaited_once_with("offline-token")
    user_lookup.assert_not_awaited()
    assert set((await db_session.scalars(select(User.id))).all()) == users_before
    assert set(
        (await db_session.scalars(select(Organization.id))).all()
    ) == organizations_before
    assert not response.cookies


@pytest.mark.asyncio
async def test_social_provider_failure_is_fail_closed_before_database(
    public_async_client, db_session, monkeypatch
):
    from app.models.organization import Organization
    from app.models.user import User

    monkeypatch.setattr(auth_api.settings, "SUPABASE_JWT_SECRET", "offline-test-secret")
    monkeypatch.setattr(
        jwt, "decode", lambda *args, **kwargs: {"sub": "supabase-subject"}
    )
    provider_lookup = AsyncMock(
        side_effect=AppError(
            "SOCIAL_AUTH_UNAVAILABLE", "Social sign-in is temporarily unavailable.", 503
        )
    )
    monkeypatch.setattr(auth_api, "_fetch_supabase_user", provider_lookup)
    user_lookup = AsyncMock(
        side_effect=AssertionError("provider failure must precede database lookup")
    )
    monkeypatch.setattr(auth_api, "_lookup_user_by_provider_id", user_lookup)

    users_before = set((await db_session.scalars(select(User.id))).all())
    organizations_before = set(
        (await db_session.scalars(select(Organization.id))).all()
    )
    response = await public_async_client.post(
        "/api/v1/auth/social-login",
        json={"token": "offline-token", "provider": "google"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SOCIAL_AUTH_UNAVAILABLE"
    provider_lookup.assert_awaited_once_with("offline-token")
    user_lookup.assert_not_awaited()
    assert set((await db_session.scalars(select(User.id))).all()) == users_before
    assert set(
        (await db_session.scalars(select(Organization.id))).all()
    ) == organizations_before
    assert not response.cookies


@pytest.mark.asyncio
async def test_supabase_user_lookup_uses_mock_transport_and_project_endpoint(monkeypatch):
    requests = []
    expected_user = _canonical_user("supabase-subject", "person@example.com")
    transport = httpx.MockTransport(
        lambda request: (
            requests.append(request)
            or httpx.Response(200, json=expected_user)
        )
    )
    real_async_client = httpx.AsyncClient

    def mock_client(*, timeout, follow_redirects):
        return real_async_client(
            transport=transport,
            timeout=timeout,
            follow_redirects=follow_redirects,
        )

    monkeypatch.setattr(auth_api.settings, "SUPABASE_URL", "https://project.example")
    monkeypatch.setattr(auth_api.settings, "SUPABASE_ANON_KEY", "offline-anon-key")
    monkeypatch.setattr(auth_api.httpx, "AsyncClient", mock_client)

    actual_user = await auth_api._fetch_supabase_user("offline-bearer-token")

    assert actual_user == expected_user
    assert len(requests) == 1
    assert str(requests[0].url) == "https://project.example/auth/v1/user"
    assert requests[0].headers["authorization"] == "Bearer offline-bearer-token"
    assert requests[0].headers["apikey"] == "offline-anon-key"


@pytest.mark.asyncio
async def test_social_email_collision_does_not_merge_or_mutate_tenants(
    public_async_client, db_session, monkeypatch
):
    from app.models.organization import Organization
    from app.models.user import User

    original_email = f"original-{uuid4().hex}@example.com"
    shared_email = f"shared-{uuid4().hex}@example.com"
    subject_user = User(
        id=uuid4(),
        email=original_email,
        hashed_password="offline-hash",
        organization=Organization(
            name="Subject Tenant", slug=f"subject-tenant-{uuid4().hex}"
        ),
        provider="google",
        provider_id="supabase-subject",
    )
    email_owner = User(
        id=uuid4(),
        email=shared_email,
        hashed_password="offline-hash",
        organization=Organization(
            name="Email Tenant", slug=f"email-tenant-{uuid4().hex}"
        ),
        provider="google",
        provider_id="other-subject",
    )
    db_session.add_all([subject_user, email_owner])
    await db_session.commit()
    original_state = (
        subject_user.email,
        subject_user.organization_id,
        email_owner.email,
        email_owner.organization_id,
    )
    _mock_social(
        monkeypatch,
        subject="supabase-subject",
        canonical_user=_canonical_user("supabase-subject", shared_email.upper()),
    )

    response = await public_async_client.post(
        "/api/v1/auth/social-login",
        json={"token": "offline-token", "provider": "google"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SOCIAL_ACCOUNT_LINK_REQUIRED"
    await db_session.refresh(subject_user)
    await db_session.refresh(email_owner)
    assert (
        subject_user.email,
        subject_user.organization_id,
        email_owner.email,
        email_owner.organization_id,
    ) == original_state
    assert not response.cookies


@pytest.mark.asyncio
async def test_email_owner_race_during_subject_email_update_returns_conflict(
    public_async_client, db_session, monkeypatch
):
    from app.models.organization import Organization
    from app.models.user import User

    canonical_email = f"race-collision-{uuid4().hex}@example.com"
    subject_user = User(
        id=uuid4(),
        email=f"old-{uuid4().hex}@example.com",
        hashed_password="offline-hash",
        organization=Organization(
            name="Subject Tenant", slug=f"race-subject-tenant-{uuid4().hex}"
        ),
        provider="google",
        provider_id="supabase-subject",
    )
    email_owner = User(
        id=uuid4(),
        email=canonical_email,
        hashed_password="offline-hash",
        organization=Organization(
            name="Email Tenant", slug=f"race-email-tenant-{uuid4().hex}"
        ),
        provider="google",
        provider_id="other-subject",
    )
    db_session.add_all([subject_user, email_owner])
    await db_session.commit()
    original_state = (subject_user.email, subject_user.organization_id)
    original_lookup = auth_api._lookup_users_by_canonical_email
    lookup_count = 0

    async def simulate_stale_email_precheck(db, email):
        nonlocal lookup_count
        lookup_count += 1
        if lookup_count == 1:
            return []
        return await original_lookup(db, email)

    monkeypatch.setattr(
        auth_api, "_lookup_users_by_canonical_email", simulate_stale_email_precheck
    )
    _mock_social(
        monkeypatch,
        subject="supabase-subject",
        canonical_user=_canonical_user("supabase-subject", canonical_email.upper()),
    )

    response = await public_async_client.post(
        "/api/v1/auth/social-login",
        json={"token": "offline-token", "provider": "google"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SOCIAL_ACCOUNT_LINK_REQUIRED"
    await db_session.refresh(subject_user)
    assert (subject_user.email, subject_user.organization_id) == original_state
    assert not response.cookies
    assert lookup_count == 2


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
async def test_concurrent_social_signup_reuses_subject_winner_and_existing_tenant(
    public_async_client, db_session, monkeypatch
):
    from app.main import app
    from app.models.organization import Organization
    from app.models.user import User

    subject = f"supabase-race-{uuid4().hex}"
    email = f"race-{uuid4().hex}@example.com"
    winner = User(
        id=uuid4(),
        email=email,
        hashed_password="offline-hash",
        organization=Organization(
            name="Race Winner Tenant", slug=f"race-winner-{uuid4().hex}"
        ),
        provider="google",
        provider_id=subject,
    )
    db_session.add(winner)
    await db_session.commit()
    user_id = winner.id
    organization_id = winner.organization_id
    _mock_social(
        monkeypatch,
        subject=subject,
        canonical_user=_canonical_user(subject, email),
    )
    invite_token = await _issue_social_invitation(db_session, organization_id, email)

    subject_lookup_count = 0
    email_lookup_count = 0

    async def hide_first_subject_read(db, requested_subject):
        nonlocal subject_lookup_count
        subject_lookup_count += 1
        if subject_lookup_count == 1:
            return None
        await db.refresh(winner)
        return winner

    async def hide_first_email_read(db, requested_email):
        nonlocal email_lookup_count
        email_lookup_count += 1
        if email_lookup_count == 1:
            return []
        return [winner]

    monkeypatch.setattr(auth_api, "_lookup_user_by_provider_id", hide_first_subject_read)
    monkeypatch.setattr(
        auth_api, "_lookup_users_by_canonical_email", hide_first_email_read
    )

    previous_override = app.dependency_overrides.get(auth_api.get_db)

    async def use_test_session():
        yield db_session

    app.dependency_overrides[auth_api.get_db] = use_test_session
    try:
        response = await public_async_client.post(
            "/api/v1/auth/social-login",
            json={
                "token": "offline-token",
                "provider": "google",
                "invite_token": invite_token,
            },
        )
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(auth_api.get_db, None)
        else:
            app.dependency_overrides[auth_api.get_db] = previous_override

    assert response.status_code == 200, response.text
    assert subject_lookup_count == 2
    assert email_lookup_count == 2
    await db_session.refresh(winner)
    assert winner.id == user_id
    assert winner.organization_id == organization_id
    assert winner.email == email
    assert len(
        list((await db_session.scalars(select(User).where(User.provider_id == subject))).all())
    ) == 1
    organizations = await db_session.scalars(select(Organization.id))
    assert set(organizations.all()) == {organization_id}


@pytest.mark.asyncio
async def test_user_model_unique_provider_subject_allows_nulls_but_rejects_duplicates(
    db_session,
):
    from app.models.organization import Organization
    from app.models.user import User

    organization = Organization(
        name="Identity Index Tenant", slug=f"identity-index-{uuid4().hex}"
    )
    db_session.add_all(
        [
            User(
                id=uuid4(),
                email="null-one@example.com",
                hashed_password="offline",
                organization=organization,
            ),
            User(
                id=uuid4(),
                email="null-two@example.com",
                hashed_password="offline",
                organization=organization,
            ),
        ]
    )
    await db_session.commit()
    db_session.add_all(
        [
            User(
                id=uuid4(),
                email="subject-one@example.com",
                hashed_password="offline",
                provider_id="same-subject",
                organization=organization,
            ),
            User(
                id=uuid4(),
                email="subject-two@example.com",
                hashed_password="offline",
                provider_id="same-subject",
                organization=organization,
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


def test_provider_subject_migration_preflights_duplicate_data_without_repair():
    migration = _load_provider_id_migration()
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, provider_id TEXT NULL)"))
        connection.execute(
            text("INSERT INTO users(provider_id) VALUES (:value), (:value)"),
            {"value": "duplicate-subject"},
        )

        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError, match="duplicate provider_id"):
                migration.upgrade()

        rows = connection.execute(
            text("SELECT provider_id FROM users ORDER BY id")
        ).fetchall()
        indexes = connection.execute(text("PRAGMA index_list(users)")).fetchall()

    assert rows == [("duplicate-subject",), ("duplicate-subject",)]
    assert indexes == []


def test_provider_subject_migration_creates_unique_non_null_index():
    migration = _load_provider_id_migration()
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, provider_id TEXT NULL)"))
        connection.execute(
            text("INSERT INTO users(provider_id) VALUES (NULL), (NULL), (:value)"),
            {"value": "unique-subject"},
        )

        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        connection.execute(text("INSERT INTO users(provider_id) VALUES (NULL)"))
        assert connection.execute(
            text("PRAGMA index_list(users)")
        ).fetchall()

    with engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(
                text("INSERT INTO users(provider_id) VALUES (:value)"),
                {"value": "unique-subject"},
            )


@pytest.mark.asyncio
async def test_password_login_rejects_social_account_even_with_dummy_password(
    public_async_client, db_session
):
    from app.models.organization import Organization
    from app.models.user import User

    organization = Organization(
        name="Social Password Guard",
        slug=f"social-password-guard-{uuid4().hex}",
    )
    db_session.add(organization)
    await db_session.flush()
    user = User(
        id=uuid4(),
        email=f"social-login-{uuid4().hex}@example.com",
        hashed_password=auth_api.DUMMY_PASSWORD_HASH,
        organization_id=organization.id,
        provider="google",
        provider_id=f"supabase-{uuid4().hex}",
    )
    db_session.add(user)
    await db_session.commit()

    response = await public_async_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "not-the-real-password"},
    )

    assert response.status_code == 401
    assert not response.cookies
    await db_session.refresh(user)
    assert user.last_login_at is None


def test_user_model_normalizes_email_before_storage():
    from app.models.user import User

    user = User(
        id=uuid4(),
        email="  Mixed.Case@Example.com  ",
        hashed_password="offline-hash",
        organization_id=uuid4(),
    )

    assert user.email == "mixed.case@example.com"


@pytest.mark.asyncio
async def test_auth_email_lookups_resolve_legacy_case_and_whitespace(
    db_session,
):
    from app.models.organization import Organization
    from app.models.user import User

    organization = Organization(
        name="Legacy Email Tenant", slug=f"legacy-email-{uuid4().hex}"
    )
    user = User(
        id=uuid4(),
        email=f"legacy-{uuid4().hex}@example.com",
        hashed_password="offline-hash",
        organization=organization,
    )
    legacy_email = f"  {user.email.upper()}  "
    db_session.add(user)
    await db_session.commit()
    await db_session.execute(
        text("UPDATE users SET email = :email WHERE id = :user_id"),
        {"email": legacy_email, "user_id": user.id.hex},
    )
    await db_session.commit()
    await db_session.refresh(user)

    by_login = await auth_api._lookup_user_by_email(db_session, user.email)
    by_social = await auth_api._lookup_users_by_canonical_email(
        db_session, user.email
    )

    assert user.email == legacy_email
    assert by_login is not None and by_login.id == user.id
    assert len(by_social) == 1 and by_social[0].id == user.id


@pytest.mark.asyncio
async def test_social_signup_stores_canonical_email_in_normalized_form(
    public_async_client, db_session, default_org, monkeypatch
):
    from app.models.user import User

    subject = f"supabase-{uuid4().hex}"
    email = f"Mixed-{uuid4().hex}@Example.com"
    _mock_social(
        monkeypatch,
        subject=subject,
        canonical_user=_canonical_user(subject, email),
    )
    invite_token = await _issue_social_invitation(db_session, default_org.id, email)

    response = await public_async_client.post(
        "/api/v1/auth/social-login",
        json={"token": "offline-token", "provider": "google", "invite_token": invite_token},
    )

    assert response.status_code == 200, response.text
    user = await db_session.scalar(select(User).where(User.provider_id == subject))
    assert user is not None
    assert user.email == email.lower()


def _load_normalized_email_migration():
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "027_normalized_user_email.py"
    )
    spec = importlib.util.spec_from_file_location(
        "migration_027_normalized_user_email", migration_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalized_email_migration_preflights_duplicates_without_repair():
    migration = _load_normalized_email_migration()
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL)")
        )
        connection.execute(
            text("INSERT INTO users(email) VALUES (:one), (:two)"),
            {"one": "Person@Example.com", "two": " person@example.com "},
        )

        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError, match="duplicate normalized email"):
                migration.upgrade()

        rows = connection.execute(
            text("SELECT email FROM users ORDER BY id")
        ).fetchall()
        indexes = connection.execute(text("PRAGMA index_list(users)")).fetchall()

    assert rows == [("Person@Example.com",), (" person@example.com ",)]
    assert indexes == []


def test_normalized_email_migration_enforces_case_insensitive_uniqueness():
    migration = _load_normalized_email_migration()
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL)")
        )
        connection.execute(
            text("INSERT INTO users(email) VALUES (:email)"),
            {"email": "person@example.com"},
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

        with pytest.raises(IntegrityError):
            connection.execute(
                text("INSERT INTO users(email) VALUES (:email)"),
                {"email": " PERSON@EXAMPLE.COM "},
            )
