"""
Shared fixtures for service tests
"""

from unittest.mock import AsyncMock, Mock

import pytest


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    redis.ping = AsyncMock(return_value=True)
    return redis


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = Mock()
    settings.OLLAMA_URL = "http://localhost:11434"
    settings.OLLAMA_ENABLED = True
    settings.DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
    settings.OPENAI_API_KEY = "test-key"
    settings.REDIS_HOST = "localhost"
    settings.REDIS_PORT = 6379
    settings.REDIS_PASSWORD = None
    return settings
