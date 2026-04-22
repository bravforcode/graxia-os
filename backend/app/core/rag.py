import logging
import math
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.knowledge import KnowledgeItem
from app.core.embedder import embed_text_async

logger = logging.getLogger(__name__)

class RAGRetriever:
    async def get_context(self, query: str, top_k: int = 5, project_id: str | None = None) -> str:
        query_vec = await embed_text_async(query)
        if not query_vec:
            return ""

        async with AsyncSessionLocal() as db:
            stmt = (
                select(KnowledgeItem, KnowledgeItem.embedding.cosine_distance(query_vec).label("distance"))
                .where(KnowledgeItem.is_active == True)
                .filter(KnowledgeItem.embedding.cosine_distance(query_vec) <= 0.28)
            )
            
            if project_id:
                stmt = stmt.filter(KnowledgeItem.tags.contains([f"project:{project_id}"]))
                
            stmt = stmt.order_by(KnowledgeItem.embedding.cosine_distance(query_vec)).limit(top_k * 2)
            
            result = await db.execute(stmt)
            rows = result.all()
            
            if not rows:
                return ""
                
            scored_items = []
            for item, distance in rows:
                similarity = 1.0 - distance
                boost = 1.0 + math.log1p(item.use_count or 0)
                final_score = similarity * boost
                scored_items.append((final_score, item))
            
            scored_items.sort(key=lambda x: x[0], reverse=True)
            items = [item for _, item in scored_items[:top_k]]

            for item in items:
                item.use_count = (item.use_count or 0) + 1
                db.add(item)
            await db.commit()

            snippets = []
            for item in items:
                snippets.append(f"Source: {item.source_path or item.title}\n{item.content}")

            ctx_text = "\n\n".join(snippets)
            
            if len(ctx_text) > 3200:
                ctx_text = ctx_text[:3200] + "..."
                
            return f"<context>\n{ctx_text}\n</context>"
