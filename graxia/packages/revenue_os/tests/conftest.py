"""
Revenue OS Test Configuration
Pytest fixtures and test database setup
"""
import pytest
import pytest_asyncio
import asyncio
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.pool import NullPool
from sqlalchemy import text

from graxia.database import Base
import os


# Test database URL (use separate test database)
def _get_test_database_url():
    """Get test database URL from env or construct from default."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url.rsplit("/", 1)[0] + "/revenue_os_test"
    return "postgresql+asyncpg://graxia:graxia@localhost:5432/revenue_os_test"

TEST_DATABASE_URL = _get_test_database_url()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=NullPool,  # Disable connection pooling for tests
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables after tests. Pre-existing FK cycle between revenue_os_ai_drafts
    # and revenue_os_approvals (unnamed constraints) makes metadata drop_all raise
    # CircularDependencyError — the test DB is ephemeral, so swallow the failure and
    # let tables persist (per-test deletes keep isolation; create_all is idempotent).
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    except Exception:
        pass
    await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Create a fresh database session for each test.

    NOTE: services in this package commit internally (order/fulfillment/email/...),
    so the session must NOT be wrapped in a single outer transaction — commits inside
    the test would close it. Instead: clean slate per test (delete all rows), then
    yield a plain session; rollback at teardown as a safety net.
    """
    # Create session factory
    async_session_maker = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        # Clean slate: delete all rows (children first via reversed dependency order)
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()
        yield session
        # Safety net: discard anything the test left uncommitted
        await session.rollback()


@pytest.fixture
def sample_product_data():
    """Sample product data for tests."""
    return {
        "name": "Test Product",
        "slug": "test-product",
        "price_cents": 9900,
        "description": "A test product for unit tests",
    }


@pytest.fixture
def sample_customer_data():
    """Sample customer data for tests."""
    return {
        "email": "test@example.com",
        "name": "Test Customer",
    }


@pytest.fixture
def sample_order_data():
    """Sample order data for tests."""
    return {
        "platform": "stripe",
        "platform_order_id": "test_order_001",
        "customer_email": "test@example.com",
        "amount_cents": 9900,
    }


@pytest.fixture
def sample_lead_data():
    """Sample lead data for tests."""
    return {
        "email": "lead@example.com",
        "name": "Test Lead",
        "source": "organic_search",
        "score": 50,
    }


@pytest.fixture
def sample_campaign_data():
    """Sample campaign data for tests."""
    return {
        "name": "Test Campaign",
        "slug": "test-campaign",
        "objective": "lead_to_sale",
        "budget_cents": 100000,  # 1000 THB
        "target_revenue_cents": 500000,  # 5000 THB
    }


@pytest.fixture
def mock_resend_client():
    """Mock Resend API client for email tests."""
    class MockResendClient:
        class Emails:
            async def send(self, data):
                """Mock email send."""
                return {
                    "id": "mock_resend_id_123",
                    "status": "sent",
                }

        def __init__(self):
            self.emails = self.Emails()

    return MockResendClient()


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic API client for AI tests."""
    class MockMessage:
        def __init__(self, content):
            self.content = [type('obj', (object,), {'text': content})]
            self.usage = type('obj', (object,), {
                'input_tokens': 100,
                'output_tokens': 200,
            })

    class MockMessages:
        async def create(self, **kwargs):
            """Mock message creation."""
            return MockMessage("Mock AI response")

    class MockAnthropicClient:
        def __init__(self):
            self.messages = MockMessages()

    return MockAnthropicClient()
