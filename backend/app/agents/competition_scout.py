import logging
import uuid
from app.agents.base import BaseAgent
from app.core.llm import llm_client
from app.core.identity import identity

logger = logging.getLogger(__name__)


class CompetitionScout(BaseAgent):
    name = "competition_scout"

    async def run(self) -> int:
        """Run all competition scrapers, extract with LLM, save, emit events. Returns count found."""
        from app.scrapers.devpost import DevpostScraper
        from app.scrapers.eventpop import EventpopScraper
        from app.scrapers.serpapi_search import SerpAPIScraper
        from app.scrapers.rss_reader import RSSReaderScraper

        all_raw = []
        for scraper_cls in [DevpostScraper, EventpopScraper]:
            try:
                items = await scraper_cls().run()
                all_raw.extend(items)
            except Exception as e:
                logger.error(f"Scraper {scraper_cls.__name__} failed: {e}")

        try:
            serp_items = await SerpAPIScraper.run_all_queries()
            all_raw.extend(serp_items)
        except Exception as e:
            logger.error(f"SerpAPI failed: {e}")

        try:
            rss_items = await RSSReaderScraper.run_all_feeds()
            all_raw.extend(rss_items)
        except Exception as e:
            logger.error(f"RSS failed: {e}")

        count = 0
        for raw in all_raw:
            try:
                opp_id = await self._save_opportunity(raw)
                if opp_id:
                    await self.bus.emit("opportunity.found", {"opportunity_id": str(opp_id), "source": raw.get("source_platform", "unknown")})
                    count += 1
            except Exception as e:
                logger.error(f"Failed to save opportunity: {e}")

        logger.info(f"CompetitionScout: found {count} opportunities")
        return count

    async def _save_opportunity(self, raw: dict):
        from app.database import AsyncSessionLocal
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
                type=raw.get("type", "other"),
                title=raw.get("title", "Untitled"),
                description=raw.get("description"),
                source_url=raw.get("source_url"),
                source_platform=raw.get("source_platform"),
                deadline=raw.get("deadline"),
                prize_amount=raw.get("prize_amount"),
                tags=raw.get("tags", []),
                requirements=raw.get("requirements", []),
                is_student_eligible=raw.get("is_student_eligible"),
                location_type=raw.get("location_type"),
                is_team_allowed=raw.get("is_team_allowed"),
                max_team_size=raw.get("max_team_size"),
                fit_summary=raw.get("fit_summary"),
                raw_data=raw.get("raw_data", {}),
                source_hash=source_hash,
                status="found",
            )
            db.add(opp)
            await db.commit()
            await db.refresh(opp)
            return opp.id
