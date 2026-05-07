import logging

import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)
URL = "https://fastwork.co/category/web-developer?sort=latest"


class FastworkScraper(BaseScraper):
    source_name = "fastwork"

    def _get_url(self) -> str:
        return URL

    async def fetch(self, url: str) -> httpx.Response | None:
        return await self._safe_fetch(url)

    async def parse(self, response: httpx.Response) -> list[dict]:
        try:
            soup = BeautifulSoup(response.text, "lxml")
            items = []
            for card in soup.select(".service-card, .fw-card, [class*='service']")[:15]:
                title_el = card.select_one("h2, h3, .title, .service-title")
                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    continue
                link_el = card.select_one("a[href]")
                href = link_el.get("href", "") if link_el else ""
                if href and not href.startswith("http"):
                    href = "https://fastwork.co" + href
                price_el = card.select_one(".price, .cost, [class*='price']")
                price = price_el.get_text(strip=True) if price_el else None
                items.append({"title": title, "source_url": href, "budget_mentioned": price})
            return items
        except Exception as e:
            logger.error(f"Fastwork parse error: {e}")
            return []

    async def normalize(self, raw_item: dict) -> dict | None:
        if not raw_item.get("title"):
            return None
        source_hash = self._compute_source_hash(raw_item.get("source_url", ""), raw_item.get("title", ""))
        return {
            "type": "freelance",
            "title": raw_item["title"],
            "source_url": raw_item.get("source_url", ""),
            "prize_amount": raw_item.get("budget_mentioned"),
            "location_type": "thailand",
            "tags": ["freelance", "web", "fastwork"],
            "source_hash": source_hash,
            "raw_data": raw_item,
        }
