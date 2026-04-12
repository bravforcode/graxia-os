from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import app as _app_bootstrap  # noqa: F401 - install Windows platform import guards

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - register all SQLAlchemy models with Base.metadata
from app.core.auth import get_password_hash
from app.database import get_db
from app.services.session_service import reset_session_service_state
from app.middleware.rate_limit import reset_rate_limit_state
from app.tasks.dlq_handler import reset_dlq_state
from app.core.time_utils import business_day_bounds_utc
from app.main import app
from app.models.assistant_task import AssistantTask
from app.models.email_thread import EmailThread
from app.models.job_posting import JobPosting
from app.models.openclaw_usage import OpenClawUsage
from app.models.base import Base
from app.models.user import User


@pytest_asyncio.fixture()
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestSessionFactory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with TestSessionFactory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield TestSessionFactory
    finally:
        app.dependency_overrides.clear()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture()
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture()
async def public_async_client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient, None]:
    reset_session_service_state()
    reset_rate_limit_state()
    reset_dlq_state()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture()
async def async_client(
    session_factory: async_sessionmaker[AsyncSession],
    public_async_client: AsyncClient,
) -> AsyncGenerator[AsyncClient, None]:
    async with session_factory() as session:
        admin = User(
            id=uuid4(),
            email="admin@example.com",
            hashed_password=get_password_hash("correct-horse-battery"),
            full_name="Admin Operator",
            role="admin",
            is_active=True,
            totp_enabled=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(admin)
        await session.commit()

    login_response = await public_async_client.post(
        "/api/v1/auth/login",
        data={"username": "admin@example.com", "password": "correct-horse-battery"},
    )
    assert login_response.status_code == 200
    access_token = login_response.json().get("access_token")
    if access_token:
        public_async_client.headers["Authorization"] = f"Bearer {access_token}"
    csrf_token = public_async_client.cookies.get("csrf_token")
    if csrf_token:
        public_async_client.headers["X-CSRF-Token"] = csrf_token
    yield public_async_client


@dataclass
class SeededRecords:
    high_score_job: JobPosting
    low_score_job: JobPosting
    email_thread: EmailThread
    task: AssistantTask


@pytest_asyncio.fixture()
async def seeded_records(db_session: AsyncSession) -> SeededRecords:
    now = datetime.now(timezone.utc)
    _, next_business_day_start_utc = business_day_bounds_utc()
    high_score_job = JobPosting(
        title="Senior Platform Engineer",
        company="Signal Forge",
        source_platform="linkedin",
        source_url="https://example.com/jobs/1",
        location="Remote",
        job_type="job",
        description="Own the API platform.",
        required_skills=["Python", "FastAPI"],
        matched_skills=["Python"],
        match_score=Decimal("8.50"),
        status="discovered",
        source_hash="job-high-score",
    )
    low_score_job = JobPosting(
        title="Junior CMS Editor",
        company="Content Co",
        source_platform="upwork",
        source_url="https://example.com/jobs/2",
        job_type="freelance",
        required_skills=["WordPress"],
        match_score=Decimal("4.00"),
        status="discovered",
        source_hash="job-low-score",
    )
    email_thread = EmailThread(
        thread_id="gmail-thread-1",
        subject="Proposal follow-up",
        participants=[{"email": "client@example.com", "name": "Client"}],
        category="important",
        priority=8,
        last_message_at=now,
        unread_count=2,
        has_attachments=False,
        action_items=[{"task": "Reply with proposal"}],
        status="unread",
        created_at=now,
        updated_at=now,
    )
    task = AssistantTask(
        title="Send proposal",
        description="Follow up with client.",
        task_type="email",
        priority=8,
        status="pending",
        due_date=next_business_day_start_utc - timedelta(minutes=1),
        assigned_to="user",
        created_at=now,
        updated_at=now,
    )
    db_session.add_all(
        [
            high_score_job,
            low_score_job,
            email_thread,
            task,
            OpenClawUsage(
                platform="linkedin",
                action="extract_jobs",
                cost_usd=Decimal("0.2500"),
                created_at=now,
            ),
            OpenClawUsage(
                platform="upwork",
                action="scrape",
                cost_usd=Decimal("0.1250"),
                created_at=now - timedelta(days=2),
            ),
        ]
    )
    await db_session.commit()

    return SeededRecords(
        high_score_job=high_score_job,
        low_score_job=low_score_job,
        email_thread=email_thread,
        task=task,
    )
