"""
Tests for EmbeddingService
"""

import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.embedding_service import (
    VECTOR_DIMENSIONS,
    EmbeddingService,
    get_embedding_service,
)

# ═════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def embedding_service():
    """Create EmbeddingService instance for testing."""
    service = EmbeddingService()
    service._cache = AsyncMock()
    return service


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════


def _make_http_client_mock(json_response: dict) -> MagicMock:
    """
    Build a MagicMock that correctly acts as an httpx.AsyncClient async
    context manager.  Setting __aenter__.return_value = mock_client ensures
    that `async with httpx.AsyncClient() as client:` hands back our pre-
    configured mock client with the `post` AsyncMock already attached.
    """
    mock_response = MagicMock()
    mock_response.json.return_value = json_response
    mock_response.raise_for_status = MagicMock(return_value=None)

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ═════════════════════════════════════════════════════════════════════════════
# Test Cases
# ═════════════════════════════════════════════════════════════════════════════


class TestEmbeddingServiceInit:
    """Test EmbeddingService initialization."""

    def test_default_model_is_nomic(self):
        """Without explicit model config the service falls back to nomic-embed-text."""
        with patch("app.services.embedding_service.settings") as mock_settings:
            mock_settings.DEFAULT_EMBEDDING_MODEL = ""
            mock_settings.OLLAMA_URL = ""
            mock_settings.OPENAI_API_KEY = ""
            mock_settings.OPENAI_BASE_URL = ""
            service = EmbeddingService()
        assert service.model == "nomic-embed-text"
        assert service.dimension == 768

    def test_dimension_lookup(self):
        """Test dimension constants are correct."""
        assert VECTOR_DIMENSIONS["nomic-embed-text"] == 768
        assert VECTOR_DIMENSIONS["text-embedding-3-small"] == 1536
        assert VECTOR_DIMENSIONS["text-embedding-3-large"] == 3072


class TestEmbeddingServiceGenerate:
    """Test embedding generation with various scenarios."""

    @pytest.mark.asyncio
    async def test_empty_texts_returns_empty_list(self, embedding_service):
        """Test that empty input returns empty output."""
        result = await embedding_service.generate([])
        assert result == []

    @pytest.mark.asyncio
    async def test_single_text_ollama(self, embedding_service):
        """Test generating embedding for single text via Ollama."""
        dim = embedding_service.dimension
        embedding_service._generate_ollama = AsyncMock(return_value=[[0.1] * dim])

        result = await embedding_service.generate(["hello world"], use_cache=False)

        assert len(result) == 1
        assert len(result[0]) == dim
        assert all(isinstance(x, float) for x in result[0])

    @pytest.mark.asyncio
    async def test_batch_generation(self, embedding_service):
        """Test generating embeddings for multiple texts."""
        dim = embedding_service.dimension
        embedding_service._generate_ollama = AsyncMock(
            return_value=[[0.1] * dim, [0.2] * dim, [0.3] * dim]
        )

        result = await embedding_service.generate(
            ["first text", "second text", "third text"], use_cache=False
        )

        assert len(result) == 3
        for emb in result:
            assert len(emb) == dim

    @pytest.mark.asyncio
    async def test_caching_behavior(self, embedding_service):
        """Test that embeddings are cached and retrieved correctly."""
        text = "test caching"
        cache_key = f"emb:{hashlib.sha256(text.encode()).hexdigest()}"
        dim = embedding_service.dimension

        embedding_service._cache.get = AsyncMock(return_value=json.dumps([0.5] * dim))
        embedding_service._cache.setex = AsyncMock()

        result = await embedding_service.generate([text], use_cache=True)

        embedding_service._cache.get.assert_called_once_with(cache_key)
        assert len(result) == 1
        assert result[0] == [0.5] * dim

    @pytest.mark.asyncio
    async def test_cache_miss_generates_embedding(self, embedding_service):
        """Test that cache miss triggers an API call."""
        text = "test cache miss"
        dim = embedding_service.dimension

        embedding_service._cache.get = AsyncMock(return_value=None)
        embedding_service._cache.setex = AsyncMock()
        embedding_service._generate_ollama = AsyncMock(return_value=[[0.1] * dim])

        result = await embedding_service.generate([text], use_cache=True)

        embedding_service._cache.setex.assert_called_once()
        assert len(result) == 1


class TestDimensionEnforcement:
    """Test embedding dimension enforcement inside _generate_ollama."""

    @pytest.mark.asyncio
    async def test_dimension_mismatch_raises_error(self, embedding_service):
        """Wrong dimension in Ollama response must raise ValueError."""
        wrong_dim = embedding_service.dimension + 1  # always wrong
        mock_client = _make_http_client_mock({"embeddings": [[0.1] * wrong_dim]})

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ValueError, match="dimension mismatch"):
                await embedding_service.generate(["test"], use_cache=False)

    @pytest.mark.asyncio
    async def test_correct_dimension_passes(self, embedding_service):
        """Correct dimension in Ollama response must not raise."""
        dim = embedding_service.dimension
        mock_client = _make_http_client_mock({"embeddings": [[0.1] * dim]})

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await embedding_service.generate(["test"], use_cache=False)

        assert len(result[0]) == dim


class TestFallbackBehavior:
    """Test fallback to OpenAI when Ollama fails."""

    @pytest.mark.asyncio
    async def test_ollama_failure_falls_back_to_openai(self, embedding_service):
        """Ollama raising must trigger OpenAI fallback."""
        embedding_service.openai_key = "test-key"
        # Make Ollama raise so _generate_batch falls through to OpenAI path
        embedding_service._generate_ollama = AsyncMock(
            side_effect=Exception("Ollama connection failed")
        )
        embedding_service._generate_openai = AsyncMock(return_value=[[0.1] * 1536])

        result = await embedding_service.generate(["test"], use_cache=False)

        assert len(result[0]) == 1536

    @pytest.mark.asyncio
    async def test_no_provider_raises_error(self, embedding_service):
        """Neither Ollama nor OpenAI available must raise RuntimeError."""
        embedding_service.openai_key = None

        with patch("app.services.embedding_service.settings") as mock_settings:
            mock_settings.OLLAMA_ENABLED = False

            with pytest.raises(RuntimeError, match="No embedding provider"):
                await embedding_service.generate(["test"], use_cache=False)


class TestGetEmbeddingService:
    """Test get_embedding_service singleton function."""

    @pytest.mark.asyncio
    async def test_singleton_returns_same_instance(self):
        """Singleton must return the same object on repeated calls."""
        service1 = await get_embedding_service()
        service2 = await get_embedding_service()
        assert service1 is service2

    @pytest.mark.asyncio
    async def test_singleton_creates_instance_if_none(self):
        """Singleton must create a new instance when reset to None."""
        import app.services.embedding_service as es

        original = es._embedding_service
        es._embedding_service = None

        try:
            service = await get_embedding_service()
            assert service is not None
            assert isinstance(service, EmbeddingService)
        finally:
            es._embedding_service = original
