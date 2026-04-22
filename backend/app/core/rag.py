import logging
from app.database import AsyncSessionLocal
from app.core.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)

class RAGRetriever:
    async def get_context(self, query: str, top_k: int = 5, project_id: str | None = None) -> str:
        try:
            async with AsyncSessionLocal() as db:
                service = KnowledgeService(db)
                results = await service.semantic_search(query, top_k=top_k, project_id=project_id)
                
                if not results:
                    return ""
                    
                await db.commit() # Save use_count updates

                snippets = []
                for res in results:
                    item = res["item"]
                    snippets.append(f"Source: {item.source_path or item.title}\n{item.content}")

                ctx_text = "\n\n".join(snippets)
                
                if len(ctx_text) > 3200:
                    ctx_text = ctx_text[:3200] + "..."
                    
                return f"<context>\n{ctx_text}\n</context>"
        except Exception as e:
            logger.warning(f"Postgres RAG failed, falling back to ObsidianHub: {e}")
            try:
                from app.core.obsidian_hub import obsidian_hub
                return await obsidian_hub.search_vault(query, top_k)
            except Exception as e2:
                logger.error(f"Fallback search also failed: {e2}")
                return ""
