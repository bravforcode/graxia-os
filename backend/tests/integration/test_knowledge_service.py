from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.knowledge_service import get_knowledge_service


@pytest.mark.asyncio
async def test_knowledge_service_index_content():
    mock_db = AsyncMock()
    # Mock repo methods
    mock_db.execute = AsyncMock()

    service = await get_knowledge_service()

    with patch("app.services.embedding_service.EmbeddingService.generate") as mock_embed:
        mock_embed.return_value = [[0.1] * 768]

        # Mock db execute for get existing hashes
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        indexed = await service.index_markdown_content(
            db=mock_db, title="Test Note", content="Hello world from brav os.", source_path="test/note.md"
        )

        assert indexed >= 1
        # Check if add_all or add was called
        mock_db.add_all.assert_called()


@pytest.mark.asyncio
async def test_knowledge_service_search():
    mock_db = AsyncMock()
    service = await get_knowledge_service()

    mock_item = MagicMock()
    mock_item.use_count = 0
    mock_item.content = "Result content"
    mock_item.source_path = "source.md"

    with patch("app.services.embedding_service.EmbeddingService.generate") as mock_embed:
        mock_embed.return_value = [[0.1] * 768]

        # Mock db execute for semantic search
        mock_result = MagicMock()
        mock_result.all.return_value = [(mock_item, 0.1)]
        mock_db.execute.return_value = mock_result

        results = await service.semantic_search(mock_db, "query")

        assert len(results) == 1
        assert results[0]["item"].content == "Result content"
        assert mock_item.use_count == 1
