"""
BRUTAL MODE Test Configuration
Fixtures and utilities for comprehensive testing
"""
import asyncio
import os
import sys
from typing import Any, AsyncGenerator, Generator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from app.database import get_db
from app.models.base import Base
from app.main import app


# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# Use SQLite for tests (faster, isolated)
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"


@pytest_asyncio.fixture(scope="session")
async def test_engine() -> AsyncGenerator[Any, None]:
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=None,  # Disable pooling for SQLite
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create isolated test database session."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
def mock_db() -> Any:
    """Create mock database for unit tests."""
    from unittest.mock import AsyncMock, MagicMock

    mock = AsyncMock()
    mock.execute = AsyncMock()
    mock.commit = AsyncMock()
    mock.refresh = AsyncMock()
    mock.add = MagicMock()
    mock.flush = AsyncMock()
    mock.rollback = AsyncMock()
    mock.close = AsyncMock()

    return mock


# ═══════════════════════════════════════════════════════════════════════════════
# API CLIENT FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for API testing."""
    from httpx import AsyncClient, ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def test_client():
    """Create test client for synchronous testing."""
    from fastapi.testclient import TestClient
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def test_skill_id() -> UUID:
    """Fixed skill ID for consistent testing."""
    return UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def test_agent_id() -> UUID:
    """Fixed agent ID for consistent testing."""
    return UUID("87654321-4321-8765-4321-876543218765")


@pytest.fixture
def test_user_id() -> UUID:
    """Fixed user ID for consistent testing."""
    return UUID("11111111-2222-3333-4444-555555555555")


@pytest.fixture
def sample_skill_content() -> str:
    """Sample skill content for testing."""
    return """
# Sample Skill

This is a sample skill for testing purposes.

## Parameters
- input: string
- output: string

## Logic
1. Process input
2. Transform data
3. Return output
"""


@pytest.fixture
def mock_skill_data(test_skill_id: UUID) -> dict:
    """Mock skill data for testing."""
    return {
        "id": str(test_skill_id),
        "external_id": "test-skill-001",
        "source_type": "test",
        "name": "Test Skill",
        "description": "A skill for testing",
        "content": "test content",
        "version": "1.0.0",
        "skill_metadata": {},
        "usage_count": 0,
        "success_rate": 100.0,
        "effectiveness_score": 85.0,
    }


@pytest.fixture
def mock_version_data(test_skill_id: UUID, test_agent_id: UUID) -> dict:
    """Mock version data for testing."""
    return {
        "id": str(uuid4()),
        "skill_id": str(test_skill_id),
        "version_number": "1.0.0",
        "version_major": 1,
        "version_minor": 0,
        "version_patch": 0,
        "change_type": "minor",
        "status": "published",
        "content": "version content",
        "changelog": "Initial version",
        "created_by_agent_id": str(test_agent_id),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PERFORMANCE FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def performance_threshold_ms() -> int:
    """Performance threshold in milliseconds."""
    return 100  # 95th percentile must be < 100ms


@pytest.fixture
def coverage_threshold() -> float:
    """Coverage threshold percentage."""
    return 90.0  # 90%+ coverage required


# ═══════════════════════════════════════════════════════════════════════════════
# EVENT LOOP FIXTURE
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ═══════════════════════════════════════════════════════════════════════════════
# PYTEST HOOKS
# ═══════════════════════════════════════════════════════════════════════════════

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "brutal: Brutal mode tests")
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "performance: Performance tests")
    config.addinivalue_line("markers", "security: Security tests")
    config.addinivalue_line("markers", "version: Version control tests")
    config.addinivalue_line("markers", "fork: Forking tests")
    config.addinivalue_line("markers", "merge: Merging tests")
    config.addinivalue_line("markers", "dependency: Dependency graph tests")
    config.addinivalue_line("markers", "template: Template tests")
    config.addinivalue_line("markers", "validation: Validation tests")
    config.addinivalue_line("markers", "testing: Testing framework tests")
    config.addinivalue_line("markers", "abtest: A/B testing tests")
    config.addinivalue_line("markers", "rollback: Rollback tests")
    config.addinivalue_line("markers", "draft: Draft mode tests")
    config.addinivalue_line("markers", "slow: Slow tests (> 1s)")


def pytest_collection_modifyitems(config, items):
    """Modify test items before collection."""
    # Add markers based on test name patterns
    for item in items:
        if "performance" in item.name:
            item.add_marker(pytest.mark.slow)
        if "e2e" in item.name:
            item.add_marker(pytest.mark.slow)


def pytest_runtest_setup(item):
    """Setup before each test."""
    # Log test start
    print(f"\n▶️  Running: {item.name}")


def pytest_runtest_teardown(item, nextitem):
    """Teardown after each test."""
    # Log test completion
    print(f"✅ Completed: {item.name}")


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Generate test report."""
    outcome = yield
    report = outcome.get_result()

    if report.when == "call" and report.failed:
        # Log failure details
        print(f"\n[FAILED]: {item.name}")
        if report.longrepr:
            print(report.longrepr)


# ═══════════════════════════════════════════════════════════════════════════════
# ASSERTION HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

class BrutalAssertions:
    """Custom assertions for BRUTAL MODE testing."""

    @staticmethod
    def assert_response_time(duration_ms: float, threshold_ms: float = 100):
        """Assert response time is within threshold."""
        assert duration_ms < threshold_ms, (
            f"Response time {duration_ms:.2f}ms exceeds threshold {threshold_ms}ms"
        )

    @staticmethod
    def assert_coverage(coverage_pct: float, threshold_pct: float = 90.0):
        """Assert coverage meets threshold."""
        assert coverage_pct >= threshold_pct, (
            f"Coverage {coverage_pct:.2f}% below threshold {threshold_pct}%"
        )

    @staticmethod
    def assert_no_errors(result: Any):
        """Assert no errors in result."""
        assert result is not None, "Result is None"
        if hasattr(result, 'errors'):
            assert len(result.errors) == 0, f"Errors found: {result.errors}"

    @staticmethod
    def assert_valid_uuid(value: Any, field_name: str = "id"):
        """Assert value is valid UUID."""
        assert value is not None, f"{field_name} is None"
        try:
            UUID(str(value))
        except ValueError:
            pytest.fail(f"{field_name} is not a valid UUID: {value}")


@pytest.fixture
def brutal_assertions():
    """Provide brutal assertion helpers."""
    return BrutalAssertions()
