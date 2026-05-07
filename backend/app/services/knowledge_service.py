"""
Knowledge Service for GRAXIA OS
- RAG core with semantic chunking
- Vector search with pgvector
- Knowledge base management
"""

from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.services.embedding_service import get_embedding_service

logger = structlog.get_logger("knowledge")


class KnowledgeService:
    """RAG knowledge base with semantic search"""

    async def search(
        self,
        db: AsyncSession,
        query: str,
        top_k: int = 5,
        rerank_to: int | None = None,
    ) -> list[KnowledgeChunk]:
        """Semantic search over knowledge base"""

        # Short-circuit on empty query before hitting embedding service
        if not query or not query.strip():
            return []

        # Generate query embedding
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
        from app.core.chunker import VaultChunker as SemanticChunker

        # Create document
        doc = KnowledgeDocument(
            title=title,
            content=content,
            source_type=source,
        )
        db.add(doc)
        await db.flush()

        # Chunk content
        chunker = SemanticChunker(window_size=500, overlap=50)
        chunks = chunker.process_file(content)

        # Generate embeddings
        embedding_service = await get_embedding_service()
        embeddings = await embedding_service.generate([c.text for c in chunks])

        # Store chunks
        for chunk, embedding in zip(chunks, embeddings, strict=False):
            chunk_obj = KnowledgeChunk(
                document_id=doc.id,
                content=chunk.text,
                embedding=embedding,
                chunk_index=chunk.index,
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

    async def format_as_context(
        self,
        chunks: list[dict],
        max_tokens: int = 2000,
    ) -> str:
        """Format search results as context for LLM"""
        context_parts = []
        total_tokens = 0

        for chunk in chunks:
            content = chunk.get("content", "")
            similarity = chunk.get("similarity", 0)

            # Estimate tokens (rough approximation)
            estimated_tokens = len(content.split()) * 1.3

            if total_tokens + estimated_tokens > max_tokens:
                break

            context_parts.append(f"[Relevance: {similarity:.2f}]\n{content}")
            total_tokens += estimated_tokens

        return "\n\n---\n\n".join(context_parts)

    async def _rerank_chunks(
        self,
        query: str,
        chunks: list[dict],
        top_n: int,
    ) -> list[dict]:
        """Rerank chunks using cross-encoder"""
        # Simplified: just return top by similarity for now
        # In production, use sentence-transformers cross-encoder
        return sorted(chunks, key=lambda x: x.get("similarity", 0), reverse=True)[:top_n]


# Global instance
_knowledge_service: KnowledgeService | None = None


async def get_knowledge_service() -> KnowledgeService:
    """Get or create knowledge service singleton"""
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    return _knowledge_service
