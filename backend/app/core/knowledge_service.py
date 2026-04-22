import logging
import math
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.chunker import VaultChunker
from app.core.embedder import embed_batch_async, embed_text_async
from app.core.knowledge_repository import KnowledgeRepository
from app.models.knowledge import KnowledgeItem

logger = logging.getLogger(__name__)

class KnowledgeService:
    def __init__(self, session: AsyncSession):
        self.repo = KnowledgeRepository(session)
        self.chunker = VaultChunker()

    async def index_markdown_content(self, title: str, content: str, source_path: str, metadata: dict[str, Any] | None = None):
        chunks = self.chunker.process_file(content, default_metadata=metadata)
        existing_hashes = await self.repo.get_hashes_by_source(source_path)
        
        current_hashes = {c.hash for c in chunks}
        obsolete_hashes = existing_hashes - current_hashes
        
        if obsolete_hashes:
            await self.repo.delete_by_hashes(source_path, list(obsolete_hashes))
            
        new_chunks = [c for c in chunks if c.hash not in existing_hashes]
        if not new_chunks:
            return 0

        batch_size = 10
        total_indexed = 0
        for i in range(0, len(new_chunks), batch_size):
            batch = new_chunks[i:i+batch_size]
            embeddings = await embed_batch_async([c.text for c in batch])
            
            items = []
            for idx, c in enumerate(batch):
                emb = embeddings[idx] if embeddings else None
                if emb is None:
                    continue
                
                category = c.metadata.get("category", "vault_note")
                item = KnowledgeItem(
                    title=title,
                    content=c.text,
                    category=category,
                    chunk_hash=c.hash,
                    chunk_index=i+idx,
                    source_path=source_path,
                    embedding=emb,
                    tags=c.metadata.get("tags", []),
                )
                if "project_id" in c.metadata:
                    item.tags = item.tags + [f"project:{c.metadata['project_id']}"]
                items.append(item)
            
            if items:
                await self.repo.add_all(items)
                total_indexed += len(items)
        
        return total_indexed

    async def semantic_search(self, query: str, top_k: int = 5, project_id: str | None = None) -> list[dict[str, Any]]:
        query_vec = await embed_text_async(query)
        if not query_vec:
            return []

        rows = await self.repo.search_semantic(query_vec, limit=top_k * 2, project_id=project_id)
        
        scored_items = []
        for item, distance in rows:
            similarity = 1.0 - distance
            # Boost score based on use count
            boost = 1.0 + math.log1p(item.use_count or 0)
            final_score = similarity * boost
            scored_items.append({
                "score": final_score,
                "item": item
            })
        
        scored_items.sort(key=lambda x: x["score"], reverse=True)
        results = scored_items[:top_k]
        
        # Update use count
        for res in results:
            res["item"].use_count = (res["item"].use_count or 0) + 1
            
        return results
