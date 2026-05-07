"""
LinkedIn Scraper using OpenClaw for browser automation.
Handles job postings and profile scraping with rate limiting.
"""
import logging
from urllib.parse import quote_plus

import httpx

from app.core.openclaw import OpenClawRateLimitError, openclaw_client
from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class LinkedInScraper(BaseScraper):
    """
    LinkedIn job scraper using OpenClaw for browser automation.
    
    Rate limit: 50 requests/day
    Fallback: Basic HTTP scraping (limited data)
    """
    
    source_name = "linkedin"
    
    def __init__(self, keywords: str = "python developer", location: str = "remote"):
        self.keywords = keywords
        self.location = location
        self.use_openclaw = True
    
    def _get_url(self) -> str:
        """Generate LinkedIn jobs search URL."""
        base = "https://www.linkedin.com/jobs/search/"
        params = f"?keywords={quote_plus(self.keywords)}&location={quote_plus(self.location)}"
        return base + params
    
    async def fetch(self, url: str) -> httpx.Response | None:
        """Fetch using OpenClaw or fallback to basic HTTP."""
        if self.use_openclaw:
            try:
                result = await openclaw_client.scrape_url(
                    url=url,
                    platform="linkedin",
                    wait_for_selector=".job-card-container, .jobs-search__results-list",
                    use_cache=True
                )
                
                # Create mock response with scraped HTML
                response = httpx.Response(
                    status_code=200,
                    content=result.get("html", "").encode(),
                    headers={"content-type": "text/html"}
                )
                return response
            except OpenClawRateLimitError:
                logger.warning("LinkedIn OpenClaw rate limit hit, falling back to basic HTTP")
                self.use_openclaw = False
            except Exception as e:
                logger.error(f"LinkedIn OpenClaw scraping failed: {e}")
                self.use_openclaw = False
        
        # Fallback to basic HTTP (will get limited data)
        return await self._safe_fetch(url)
    
    async def parse(self, response: httpx.Response) -> list[dict]:
        """Parse job listings from HTML."""
        try:
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(response.content, "html.parser")
            jobs = []
            
            # Try multiple selectors for job cards
            job_cards = (
                soup.select(".job-card-container") or
                soup.select(".jobs-search__results-list li") or
                soup.select(".job-search-card")
            )
            
            for card in job_cards[:20]:  # Limit to 20 jobs per scrape
                try:
                    job = self._parse_job_card(card)
                    if job:
                        jobs.append(job)
                except Exception as e:
                    logger.warning(f"Failed to parse job card: {e}")
                    continue
            
            logger.info(f"LinkedIn: parsed {len(jobs)} jobs")
            return jobs
        except Exception as e:
            logger.error(f"LinkedIn parse failed: {e}")
            return []
    
    def _parse_job_card(self, card) -> dict | None:
        """Parse individual job card."""
        try:
            # Extract title
            title_elem = (
                card.select_one(".job-card-list__title") or
                card.select_one(".base-search-card__title") or
                card.select_one("h3")
            )
            title = title_elem.get_text(strip=True) if title_elem else None
            
            if not title:
                return None
            
            # Extract company
            company_elem = (
                card.select_one(".job-card-container__company-name") or
                card.select_one(".base-search-card__subtitle") or
                card.select_one(".company-name")
            )
            company = company_elem.get_text(strip=True) if company_elem else None
            
            # Extract location
            location_elem = (
                card.select_one(".job-card-container__metadata-item") or
                card.select_one(".job-search-card__location")
            )
            location = location_elem.get_text(strip=True) if location_elem else None
            
            # Extract URL
            link_elem = card.select_one("a[href*='/jobs/']")
            url = link_elem.get("href") if link_elem else None
            if url and not url.startswith("http"):
                url = f"https://www.linkedin.com{url}"
            
            # Extract description (if available)
            desc_elem = card.select_one(".job-card-list__snippet, .base-search-card__snippet")
            description = desc_elem.get_text(strip=True) if desc_elem else None
            
            return {
                "title": title,
                "company": company,
                "location": location,
                "url": url,
                "description": description,
                "source": "linkedin"
            }
        except Exception as e:
            logger.warning(f"Job card parsing failed: {e}")
            return None
    
    async def normalize(self, raw_item: dict) -> dict | None:
        """Normalize to opportunity schema."""
        try:
            title = raw_item.get("title")
            url = raw_item.get("url")
            
            if not title or not url:
                return None
            
            # Compute source hash for deduplication
            source_hash = self._compute_source_hash(url, title)
            
            return {
                "title": title,
                "company": raw_item.get("company"),
                "source_platform": "linkedin",
                "source_url": url,
                "location": raw_item.get("location"),
                "job_type": "job",
                "description": raw_item.get("description"),
                "source_hash": source_hash,
                "raw_data": raw_item
            }
        except Exception as e:
            logger.warning(f"LinkedIn normalize failed: {e}")
            return None
