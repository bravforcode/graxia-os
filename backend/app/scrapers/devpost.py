import logging

import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper

logger = logging.getLogger(__name__)
URL = "https://devpost.com/hackathons?open_to[]=students&order_by=recently-added"


class DevpostScraper(BaseScraper):
    source_name = "devpost"

    def _get_url(self) -> str:
        return URL

    async def fetch(self, url: str) -> httpx.Response | None:
        return await self._safe_fetch(url)

    async def parse(self, response: httpx.Response) -> list[dict]:
        try:
            soup = BeautifulSoup(response.text, "lxml")
            items = []
            for card in soup.select(".hackathon-tile, [data-challenge-id]")[:20]:
                title_el = card.select_one("h2, .title, .challenge-title")
                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    continue
                link_el = card.select_one("a[href]")
                href = link_el.get("href", "") if link_el else ""
                if href and not href.startswith("http"):
                    href = "https://devpost.com" + href
                prize_el = card.select_one(".prize, .prize-amount, [class*='prize']")
                prize = prize_el.get_text(strip=True) if prize_el else None
                deadline_el = card.select_one("[data-deadline], .deadline, time")
                deadline = deadline_el.get("data-deadline") or deadline_el.get("datetime") if deadline_el else None
                items.append({"title": title, "source_url": href, "prize_amount": prize, "deadline_raw": deadline})
            return items
        except Exception as e:
            logger.error(f"Devpost parse error: {e}")
            return []

    async def normalize(self, raw_item: dict) -> dict | None:
        if not raw_item.get("title"):
            return None
        source_hash = self._compute_source_hash(raw_item.get("source_url", ""), raw_item.get("title", ""))
        deadline = None
        if raw_item.get("deadline_raw"):
            try:
                from dateutil import parser as dateparser
                deadline = dateparser.parse(raw_item["deadline_raw"]).date().isoformat()
            except Exception:
                pass
        return {
            "type": "hackathon",
            "title": raw_item["title"],
            "source_url": raw_item.get("source_url", ""),
            "prize_amount": raw_item.get("prize_amount"),
            "deadline": deadline,
            "location_type": "online",
            "is_student_eligible": True,
            "tags": ["hackathon", "devpost"],
            "source_hash": source_hash,
            "raw_data": raw_item,
        }
