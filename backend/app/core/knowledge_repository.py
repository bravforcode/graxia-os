import logging
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeItem

logger = logging.getLogger(__name__)

class KnowledgeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_chunk_hash(self, chunk_hash: str) -> KnowledgeItem | None:
        stmt = select(KnowledgeItem).where(KnowledgeItem.chunk_hash == chunk_hash)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_hashes_by_source(self, source_path: str) -> set[str]:
        stmt = select(KnowledgeItem.chunk_hash).where(KnowledgeItem.source_path == source_path)
        result = await self.session.execute(stmt)
        return {row[0] for row in result.fetchall()}

    async def delete_by_hashes(self, source_path: str, hashes: Sequence[str]):
        if not hashes:
            return
        stmt = delete(KnowledgeItem).where(
            KnowledgeItem.source_path == source_path,
            KnowledgeItem.chunk_hash.in_(hashes)
        )
        await self.session.execute(stmt)

    async def add_all(self, items: list[KnowledgeItem]):
        self.session.add_all(items)

    async def search_semantic(self, query_vec: list[float], limit: int = 5, category: str | None = None, project_id: str | None = None):
        stmt = (
            select(KnowledgeItem, KnowledgeItem.embedding.cosine_distance(query_vec).label("distance"))
            .where(KnowledgeItem.is_active == True)
        )
        
        if category:
            stmt = stmt.filter(KnowledgeItem.category == category)
        if project_id:
            stmt = stmt.filter(KnowledgeItem.tags.contains([f"project:{project_id}"]))
            
        stmt = stmt.order_by(KnowledgeItem.embedding.cosine_distance(query_vec)).limit(limit)
        
        result = await self.session.execute(stmt)
        return result.all()
