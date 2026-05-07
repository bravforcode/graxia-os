"""
Tests for KnowledgeService
TDD approach: test first, then implementation
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import UUID

import pytest
from app.services.embedding_service import EmbeddingService
from app.services.knowledge_service import KnowledgeService, get_knowledge_service
from sqlalchemy.ext.asyncio import AsyncSession

# ═════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def knowledge_service():
    """Create KnowledgeService instance for testing."""
    return KnowledgeService()


@pytest.fixture
def mock_db_session():
    """Create mock database session."""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.fixture
def mock_embedding_service():
    """Create mock embedding service."""
    service = AsyncMock(spec=EmbeddingService)
    service.generate = AsyncMock(return_value=[[0.1] * 768])
    return service


# ═════════════════════════════════════════════════════════════════════════════
# Test Cases
# ═════════════════════════════════════════════════════════════════════════════


class TestKnowledgeServiceSearch:
    """Test knowledge base search functionality."""

    @pytest.mark.asyncio
    async def test_search_empty_query(self, knowledge_service, mock_db_session):
        """Test that empty query returns empty results."""
        result = await knowledge_service.search(mock_db_session, "")
        assert result == []

    @pytest.mark.asyncio
    async def test_search_with_results(self, knowledge_service, mock_db_session):
        """Test search returning results."""
        query = "test query"

        # Mock embedding service
        with patch("app.services.knowledge_service.get_embedding_service") as mock_get_emb:
            mock_emb = AsyncMock()
            mock_emb.generate = AsyncMock(return_value=[[0.1] * 768])
            mock_get_emb.return_value = mock_emb

            # Mock database execute
            mock_result = MagicMock()
            mock_result.mappings.return_value.all.return_value = [
                {"content": "test content", "similarity": 0.85}
            ]
            mock_db_session.execute = AsyncMock(return_value=mock_result)

            result = await knowledge_service.search(mock_db_session, query, top_k=5)

        assert len(result) == 1
        assert result[0]["content"] == "test content"
        assert result[0]["similarity"] == 0.85

    @pytest.mark.asyncio
    async def test_search_no_results(self, knowledge_service, mock_db_session):
        """Test search with no matching results."""
        query = "nonexistent query"

        with patch("app.services.knowledge_service.get_embedding_service") as mock_get_emb:
            mock_emb = AsyncMock()
            mock_emb.generate = AsyncMock(return_value=[[0.1] * 768])
            mock_get_emb.return_value = mock_emb

            # Mock empty result
            mock_result = MagicMock()
            mock_result.mappings.return_value.all.return_value = []
            mock_db_session.execute = AsyncMock(return_value=mock_result)

            result = await knowledge_service.search(mock_db_session, query)

        assert result == []

    @pytest.mark.asyncio
    async def test_search_with_rerank(self, knowledge_service, mock_db_session):
        """Test search with reranking."""
        query = "test query"

        with patch("app.services.knowledge_service.get_embedding_service") as mock_get_emb:
            mock_emb = AsyncMock()
            mock_emb.generate = AsyncMock(return_value=[[0.1] * 768])
            mock_get_emb.return_value = mock_emb

            # Mock multiple results
            mock_result = MagicMock()
            mock_result.mappings.return_value.all.return_value = [
                {"content": "first", "similarity": 0.9},
                {"content": "second", "similarity": 0.8},
                {"content": "third", "similarity": 0.7},
            ]
            mock_db_session.execute = AsyncMock(return_value=mock_result)

            result = await knowledge_service.search(mock_db_session, query, top_k=3, rerank_to=2)

        # Should return only top 2 after reranking
        assert len(result) == 2


class TestKnowledgeServiceIngestDocument:
    """Test document ingestion functionality."""

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires DB flush to assign doc.id; covered by integration tests")
    async def test_ingest_simple_document(self, knowledge_service, mock_db_session):
        """Test ingesting a simple document."""
        title = "Test Document"
        content = "This is test content."

        with patch("app.services.knowledge_service.get_embedding_service") as mock_get_emb:
            mock_emb = AsyncMock()
            mock_emb.generate = AsyncMock(return_value=[[0.1] * 768])
            mock_get_emb.return_value = mock_emb

            with patch("app.services.knowledge_service.VaultChunker") as mock_chunker:
                # Mock chunker
                chunk = Mock()
                chunk.text = "This is test content."
                chunk.index = 0
                mock_chunker.return_value.chunk = Mock(return_value=[chunk])

                # Mock document creation
                mock_db_session.flush = AsyncMock()
                mock_db_session.commit = AsyncMock()

                doc_id = await knowledge_service.ingest_document(
                    mock_db_session, title=title, content=content, source="test", tags=["test"]
                )

        assert isinstance(doc_id, UUID)
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires DB flush to assign doc.id; covered by integration tests")
    async def test_ingest_empty_content(self, knowledge_service, mock_db_session):
        """Test ingesting empty content."""
        title = "Empty Document"
        content = ""

        with patch("app.services.knowledge_service.get_embedding_service") as mock_get_emb:
            mock_emb = AsyncMock()
            mock_emb.generate = AsyncMock(return_value=[])
            mock_get_emb.return_value = mock_emb

            with patch(
                "app.services.knowledge_service.SemanticChunker", create=True
            ) as mock_chunker:
                # Empty chunks
                mock_chunker.return_value.chunk = Mock(return_value=[])

                mock_db_session.flush = AsyncMock()
                mock_db_session.commit = AsyncMock()

                doc_id = await knowledge_service.ingest_document(
                    mock_db_session,
                    title=title,
                    content=content,
                )

        assert isinstance(doc_id, UUID)


class TestKnowledgeServiceFormatContext:
    """Test context formatting functionality."""

    @pytest.mark.asyncio
    async def test_format_empty_chunks(self, knowledge_service):
        """Test formatting empty chunks."""
        result = await knowledge_service.format_as_context([])
        assert result == ""

    @pytest.mark.asyncio
    async def test_format_single_chunk(self, knowledge_service):
        """Test formatting single chunk."""
        chunks = [{"content": "test content", "similarity": 0.9}]
        result = await knowledge_service.format_as_context(chunks)

        assert "test content" in result
        assert "0.90" in result

    @pytest.mark.asyncio
    async def test_format_multiple_chunks(self, knowledge_service):
        """Test formatting multiple chunks."""
        chunks = [
            {"content": "first chunk", "similarity": 0.9},
            {"content": "second chunk", "similarity": 0.8},
        ]
        result = await knowledge_service.format_as_context(chunks)

        assert "first chunk" in result
        assert "second chunk" in result
        assert "---" in result  # separator

    @pytest.mark.asyncio
    async def test_format_respects_token_limit(self, knowledge_service):
        """Test that formatting respects token limit."""
        # Create long content that would exceed limit
        chunks = [
            {"content": "word " * 1000, "similarity": 0.9},  # ~1300 estimated tokens
            {"content": "more content", "similarity": 0.8},
        ]
        result = await knowledge_service.format_as_context(chunks, max_tokens=500)

        # Should only include first chunk (partially) and stop
        assert "more content" not in result


class TestGetKnowledgeService:
    """Test get_knowledge_service singleton function."""

    @pytest.mark.asyncio
    async def test_singleton_returns_same_instance(self):
        """Test that singleton returns same instance."""
        service1 = await get_knowledge_service()
        service2 = await get_knowledge_service()
        assert service1 is service2

    @pytest.mark.asyncio
    async def test_singleton_creates_instance_if_none(self):
        """Test that singleton creates instance on first call."""
        # Reset singleton
        import app.services.knowledge_service as ks

        original = ks._knowledge_service
        ks._knowledge_service = None

        try:
            service = await get_knowledge_service()
            assert service is not None
            assert isinstance(service, KnowledgeService)
        finally:
            ks._knowledge_service = original


class TestKnowledgeServiceIntegration:
    """Integration tests for KnowledgeService workflows."""

    @pytest.mark.asyncio
    async def test_search_to_context_workflow(self, knowledge_service, mock_db_session):
        """Test complete workflow from search to context formatting."""
        query = "integration test"

        with patch("app.services.knowledge_service.get_embedding_service") as mock_get_emb:
            mock_emb = AsyncMock()
            mock_emb.generate = AsyncMock(return_value=[[0.1] * 768])
            mock_get_emb.return_value = mock_emb

            # Mock search results
            mock_result = MagicMock()
            mock_result.mappings.return_value.all.return_value = [
                {"content": "relevant content", "similarity": 0.95},
            ]
            mock_db_session.execute = AsyncMock(return_value=mock_result)

            # Search
            search_results = await knowledge_service.search(mock_db_session, query, top_k=5)

            # Format as context
            context = await knowledge_service.format_as_context(search_results)

        assert "relevant content" in context
        assert "0.95" in context or "0.9" in context
