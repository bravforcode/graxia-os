"""
Knowledge Service for GRAXIA OS
- Unified RAG core
- Vault indexing (from app.core)
- Document ingestion (from app.services)
- Semantic search across both KnowledgeItem and KnowledgeChunk
"""

import math
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chunker import VaultChunker
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeItem
from app.services.embedding_service import get_embedding_service

logger = structlog.get_logger("knowledge")


class KnowledgeService:
    """Unified Knowledge Service for RAG and Vault management"""

    def __init__(self):
        self.chunker = VaultChunker()

    # ═════════════════════════════════════════════════════════════════════════
    # GENERIC DOCUMENT RAG (formerly in services)
    # ═════════════════════════════════════════════════════════════════════════

    async def search(
        self,
        db: AsyncSession,
        query: str,
        top_k: int = 5,
        rerank_to: int | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search over generic knowledge base (knowledge_chunks)"""
        if not query or not query.strip():
            return []

        embedding_service = await get_embedding_service()
        query_embedding = await embedding_service.generate([query])
        if not query_embedding:
            return []

        query_vector = query_embedding[0]

        # Vector search with pgvector
        sql = text("""
            SELECT kc.*, 1 - (kc.embedding <=> :query_vector) as similarity
            FROM knowledge_chunks kc
            WHERE kc.embedding IS NOT NULL
            ORDER BY kc.embedding <=> :query_vector
            LIMIT :limit
        """)

        result = await db.execute(
            sql,
            {
                "query_vector": str(query_vector),
                "limit": top_k,
            },
        )

        chunks = result.mappings().all()

        # Optional: rerank with cross-encoder
        if rerank_to and len(chunks) > rerank_to:
            chunks = await self._rerank_chunks(query, chunks, rerank_to)

        return [dict(c) for c in chunks]

    async def ingest_document(
        self,
        db: AsyncSession,
        title: str,
        content: str,
        source: str = "manual",
        tags: list[str] | None = None,
    ) -> UUID:
        """Ingest document with semantic chunking"""
        # Create document
        doc = KnowledgeDocument(
            title=title,
            content=content,
            source_type=source,
            doc_metadata={"tags": tags} if tags else {},
        )
        db.add(doc)
        await db.flush()

        # Chunk content
        chunks = self.chunker.process_file(content)

        # Generate embeddings
        embedding_service = await get_embedding_service()
        embeddings = await embedding_service.generate([c.text for c in chunks])

        # Store chunks
        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=False)):
            chunk_obj = KnowledgeChunk(
                document_id=doc.id,
                content=chunk.text,
                embedding=embedding,
                chunk_index=idx,
            )
            db.add(chunk_obj)

        await db.commit()
        logger.info(
            "document_ingested",
            doc_id=str(doc.id),
            chunks=len(chunks),
            source=source,
        )
        return doc.id

    # ═════════════════════════════════════════════════════════════════════════
    # VAULT / ITEM-BASED RAG (formerly in core)
    # ═════════════════════════════════════════════════════════════════════════

    async def index_markdown_content(
        self,
        db: AsyncSession,
        title: str,
        content: str,
        source_path: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Index vault content into knowledge_items (preserving hashes and use_counts)"""
        chunks = self.chunker.process_file(content, default_metadata=metadata)

        # Get existing hashes for this source
        stmt = select(KnowledgeItem.chunk_hash).where(KnowledgeItem.source_path == source_path)
        result = await db.execute(stmt)
        existing_hashes = {row[0] for row in result.fetchall()}

        current_hashes = {c.hash for c in chunks}
        obsolete_hashes = existing_hashes - current_hashes

        if obsolete_hashes:
            del_stmt = delete(KnowledgeItem).where(
                KnowledgeItem.source_path == source_path,
                KnowledgeItem.chunk_hash.in_(list(obsolete_hashes)),
            )
            await db.execute(del_stmt)

        new_chunks = [c for c in chunks if c.hash not in existing_hashes]
        if not new_chunks:
            return 0

        embedding_service = await get_embedding_service()
        embeddings = await embedding_service.generate([c.text for c in new_chunks])

        items = []
        for idx, c in enumerate(new_chunks):
            emb = embeddings[idx] if embeddings else None
            if emb is None:
                continue

            category = c.metadata.get("category", "vault_note")
            item = KnowledgeItem(
                title=title,
                content=c.text,
                category=category,
                chunk_hash=c.hash,
                chunk_index=idx,
                source_path=source_path,
                embedding=emb,
                tags=c.metadata.get("tags", []),
            )
            if "project_id" in c.metadata:
                item.tags = (item.tags or []) + [f"project:{c.metadata['project_id']}"]
            items.append(item)

        if items:
            db.add_all(items)
            await db.flush()

        return len(items)

    async def semantic_search(
        self,
        db: AsyncSession,
        query: str,
        top_k: int = 5,
        project_id: str | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search across knowledge_items (with use_count boosting)"""
        embedding_service = await get_embedding_service()
        query_embedding = await embedding_service.generate([query])
        if not query_embedding:
            return []

        query_vec = query_embedding[0]

        # Cosine distance in pgvector: <=> operator
        stmt = select(
            KnowledgeItem,
            KnowledgeItem.embedding.cosine_distance(query_vec).label("distance"),
        ).where(KnowledgeItem.is_active == True)
        if category:
            stmt = stmt.filter(KnowledgeItem.category == category)
        if project_id:
            stmt = stmt.filter(KnowledgeItem.tags.contains([f"project:{project_id}"]))

        stmt = stmt.order_by("distance").limit(top_k * 2)
        result = await db.execute(stmt)
        rows = result.all()

        scored_items = []
        for item, distance in rows:
            similarity = 1.0 - distance
            boost = 1.0 + math.log1p(item.use_count or 0)
            final_score = similarity * boost
            scored_items.append({"score": final_score, "item": item})

        scored_items.sort(key=lambda x: x["score"], reverse=True)
        results = scored_items[:top_k]

        for res in results:
            res["item"].use_count = (res["item"].use_count or 0) + 1
            res["item"].last_used_at = datetime.now(UTC)

        return results

    # ═════════════════════════════════════════════════════════════════════════
    # UTILITIES
    # ═════════════════════════════════════════════════════════════════════════

    async def format_as_context(self, chunks: list[dict], max_tokens: int = 2000) -> str:
        """Format search results as context for LLM"""
        context_parts = []
        total_tokens = 0
        for chunk in chunks:
            if "item" in chunk:
                content = chunk["item"].content
                similarity = chunk["score"]
            else:
                content = chunk.get("content", "")
                similarity = chunk.get("similarity", 0)

            estimated_tokens = len(content.split()) * 1.3
            if total_tokens + estimated_tokens > max_tokens:
                break
            context_parts.append(f"[Relevance: {similarity:.2f}]\n{content}")
            total_tokens += estimated_tokens
        return "\n\n---\n\n".join(context_parts)

    async def _rerank_chunks(self, query: str, chunks: list[dict], top_n: int) -> list[dict]:
        """Rerank chunks using cross-encoder (Simplified)"""
        return sorted(chunks, key=lambda x: x.get("similarity", 0), reverse=True)[:top_n]


_knowledge_service: KnowledgeService | None = None


async def get_knowledge_service() -> KnowledgeService:
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    return _knowledge_service
