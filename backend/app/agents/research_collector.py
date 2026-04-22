import logging
from datetime import datetime, timezone

from app.agents.base import BaseAgent
from app.core.llm import llm_client
from app.core.model_router import route_task
from app.database import AsyncSessionLocal
from app.models.knowledge import KnowledgeItem
from app.core.embedder import embed_text_async

logger = logging.getLogger(__name__)

class ResearchCollectorAgent(BaseAgent):
    name = "researcher"

    async def run_daily_research(self, topics: list[str]):
        for topic in topics:
            content = f"Research findings for {topic}"
            
            routing = route_task("short_summary")
            summary = await llm_client.complete(
                system="Summarize research findings into a brief digest. <300 tokens.",
                user=content,
                model=routing.model,
                max_tokens=300,
                task_class="short_summary"
            )
            
            if not summary:
                continue
                
            emb = await embed_text_async(summary)
            
            if emb:
                async with AsyncSessionLocal() as db:
                    item = KnowledgeItem(
                        title=f"Research: {topic}",
                        content=summary,
                        category="research",
                        embedding=emb,
                        tags=["research"]
                    )
                    db.add(item)
                    await db.commit()
            
            try:
                from app.core.obsidian_hub import obsidian_hub
                date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                obsidian_hub.write_research(date_str, summary)
            except Exception as e:
                logger.warning(f"Could not write to obsidian hub: {e}")

research_collector_agent = ResearchCollectorAgent()
