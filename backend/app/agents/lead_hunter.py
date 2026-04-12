import logging
from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class LeadHunter(BaseAgent):
    name = "lead_hunter"

    async def run(self) -> int:
        from app.scrapers.fastwork import FastworkScraper
        from app.scrapers.serpapi_search import SerpAPIScraper

        all_raw = []
        try:
            items = await FastworkScraper().run()
            all_raw.extend(items)
        except Exception as e:
            logger.error(f"Fastwork scrape failed: {e}")

        # SerpAPI lead queries
        lead_queries = [
            "hire freelance python developer Thailand 2025",
            "web developer project Bangkok remote 2025",
            "FastAPI backend developer Thailand freelance",
        ]
        for query in lead_queries:
            try:
                scraper = SerpAPIScraper(query=query)
                items = await scraper.run()
                all_raw.extend(items)
            except Exception as e:
                logger.error(f"SerpAPI lead query failed: {e}")

        count = 0
        for raw in all_raw:
            raw["type"] = "freelance"
            try:
                opp_id = await self._save_lead(raw)
                if opp_id:
                    await self.bus.emit("opportunity.found", {"opportunity_id": str(opp_id), "source": "lead_hunter"})
                    count += 1
            except Exception as e:
                logger.error(f"Failed to save lead: {e}")

        logger.info(f"LeadHunter: found {count} leads")
        return count

    async def _save_lead(self, raw: dict):
        from app.database import AsyncSessionLocal
        from app.core.career import upsert_job_posting_from_opportunity
        from app.models.opportunity import Opportunity
        from sqlalchemy import select

        source_hash = raw.get("source_hash")
        if not source_hash:
            return None

        async with AsyncSessionLocal() as db:
            existing = await db.execute(select(Opportunity).where(Opportunity.source_hash == source_hash))
            if existing.scalar_one_or_none():
                return None
            opp = Opportunity(
                type="freelance",
                title=raw.get("title", "Untitled"),
                description=raw.get("description"),
                source_url=raw.get("source_url"),
                source_platform=raw.get("source_platform", "lead_hunter"),
                prize_amount=raw.get("prize_amount"),
                tags=raw.get("tags", []),
                raw_data=raw.get("raw_data", {}),
                source_hash=source_hash,
                status="found",
            )
            db.add(opp)
            await db.commit()
            await db.refresh(opp)
            try:
                await upsert_job_posting_from_opportunity(opp.id)
            except Exception as exc:
                logger.warning("Failed to sync job posting from opportunity %s: %s", opp.id, exc)
            return opp.id
