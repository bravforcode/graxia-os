import logging
from datetime import UTC, datetime

from app.agents.base import BaseAgent
from app.core.llm import llm_client
from app.core.model_router import route_task
from app.database import AsyncSessionLocal
from app.models.knowledge import KnowledgeItem
from app.services.embedding_service import get_embedding_service

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
                task_class="short_summary",
            )

            if not summary:
                continue

            embedding_service = await get_embedding_service()
            embs = await embedding_service.generate([summary])
            emb = embs[0] if embs else None

            if emb:
                async with AsyncSessionLocal() as db:
                    item = KnowledgeItem(
                        title=f"Research: {topic}",
                        content=summary,
                        category="research",
                        embedding=emb,
                        tags=["research"],
                    )
                    db.add(item)
                    await db.commit()

            try:
                from app.core.obsidian_hub import obsidian_hub

                date_str = datetime.now(UTC).strftime("%Y-%m-%d")
                obsidian_hub.write_research(date_str, summary)
            except Exception as e:
                logger.warning(f"Could not write to obsidian hub: {e}")


research_collector_agent = ResearchCollectorAgent()
