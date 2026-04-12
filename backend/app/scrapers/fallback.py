"""
Fallback Scrapers

Direct HTTP scraping when OpenClaw is unavailable.
"""
import hashlib
import logging
from typing import Optional
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class FallbackScraper:
    """Base class for fallback scrapers using direct HTTP."""
    
    def __init__(self, source_name: str):
        self.source_name = source_name
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
    
    def _calculate_hash(self, source: str, source_id: str) -> str:
        """Calculate SHA256 hash for deduplication."""
        content = f"{source}:{source_id}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    async def fetch_html(self, url: str, timeout: int = 30) -> Optional[str]:
        """Fetch HTML content from URL."""
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, headers=self.headers, follow_redirects=True)
                response.raise_for_status()
                return response.text
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None


class LinkedInFallbackScraper(FallbackScraper):
    """
    Fallback scraper for LinkedIn using RSS feeds.
    
    Note: LinkedIn blocks direct scraping, so we use RSS feeds
    which have limited data but don't require authentication.
    """
    
    def __init__(self):
        super().__init__("linkedin_fallback")
    
    async def run(self, keywords: str = "python developer") -> list[dict]:
        """
        Scrape LinkedIn jobs via RSS feed.
        
        Note: RSS feeds have limited data (title, link, date only)
        """
        jobs = []
        
        try:
            # LinkedIn RSS feed URL (public, no auth required)
            # Format: https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=python&location=remote
            url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={keywords}&location=remote&f_TPR=r86400"
            
            html = await self.fetch_html(url)
            if not html:
                return jobs
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Parse job cards
            job_cards = soup.find_all('li', class_='result-card')
            
            for card in job_cards[:10]:  # Limit to 10
                try:
                    title_elem = card.find('h3', class_='result-card__title')
                    company_elem = card.find('h4', class_='result-card__subtitle')
                    location_elem = card.find('span', class_='job-result-card__location')
                    link_elem = card.find('a', class_='result-card__full-card-link')
                    
                    if not title_elem or not link_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    company = company_elem.get_text(strip=True) if company_elem else "Unknown"
                    location = location_elem.get_text(strip=True) if location_elem else "Remote"
                    url = link_elem.get('href', '')
                    
                    # Extract job ID from URL
                    job_id = url.split('/')[-1].split('?')[0] if url else None
                    
                    if not job_id:
                        continue
                    
                    jobs.append({
                        "title": title,
                        "company": company,
                        "location": location,
                        "source_platform": "linkedin",
                        "source_url": url,
                        "source_hash": self._calculate_hash("linkedin", job_id),
                        "job_type": "job",
                        "description": f"Job found via LinkedIn RSS feed. Visit URL for full details.",
                        "required_skills": [],
                        "raw_data": {
                            "scraped_at": datetime.now(timezone.utc).isoformat(),
                            "scraper": "fallback"
                        }
                    })
                except Exception as e:
                    logger.warning(f"Failed to parse job card: {e}")
                    continue
            
            logger.info(f"LinkedIn fallback scraper found {len(jobs)} jobs")
        except Exception as e:
            logger.error(f"LinkedIn fallback scraper failed: {e}")
        
        return jobs


class UpworkFallbackScraper(FallbackScraper):
    """
    Fallback scraper for Upwork using RSS feeds.
    
    Upwork provides RSS feeds for job searches.
    """
    
    def __init__(self):
        super().__init__("upwork_fallback")
    
    async def run(self, keywords: str = "python") -> list[dict]:
        """Scrape Upwork jobs via RSS feed."""
        jobs = []
        
        try:
            # Upwork RSS feed URL
            url = f"https://www.upwork.com/ab/feed/jobs/rss?q={keywords}&sort=recency"
            
            html = await self.fetch_html(url)
            if not html:
                return jobs
            
            soup = BeautifulSoup(html, 'xml')
            
            # Parse RSS items
            items = soup.find_all('item')
            
            for item in items[:10]:  # Limit to 10
                try:
                    title = item.find('title').get_text(strip=True) if item.find('title') else None
                    link = item.find('link').get_text(strip=True) if item.find('link') else None
                    description = item.find('description').get_text(strip=True) if item.find('description') else ""
                    pub_date = item.find('pubDate').get_text(strip=True) if item.find('pubDate') else None
                    
                    if not title or not link:
                        continue
                    
                    # Extract job ID from URL
                    job_id = link.split('/')[-1].split('?')[0] if link else None
                    
                    if not job_id:
                        continue
                    
                    jobs.append({
                        "title": title,
                        "company": "Upwork Client",
                        "location": "Remote",
                        "source_platform": "upwork",
                        "source_url": link,
                        "source_hash": self._calculate_hash("upwork", job_id),
                        "job_type": "freelance",
                        "description": description[:500],
                        "required_skills": [],
                        "raw_data": {
                            "pub_date": pub_date,
                            "scraped_at": datetime.now(timezone.utc).isoformat(),
                            "scraper": "fallback"
                        }
                    })
                except Exception as e:
                    logger.warning(f"Failed to parse RSS item: {e}")
                    continue
            
            logger.info(f"Upwork fallback scraper found {len(jobs)} jobs")
        except Exception as e:
            logger.error(f"Upwork fallback scraper failed: {e}")
        
        return jobs


class FiverrFallbackScraper(FallbackScraper):
    """
    Fallback scraper for Fiverr.
    
    Scrapes Fiverr search results directly.
    """
    
    def __init__(self):
        super().__init__("fiverr_fallback")
    
    async def run(self, keywords: str = "python development") -> list[dict]:
        """Scrape Fiverr gigs."""
        jobs = []
        
        try:
            # Fiverr search URL
            url = f"https://www.fiverr.com/search/gigs?query={keywords}&source=top-bar&search_in=everywhere"
            
            html = await self.fetch_html(url)
            if not html:
                return jobs
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Parse gig cards
            gig_cards = soup.find_all('div', class_='gig-card-layout')
            
            for card in gig_cards[:10]:  # Limit to 10
                try:
                    title_elem = card.find('h3')
                    seller_elem = card.find('div', class_='seller-name')
                    link_elem = card.find('a', class_='gig-link')
                    
                    if not title_elem or not link_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    seller = seller_elem.get_text(strip=True) if seller_elem else "Unknown"
                    link = "https://www.fiverr.com" + link_elem.get('href', '')
                    
                    # Extract gig ID from URL
                    gig_id = link.split('/')[-1].split('?')[0] if link else None
                    
                    if not gig_id:
                        continue
                    
                    jobs.append({
                        "title": title,
                        "company": f"Fiverr - {seller}",
                        "location": "Remote",
                        "source_platform": "fiverr",
                        "source_url": link,
                        "source_hash": self._calculate_hash("fiverr", gig_id),
                        "job_type": "gig",
                        "description": f"Fiverr gig by {seller}. Visit URL for full details.",
                        "required_skills": [],
                        "raw_data": {
                            "seller": seller,
                            "scraped_at": datetime.now(timezone.utc).isoformat(),
                            "scraper": "fallback"
                        }
                    })
                except Exception as e:
                    logger.warning(f"Failed to parse gig card: {e}")
                    continue
            
            logger.info(f"Fiverr fallback scraper found {len(jobs)} jobs")
        except Exception as e:
            logger.error(f"Fiverr fallback scraper failed: {e}")
        
        return jobs


# Fallback scraper instances
linkedin_fallback = LinkedInFallbackScraper()
upwork_fallback = UpworkFallbackScraper()
fiverr_fallback = FiverrFallbackScraper()
