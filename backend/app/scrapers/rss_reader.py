import logging
from typing import Optional
import httpx
from xml.etree import ElementTree as ET
from .base import BaseScraper

logger = logging.getLogger(__name__)

RSS_FEEDS = [
    ("https://devpost.com/hackathons.rss", "devpost_rss"),
    ("https://www.f6s.com/programs.rss", "f6s_rss"),
]


class RSSReaderScraper(BaseScraper):
    source_name = "rss_reader"

    def __init__(self, feed_url: Optional[str] = None, feed_name: Optional[str] = None) -> None:
        self._feed_url = feed_url or RSS_FEEDS[0][0]
        if feed_name:
            self.source_name = feed_name

    def _get_url(self) -> str:
        return self._feed_url

    async def fetch(self, url: str) -> Optional[httpx.Response]:
        return await self._safe_fetch(url)

    async def parse(self, response: httpx.Response) -> list[dict]:
        try:
            root = ET.fromstring(response.content)
            ns = ""
            items = []
            for item in root.findall(".//item")[:20]:
                title_el = item.find("title")
                link_el = item.find("link")
                desc_el = item.find("description")
                pub_el = item.find("pubDate")
                title = title_el.text.strip() if title_el is not None and title_el.text else ""
                if not title:
                    continue
                items.append({
                    "title": title,
                    "source_url": link_el.text.strip() if link_el is not None and link_el.text else "",
                    "description": desc_el.text.strip() if desc_el is not None and desc_el.text else "",
                    "pub_date": pub_el.text.strip() if pub_el is not None and pub_el.text else None,
                })
            return items
        except Exception as e:
            logger.error(f"RSS parse error: {e}")
            return []

    async def normalize(self, raw_item: dict) -> Optional[dict]:
        if not raw_item.get("title"):
            return None
        source_hash = self._compute_source_hash(raw_item.get("source_url", ""), raw_item.get("title", ""))
        deadline = None
        if raw_item.get("pub_date"):
            try:
                from dateutil import parser as dateparser
                deadline = dateparser.parse(raw_item["pub_date"]).date().isoformat()
            except Exception:
                pass
        return {
            "type": "hackathon",
            "title": raw_item["title"],
            "source_url": raw_item.get("source_url", ""),
            "description": raw_item.get("description", "")[:500],
            "deadline": deadline,
            "location_type": "online",
            "tags": ["rss", self.source_name],
            "source_hash": source_hash,
            "raw_data": raw_item,
        }

    @classmethod
    async def run_all_feeds(cls) -> list[dict]:
        all_results = []
        for feed_url, feed_name in RSS_FEEDS:
            scraper = cls(feed_url=feed_url, feed_name=feed_name)
            results = await scraper.run()
            all_results.extend(results)
        return all_results
