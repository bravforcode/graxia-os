import logging
from typing import Optional
import httpx
from .base import BaseScraper
from app.config import settings

logger = logging.getLogger(__name__)

SEARCH_QUERIES = [
    "hackathon Thailand 2025 prize students",
    "startup competition Thailand 2025",
    "grant program developer Thailand 2025",
    "NSTDA NECTEC DEPA grant startup 2025",
    "fellowship program developer ASEAN 2025",
    "accelerator program Thailand student 2025",
]


class SerpAPIScraper(BaseScraper):
    source_name = "serpapi"

    def __init__(self, query: Optional[str] = None) -> None:
        self._query = query or SEARCH_QUERIES[0]

    def _get_url(self) -> str:
        return f"https://serpapi.com/search.json?q={self._query}&api_key={settings.SERPAPI_KEY}&num=10&hl=en&gl=th"

    async def fetch(self, url: str) -> Optional[httpx.Response]:
        if not settings.SERPAPI_KEY:
            logger.info("SerpAPI: no key — skipping")
            return None
        return await self._safe_fetch(url)

    async def parse(self, response: httpx.Response) -> list[dict]:
        try:
            data = response.json()
            results = data.get("organic_results", [])
            return [
                {"title": r.get("title", ""), "source_url": r.get("link", ""), "snippet": r.get("snippet", "")}
                for r in results
                if r.get("title")
            ]
        except Exception as e:
            logger.error(f"SerpAPI parse error: {e}")
            return []

    async def normalize(self, raw_item: dict) -> Optional[dict]:
        title = raw_item.get("title", "")
        if not title:
            return None
        source_hash = self._compute_source_hash(raw_item.get("source_url", ""), title)
        query_lower = self._query.lower()
        opp_type = "other"
        if "hackathon" in query_lower:
            opp_type = "hackathon"
        elif "startup competition" in query_lower:
            opp_type = "competition"
        elif "grant" in query_lower:
            opp_type = "grant"
        elif "accelerator" in query_lower:
            opp_type = "accelerator"
        elif "fellowship" in query_lower:
            opp_type = "fellowship"
        return {
            "type": opp_type,
            "title": title,
            "source_url": raw_item.get("source_url", ""),
            "description": raw_item.get("snippet", ""),
            "location_type": "thailand",
            "tags": ["search", opp_type],
            "source_hash": source_hash,
            "raw_data": raw_item,
        }

    @classmethod
    async def run_all_queries(cls) -> list[dict]:
        all_results = []
        for query in SEARCH_QUERIES:
            scraper = cls(query=query)
            results = await scraper.run()
            all_results.extend(results)
        return all_results
