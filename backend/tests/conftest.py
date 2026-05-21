import os
import sys
import uuid
from pathlib import Path

# Ensure project root is on sys.path for imports from scripts/ops/
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Also add backend/ to sys.path so scripts/ops/* can import 'app' module
# Note: Project root MUST be before backend/ to avoid namespace collision
# between backend/scripts/ and project-root/scripts/
_backend_path = _project_root / "backend"
if str(_backend_path) not in sys.path:
    # Insert at position after project_root to keep project root first
    sys.path.insert(1, str(_backend_path))

# ── TEST DATABASE SAFETY GUARD ──────────────────────────────────────────
# Refuse to run tests against production/staging databases.
# Only SQLite or URLs containing 'test', 'tmp', or explicit override are allowed.

_original_db_url = os.environ.get("DATABASE_URL", "")
_safe_hostnames = ["localhost", "127.0.0.1", "::1", "host.docker.internal"]
_unsafe_hostnames = ["supabase.co", "fly.dev", "production.", "staging.", "prod-", "rds.amazonaws.com", "cockroachlabs.cloud"]

def _is_safe_test_db_url(url: str) -> bool:
    """Check if DATABASE_URL is safe for testing."""
    if not url:
        return True  # Will be overridden below
    url_lower = url.lower()
    # SQLite is always safe
    if "sqlite" in url_lower:
        return True
    # Local/dev hostnames are always acceptable for testing
    for safe in _safe_hostnames:
        if safe in url_lower:
            return True
    # Check for unsafe production hostnames
    for unsafe in _unsafe_hostnames:
        if unsafe in url_lower:
            return False
    # Check for explicit override
    if os.environ.get("ALLOW_UNSAFE_TEST_DB") == "1":
        return True
    # Check URL path for 'test' or 'tmp' markers
    if "/test" in url_lower or "/tmp" in url_lower or "test_" in url_lower or "_test" in url_lower:
        return True
    return False

if not _is_safe_test_db_url(_original_db_url) and not os.environ.get("ALLOW_UNSAFE_TEST_DB") == "1":
    raise RuntimeError(
        f"REFUSING to run tests: DATABASE_URL={_original_db_url!r} appears to point to a "
        f"production or staging database. Set ALLOW_UNSAFE_TEST_DB=1 to override (NOT RECOMMENDED)."
    )

# Use a unique DB for each test process to avoid concurrency issues
_test_db_id = uuid.uuid4().hex[:8]
_test_db_path = str(_project_root / "backend" / "tests" / f"test_{_test_db_id}.db")

# Force REAL services for Phase 9 tests
os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_test_db_path}"
os.environ["REDIS_ENABLED"] = "false"
os.environ["REDIS_URL"] = "redis://localhost:6380/0"

import base64
os.environ["APP_ENV"] = "testing"  # Bypass strict secret validation at module import time
os.environ["SECRET_KEY"] = "8b6e6f1f43a6d96e8f498c1999d3e527d710f63e63283c483d8e578c772091d3"
os.environ["ENCRYPTION_KEY"] = "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE="

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

# Import app.database first to ensure engine is created with correct settings
import app.database

# Ensure all models are registered
import app.models
import pytest_asyncio
from app.config import settings
from app.core.auth import get_password_hash
from app.core.time_utils import business_day_bounds_utc
from app.middleware.rate_limit import reset_rate_limit_state
from app.models.assistant_task import AssistantTask
from app.models.base import Base
from app.models.email_thread import EmailThread
from app.models.job_posting import JobPosting
from app.models.openclaw_usage import OpenClawUsage
from app.models.organization import Organization
from app.models.user import User
from app.services.session_service import reset_session_service_state
from app.tasks.dlq_handler import reset_dlq_state
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest_asyncio.fixture(scope="session")
def engine():
    # Force recreate engine with test settings
    import importlib
    importlib.reload(app.database)
    return app.database.engine

@pytest_asyncio.fixture(autouse=True)
async def setup_database(engine):
    # For test DB file, create all tables fresh for each test
    # Using proper ordering to avoid foreign key issues with SQLite
    async with engine.begin() as conn:
        # Disable foreign keys during table creation for SQLite
        def _create_tables(conn):
            conn.execute(text("PRAGMA foreign_keys=OFF"))
            Base.metadata.create_all(conn)
            conn.execute(text("PRAGMA foreign_keys=ON"))

        await conn.run_sync(_create_tables)

    yield

    # Cleanup after test
    async with engine.begin() as conn:
        def _drop_tables(conn):
            conn.execute(text("PRAGMA foreign_keys=OFF"))
            Base.metadata.drop_all(conn)
            conn.execute(text("PRAGMA foreign_keys=ON"))

        await conn.run_sync(_drop_tables)

@pytest_asyncio.fixture()
async def session_factory(engine, setup_database) -> async_sessionmaker[AsyncSession]:
    return app.database.AsyncSessionLocal

@pytest_asyncio.fixture()
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session
        await session.rollback()

@pytest_asyncio.fixture()
async def public_async_client(session_factory) -> AsyncGenerator[AsyncClient, None]:
    reset_session_service_state()
    reset_rate_limit_state()
    reset_dlq_state()

    from app.main import app as fastapi_app

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

@pytest_asyncio.fixture()
async def default_org(db_session: AsyncSession) -> Organization:
    org_id = uuid4()
    org = Organization(
        id=org_id,
        name=f"Test Org {org_id}",
        slug=f"test-org-{org_id}",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org

@pytest_asyncio.fixture()
async def async_client(
    session_factory: async_sessionmaker[AsyncSession],
    public_async_client: AsyncClient,
) -> AsyncGenerator[AsyncClient, None]:
    async with session_factory() as session:
        org_id = uuid4()
        org = Organization(
            id=org_id,
            name=f"Admin Org {org_id}",
            slug=f"admin-org-{org_id}",
            status="active",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(org)
        await session.commit()
        await session.refresh(org)

        email = f"admin-{uuid4()}@example.com"
        admin = User(
            id=uuid4(),
            email=email,
            hashed_password=get_password_hash("password"),
            full_name="Admin Operator",
            role="admin",
            is_active=True,
            totp_enabled=False,
            organization_id=org.id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(admin)
        await session.commit()

    login_response = await public_async_client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "password"},
    )
    assert login_response.status_code == 200
    access_token = login_response.json().get("access_token")
    if access_token:
        public_async_client.headers["Authorization"] = f"Bearer {access_token}"
    csrf_token = public_async_client.cookies.get(settings.CSRF_COOKIE_NAME)
    if csrf_token:
        public_async_client.headers["X-CSRF-Token"] = csrf_token
    yield public_async_client

@pytest_asyncio.fixture()
async def admin_user(db_session: AsyncSession, default_org: Organization) -> User:
    user = User(
        email=f"admin-fixture-{uuid4()}@example.com",
        hashed_password=get_password_hash("testpassword123"),
        full_name="Admin Operator",
        role="admin",
        is_active=True,
        organization_id=default_org.id,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@dataclass
class SeededRecords:
    high_score_job: JobPosting
    low_score_job: JobPosting
    email_thread: EmailThread
    task: AssistantTask

@pytest_asyncio.fixture()
async def seeded_records(db_session: AsyncSession, default_org: Organization) -> SeededRecords:
    now = datetime.now(UTC)
    _, next_business_day_start_utc = business_day_bounds_utc()
    high_score_job = JobPosting(
        title="Senior Platform Engineer",
        company="Tech Corp",
        source_platform="linkedin",
        source_url="http://example.com/job1",
        match_score=Decimal("9.5"),
        status="discovered",
        job_type="job",
        source_hash=f"job1-{uuid4()}",
        organization_id=default_org.id,
    )
    low_score_job = JobPosting(
        title="Junior Dev",
        company="Startup",
        source_platform="indeed",
        source_url="http://example.com/job2",
        match_score=Decimal("4.5"),
        status="discovered",
        job_type="job",
        source_hash=f"job2-{uuid4()}",
        organization_id=default_org.id,
    )
    email_thread = EmailThread(
        thread_id=f"thread-{uuid4()}",
        subject="Interview Invitation",
        category="important",
        priority=10,
        status="unread",
        unread_count=1,
        last_message_at=now,
        organization_id=default_org.id,
    )
    email_thread.add_action_item("Prepare for interview", priority=9)
    task = AssistantTask(
        title="Initial Research",
        description="Follow up.",
        task_type="email",
        priority=8,
        status="pending",
        due_date=next_business_day_start_utc - timedelta(minutes=1),
        assigned_to="user",
        organization_id=default_org.id,
        created_at=now,
        updated_at=now,
    )

    usage1 = OpenClawUsage(
        id=uuid4(),
        platform="linkedin",
        action="scrape",
        cost_usd=Decimal("0.25"),
        created_at=now,
    )
    usage2 = OpenClawUsage(
        id=uuid4(),
        platform="upwork",
        action="scrape",
        cost_usd=Decimal("0.125"),
        created_at=now - timedelta(days=2),
    )

    db_session.add_all([high_score_job, low_score_job, email_thread, task, usage1, usage2])
    await db_session.commit()
    return SeededRecords(
        high_score_job=high_score_job,
        low_score_job=low_score_job,
        email_thread=email_thread,
        task=task,
    )

@pytest_asyncio.fixture()
def isolated_event_bus():
    from app.core.event_bus import EventBus
    return EventBus()

from unittest.mock import MagicMock, patch

@pytest_asyncio.fixture(autouse=True)
def mock_celery_inspect():
    with patch("app.tasks.celery_app.celery_app.control.inspect") as mock_inspect:
        mock_inspect_instance = MagicMock()
        mock_inspect_instance.ping.return_value = {"celery@test": {"ok": "pong"}}
        mock_inspect.return_value = mock_inspect_instance
        yield mock_inspect
