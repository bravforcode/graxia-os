from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.core.knowledge_service import KnowledgeService


@pytest.mark.asyncio
async def test_knowledge_service_index_content():
    mock_db = AsyncMock()
    # Mock repo methods
    mock_db.execute = AsyncMock()

    service = KnowledgeService(mock_db)

    with patch("app.core.knowledge_service.embed_batch_async") as mock_embed:
        mock_embed.return_value = [[0.1] * 768]

        # Setup repo mock return for get_hashes_by_source
        service.repo.get_hashes_by_source = AsyncMock(return_value=set())
        service.repo.add_all = AsyncMock()

        indexed = await service.index_markdown_content(
            title="Test Note", content="Hello world from brav os.", source_path="test/note.md"
        )

        assert indexed == 1
        service.repo.add_all.assert_called_once()


@pytest.mark.asyncio
async def test_knowledge_service_search():
    mock_db = AsyncMock()
    service = KnowledgeService(mock_db)

    mock_item = MagicMock()
    mock_item.use_count = 0
    mock_item.content = "Result content"
    mock_item.source_path = "source.md"

    with patch("app.core.knowledge_service.embed_text_async") as mock_embed:
        mock_embed.return_value = [0.1] * 768

        service.repo.search_semantic = AsyncMock(return_value=[(mock_item, 0.1)])

        results = await service.semantic_search("query")

        assert len(results) == 1
        assert results[0]["item"].content == "Result content"
        assert mock_item.use_count == 1
