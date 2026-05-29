"""
Facebook Scraper using OpenClaw for massive group scraping.
"""
import logging
import re
import asyncio
from datetime import datetime, UTC

import httpx
from bs4 import BeautifulSoup

from app.core.openclaw import openclaw_client
from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

class FacebookScraper(BaseScraper):
    """
    Facebook Group Scraper for Brav OS Massive Scraping Engine.
    Target: 500+ posts/day across 10 groups.
    """
    
    source_name = "facebook"
    
    def __init__(self, target_groups: list[str] = None):
        self.target_groups = target_groups or [
            "https://www.facebook.com/share/g/1LVFMct7hR/?mibextid=wwXIfr",
            "https://www.facebook.com/share/g/18SE6B254K/?mibextid=wwXIfr",
            "https://www.facebook.com/share/g/1DLXSAT8W7/?mibextid=wwXIfr",
            "https://www.facebook.com/share/g/1CrX8Zp8xb/?mibextid=wwXIfr",
            "https://www.facebook.com/share/g/1B8mjvuG4Q/?mibextid=wwXIfr",
            "https://www.facebook.com/share/g/1HhAToUqQW/?mibextid=wwXIfr",
        ]
        
        # Condition 1: Owner keywords
        self.owner_keywords = [
            "Owner post", "เจ้าของ", "เจ้าของปล่อยเช่า", "Agent welcome", "Agent wellcome",
            "เจ้าของโพสต์เอง", "เจ้าของโพสเอง", "เจ้าของห้อง", "เจ้าของปล่อยเอง", "ยินดีรับเอเจ้น"
        ]
        
        # Condition 2: Rent keywords
        self.rent_keywords = ["เช่า", "Rent"]
        
        # Contact Patterns
        self.phone_pattern = re.compile(r"0[0-9]{1,2}-?[0-9]{3}-?[0-9]{4}")
        self.line_id_pattern = re.compile(r"line(?:\s*id)?\s*[:\-\s]\s*([a-zA-Z0-9_\-\.]+)", re.IGNORECASE)

    async def run(self) -> list[dict]:
        """Parallelized scraping of all target groups with strict filtering."""
        if await self._is_muted():
            logger.info(f"Scraper {self.source_name}: muted — skipping")
            return []
            
        await self._record_attempt()
        
        tasks = [self.scrape_group(url) for url in self.target_groups]
        results_nested = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_posts = []
        for res in results_nested:
            if isinstance(res, list):
                all_posts.extend(res)
            elif isinstance(res, Exception):
                logger.error(f"Group scraping task failed: {res}")
        
        # Deduplication by both hash and contact info
        deduped = self._dedup(all_posts)
        
        await self._record_result(
            success=True, 
            item_count=len(deduped)
        )
        
        return deduped

    def _dedup(self, posts: list[dict]) -> list[dict]:
        seen_hash = set()
        seen_contact = set()
        deduped = []
        for p in posts:
            h = p.get("source_hash")
            contact = p.get("contact_info")
            contact_key = f"{contact.get('phone')}_{contact.get('line_id')}" if contact else None
            
            if h not in seen_hash:
                if contact_key and contact_key in seen_contact:
                    continue
                
                seen_hash.add(h)
                if contact_key:
                    seen_contact.add(contact_key)
                deduped.append(p)
        return deduped

    async def scrape_group(self, url: str) -> list[dict]:
        """Scrape a single Facebook group using OpenClaw."""
        try:
            logger.info(f"Scraping Facebook Group: {url}")
            result = await openclaw_client.scrape_url(
                url=url,
                platform="facebook",
                wait_for_selector="div[role='feed']",
                use_cache=False
            )
            
            html = result.get("html", "")
            if not html:
                return []
                
            return await self.parse_html(html, url)
            
        except Exception as e:
            logger.error(f"Failed to scrape group {url}: {e}")
            return []

    async def parse_html(self, html: str, group_url: str) -> list[dict]:
        """Parse Facebook group HTML and extract filtered posts."""
        soup = BeautifulSoup(html, "html.parser")
        posts = []
        
        # FB post selectors often change, using a broad approach for role='article'
        articles = soup.select("div[role='article']")
        
        for article in articles:
            try:
                # Extract post text
                text_container = article.select_one("div[data-ad-preview='message']") or article.select_one("div[dir='auto']")
                if not text_container:
                    continue
                    
                content = text_container.get_text(separator=" ", strip=True)
                
                # Apply Filters (Dual-Condition)
                if not self._apply_filters(content):
                    continue
                    
                # Extract Contact (Mandatory)
                contact_info = self._extract_contact(content)
                if not contact_info:
                    continue
                
                # Extract URL (FB post URLs are tricky in HTML, often nested in timestamp)
                post_link = article.select_one("a[href*='/posts/'], a[href*='/groups/'][href*='/permalink/']")
                post_url = post_link.get("href") if post_link else group_url
                if post_url.startswith("/"):
                    post_url = f"https://www.facebook.com{post_url}"
                
                # Normalize
                post_id = self._compute_source_hash(post_url, content)
                
                posts.append({
                    "title": content[:100] + "...",
                    "content": content,
                    "source_url": post_url,
                    "contact_info": contact_info,
                    "source_platform": "facebook",
                    "source_hash": post_id,
                    "extracted_at": datetime.now(UTC).isoformat()
                })
                
            except Exception as e:
                logger.warning(f"Error parsing post: {e}")
                continue
                
        return posts

    def _apply_filters(self, content: str) -> bool:
        """Apply Owner and Rent keyword filters (Dual-Condition)."""
        content_lower = content.lower()
        
        # Condition 1: Owner Keywords
        has_owner = any(kw.lower() in content_lower for kw in self.owner_keywords)
        if not has_owner:
            return False
            
        # Condition 2: Rent Keywords
        has_rent = any(kw.lower() in content_lower for kw in self.rent_keywords)
        if not has_rent:
            return False
            
        return True

    def _extract_contact(self, content: str) -> dict | None:
        """Extract Phone or LINE ID."""
        phone_match = self.phone_pattern.search(content)
        line_match = self.line_id_pattern.search(content)
        
        if not phone_match and not line_match:
            return None
            
        return {
            "phone": phone_match.group(0) if phone_match else None,
            "line_id": line_match.group(1) if line_match else None
        }

    # Override normalize to fit the run() flow if needed, but run() uses parse_html
    async def fetch(self, url: str) -> httpx.Response | None:
        # BaseScraper compatibility, but we use scrape_group for parallelization
        return None

    async def parse(self, response: httpx.Response) -> list[dict]:
        return []

    async def normalize(self, raw_item: dict) -> dict | None:
        return raw_item
