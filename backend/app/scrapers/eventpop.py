import logging

import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)
URL = "https://www.eventpop.me/events?category=technology"


class EventpopScraper(BaseScraper):
    source_name = "eventpop"

    def _get_url(self) -> str:
        return URL

    async def fetch(self, url: str) -> httpx.Response | None:
        return await self._safe_fetch(url)

    async def parse(self, response: httpx.Response) -> list[dict]:
        try:
            soup = BeautifulSoup(response.text, "lxml")
            items = []
            for card in soup.select(".event-card, .event-item, [class*='event']")[:15]:
                title_el = card.select_one("h2, h3, .event-name, .title")
                title = title_el.get_text(strip=True) if title_el else ""
                if not title or len(title) < 5:
                    continue
                link_el = card.select_one("a[href]")
                href = link_el.get("href", "") if link_el else ""
                if href and not href.startswith("http"):
                    href = "https://www.eventpop.me" + href
                date_el = card.select_one("time, .date, [class*='date']")
                event_date = date_el.get("datetime") or date_el.get_text(strip=True) if date_el else None
                items.append({"title": title, "source_url": href, "event_date": event_date})
            return items
        except Exception as e:
            logger.error(f"Eventpop parse error: {e}")
            return []

    async def normalize(self, raw_item: dict) -> dict | None:
        if not raw_item.get("title"):
            return None
        source_hash = self._compute_source_hash(raw_item.get("source_url", ""), raw_item.get("title", ""))
        deadline = None
        if raw_item.get("event_date"):
            try:
                from dateutil import parser as dateparser
                deadline = dateparser.parse(raw_item["event_date"]).date().isoformat()
            except Exception:
                pass
        return {
            "type": "hackathon",
            "title": raw_item["title"],
            "source_url": raw_item.get("source_url", ""),
            "deadline": deadline,
            "location_type": "thailand",
            "tags": ["event", "thailand", "tech"],
            "source_hash": source_hash,
            "raw_data": raw_item,
        }
