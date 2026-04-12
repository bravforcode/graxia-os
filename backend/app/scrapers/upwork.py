"""
Upwork Scraper using OpenClaw for browser automation.
Handles freelance job postings with rate limiting.
"""
import logging
from typing import Optional
from urllib.parse import quote_plus

import httpx

from app.core.openclaw import openclaw_client, OpenClawRateLimitError
from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class UpworkScraper(BaseScraper):
    """
    Upwork freelance job scraper using OpenClaw.
    
    Rate limit: 100 requests/day (default)
    Fallback: RSS feed (limited data)
    """
    
    source_name = "upwork"
    
    def __init__(self, keywords: str = "python", category: str = "web-mobile-software-dev"):
        self.keywords = keywords
        self.category = category
        self.use_openclaw = True
    
    def _get_url(self) -> str:
        """Generate Upwork search URL."""
        base = "https://www.upwork.com/nx/search/jobs/"
        params = f"?q={quote_plus(self.keywords)}&category2_uid={self.category}"
        return base + params
    
    async def fetch(self, url: str) -> Optional[httpx.Response]:
        """Fetch using OpenClaw or fallback to RSS."""
        if self.use_openclaw:
            try:
                result = await openclaw_client.scrape_url(
                    url=url,
                    platform="upwork",
                    wait_for_selector="[data-test='job-tile'], .job-tile",
                    use_cache=True
                )
                
                response = httpx.Response(
                    status_code=200,
                    content=result.get("html", "").encode(),
                    headers={"content-type": "text/html"}
                )
                return response
            except OpenClawRateLimitError:
                logger.warning("Upwork OpenClaw rate limit hit, falling back to RSS")
                self.use_openclaw = False
            except Exception as e:
                logger.error(f"Upwork OpenClaw scraping failed: {e}")
                self.use_openclaw = False
        
        # Fallback to RSS feed
        rss_url = f"https://www.upwork.com/ab/feed/jobs/rss?q={quote_plus(self.keywords)}"
        return await self._safe_fetch(rss_url)
    
    async def parse(self, response: httpx.Response) -> list[dict]:
        """Parse job listings from HTML or RSS."""
        content_type = response.headers.get("content-type", "")
        
        if "xml" in content_type or "rss" in content_type:
            return await self._parse_rss(response)
        else:
            return await self._parse_html(response)
    
    async def _parse_html(self, response: httpx.Response) -> list[dict]:
        """Parse jobs from HTML."""
        try:
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(response.content, "html.parser")
            jobs = []
            
            job_tiles = soup.select("[data-test='job-tile'], .job-tile, .up-card-section")
            
            for tile in job_tiles[:20]:
                try:
                    job = self._parse_job_tile(tile)
                    if job:
                        jobs.append(job)
                except Exception as e:
                    logger.warning(f"Failed to parse job tile: {e}")
                    continue
            
            logger.info(f"Upwork: parsed {len(jobs)} jobs from HTML")
            return jobs
        except Exception as e:
            logger.error(f"Upwork HTML parse failed: {e}")
            return []
    
    async def _parse_rss(self, response: httpx.Response) -> list[dict]:
        """Parse jobs from RSS feed."""
        try:
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(response.content, "xml")
            jobs = []
            
            for item in soup.find_all("item")[:20]:
                try:
                    title = item.find("title").get_text(strip=True) if item.find("title") else None
                    link = item.find("link").get_text(strip=True) if item.find("link") else None
                    description = item.find("description").get_text(strip=True) if item.find("description") else None
                    pub_date = item.find("pubDate").get_text(strip=True) if item.find("pubDate") else None
                    
                    if title and link:
                        jobs.append({
                            "title": title,
                            "url": link,
                            "description": description,
                            "posted_date": pub_date,
                            "source": "upwork"
                        })
                except Exception as e:
                    logger.warning(f"Failed to parse RSS item: {e}")
                    continue
            
            logger.info(f"Upwork: parsed {len(jobs)} jobs from RSS")
            return jobs
        except Exception as e:
            logger.error(f"Upwork RSS parse failed: {e}")
            return []
    
    def _parse_job_tile(self, tile) -> Optional[dict]:
        """Parse individual job tile from HTML."""
        try:
            # Extract title
            title_elem = (
                tile.select_one("[data-test='job-tile-title']") or
                tile.select_one(".job-title") or
                tile.select_one("h4, h3")
            )
            title = title_elem.get_text(strip=True) if title_elem else None
            
            if not title:
                return None
            
            # Extract URL
            link_elem = tile.select_one("a[href*='/jobs/']")
            url = link_elem.get("href") if link_elem else None
            if url and not url.startswith("http"):
                url = f"https://www.upwork.com{url}"
            
            # Extract description
            desc_elem = (
                tile.select_one("[data-test='job-description']") or
                tile.select_one(".job-description")
            )
            description = desc_elem.get_text(strip=True) if desc_elem else None
            
            # Extract budget/rate
            budget_elem = tile.select_one("[data-test='budget'], .budget")
            budget = budget_elem.get_text(strip=True) if budget_elem else None
            
            # Extract skills
            skills = []
            skill_elems = tile.select("[data-test='token'], .skill-tag")
            for skill_elem in skill_elems:
                skill = skill_elem.get_text(strip=True)
                if skill:
                    skills.append(skill)
            
            return {
                "title": title,
                "url": url,
                "description": description,
                "budget": budget,
                "skills": skills,
                "source": "upwork"
            }
        except Exception as e:
            logger.warning(f"Job tile parsing failed: {e}")
            return None
    
    async def normalize(self, raw_item: dict) -> Optional[dict]:
        """Normalize to opportunity schema."""
        try:
            title = raw_item.get("title")
            url = raw_item.get("url")
            
            if not title or not url:
                return None
            
            source_hash = self._compute_source_hash(url, title)
            
            # Extract skills from description if not already present
            skills = raw_item.get("skills", [])
            if not skills and raw_item.get("description"):
                # Simple keyword extraction
                desc_lower = raw_item["description"].lower()
                common_skills = ["python", "javascript", "react", "node", "django", "fastapi", "sql", "aws"]
                skills = [s for s in common_skills if s in desc_lower]
            
            return {
                "title": title,
                "company": "Upwork Client",
                "source_platform": "upwork",
                "source_url": url,
                "location": "Remote",
                "job_type": "freelance",
                "description": raw_item.get("description"),
                "required_skills": skills,
                "source_hash": source_hash,
                "raw_data": raw_item
            }
        except Exception as e:
            logger.warning(f"Upwork normalize failed: {e}")
            return None
