"""
Knowledge Tool for Agents
- Search knowledge base
- Ingest new information
- Format context for LLM
"""

from app.services.knowledge_service import get_knowledge_service
from sqlalchemy.ext.asyncio import AsyncSession


class KnowledgeTool:
    """Tool for agents to access knowledge base"""

    name = "knowledge_search"
    description = "Search the knowledge base for relevant information"

    async def search(
        self,
        db: AsyncSession,
        query: str,
        top_k: int = 5,
    ) -> str:
        """Search knowledge and return formatted context"""
        service = await get_knowledge_service()
        results = await service.search(db, query, top_k=top_k)
        return await service.format_as_context(results)
