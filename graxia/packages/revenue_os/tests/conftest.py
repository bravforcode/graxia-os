"""
Revenue OS Test Configuration
Pytest fixtures and test database setup
"""
import pytest
import asyncio
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.pool import NullPool

from graxia.database import Base
from ..db import _get_or_init_database_url
import os


# Test database URL (use separate test database)
def _get_test_database_url():
    """Get test database URL from env or construct from default."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url.rsplit("/", 1)[0] + "/revenue_os_test"
    return "postgresql+asyncpg://graxia:graxia@localhost:5432/revenue_os_test"

TEST_DATABASE_URL = _get_test_database_url()


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
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

    # Drop all tables after tests
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Create a fresh database session for each test.
    Uses transaction rollback to ensure test isolation.
    """
    # Create session factory
    async_session_maker = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        # Start transaction
        async with session.begin():
            yield session
            # Rollback transaction after test
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
