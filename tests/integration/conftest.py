"""
Integration test configuration and fixtures
"""
import asyncio
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

import sys
sys.path.insert(0, 'backend')
from app.main import app
from app.models.base import Base
from app.database import get_db

# Test database URL
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "sqlite+aiosqlite:///./test.db"
)

# Create test engine
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
)

TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create test database session"""
    # Create tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    async with TestSessionLocal() as session:
        yield session

    # Drop tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client"""
    from httpx import ASGITransport

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient) -> str:
    """Create admin user and return auth token"""
    # Register admin user
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "admin@test.com",
            "password": "testpassword123",
            "full_name": "Test Admin"
        }
    )
    assert response.status_code == 200

    # Login
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@test.com",
            "password": "testpassword123"
        }
    )
    assert response.status_code == 200
    data = response.json()
    return data["access_token"]


@pytest.fixture
def auth_headers(admin_token: str) -> dict:
    """Create authorization headers"""
    return {"Authorization": f"Bearer {admin_token}"}
