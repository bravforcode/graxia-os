"""
Pytest Configuration and Fixtures

Provides shared fixtures for all tests.
"""
import asyncio
import pytest
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.models.base import Base


# Test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


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
        future=True
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create database session for tests."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
def sample_job_data():
    """Sample job posting data."""
    return {
        "title": "Senior Python Developer",
        "company": "Tech Corp",
        "source_platform": "linkedin",
        "source_url": "https://linkedin.com/jobs/123",
        "location": "Remote",
        "job_type": "full-time",
        "description": "We are looking for a senior Python developer...",
        "required_skills": ["Python", "FastAPI", "PostgreSQL"],
        "source_hash": "abc123def456",
        "status": "discovered"
    }


@pytest.fixture
def sample_contact_data():
    """Sample contact data."""
    return {
        "name": "John Doe",
        "email": "john@example.com",
        "title": "CTO",
        "company": "Startup Inc",
        "location": "San Francisco",
        "linkedin_url": "https://linkedin.com/in/johndoe",
        "tags": ["founder", "tech"],
        "relationship_strength": 0.0
    }


@pytest.fixture
def sample_email_data():
    """Sample email thread data."""
    return {
        "thread_id": "thread_123",
        "subject": "Project Proposal",
        "participants": [
            {"email": "client@example.com", "name": "Client Name"}
        ],
        "category": "important",
        "priority": 7,
        "unread_count": 1,
        "has_attachments": False,
        "action_items": [],
        "status": "unread"
    }


@pytest.fixture
def sample_task_data():
    """Sample assistant task data."""
    return {
        "title": "Send proposal to client",
        "description": "Follow up on project discussion",
        "task_type": "email",
        "priority": 8,
        "status": "pending",
        "assigned_to": "user"
    }


@pytest.fixture
async def mock_llm_client():
    """Mock LLM client for testing."""
    class MockLLMClient:
        async def complete(self, system: str, user: str, **kwargs):
            return "Mock LLM response"
        
        async def complete_json(self, system: str, user: str, **kwargs):
            return {"score": 8.0, "summary": "Mock scoring result"}
    
    return MockLLMClient()


@pytest.fixture
async def mock_openclaw_client():
    """Mock OpenClaw client for testing."""
    class MockOpenClawClient:
        async def scrape_url(self, url: str, **kwargs):
            return {
                "html": "<html>Mock HTML</html>",
                "text": "Mock text content",
                "data": {}
            }
        
        async def extract_contacts(self, url: str, **kwargs):
            return [
                {
                    "name": "Test Contact",
                    "title": "Engineer",
                    "company": "Test Corp",
                    "profile_url": "https://linkedin.com/in/test"
                }
            ]
        
        async def extract_jobs(self, url: str, **kwargs):
            return [
                {
                    "title": "Test Job",
                    "company": "Test Corp",
                    "location": "Remote",
                    "url": "https://example.com/job/1"
                }
            ]
    
    return MockOpenClawClient()


@pytest.fixture
def mock_event_bus():
    """Mock event bus for testing."""
    class MockEventBus:
        def __init__(self):
            self.events = []
        
        async def emit(self, event: str, payload: dict):
            self.events.append({"event": event, "payload": payload})
        
        def get_events(self, event_type: str = None):
            if event_type:
                return [e for e in self.events if e["event"] == event_type]
            return self.events
        
        def clear(self):
            self.events = []
    
    return MockEventBus()
