"""
Fiverr Scraper for buyer requests (jobs posted by clients).
Uses OpenClaw for browser automation with fallback.
"""
import logging
from urllib.parse import quote_plus

import httpx

from app.core.openclaw import OpenClawRateLimitError, openclaw_client
from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class FiverrScraper(BaseScraper):
    """
    Fiverr buyer requests scraper using OpenClaw.
    
    Note: Fiverr buyer requests require login, so this scraper
    focuses on public gig searches that indicate demand.
    
    Rate limit: 100 requests/day (default)
    """
    
    source_name = "fiverr"
    
    def __init__(self, keywords: str = "python development", category: str = "programming-tech"):
        self.keywords = keywords
        self.category = category
        self.use_openclaw = True
    
    def _get_url(self) -> str:
        """Generate Fiverr search URL."""
        base = "https://www.fiverr.com/search/gigs"
        params = f"?query={quote_plus(self.keywords)}&source=top-bar&search_in=everywhere"
        return base + params
    
    async def fetch(self, url: str) -> httpx.Response | None:
        """Fetch using OpenClaw or fallback to basic HTTP."""
        if self.use_openclaw:
            try:
                result = await openclaw_client.scrape_url(
                    url=url,
                    platform="fiverr",
                    wait_for_selector=".gig-card-layout, [data-gig-id]",
                    use_cache=True
                )
                
                response = httpx.Response(
                    status_code=200,
                    content=result.get("html", "").encode(),
                    headers={"content-type": "text/html"}
                )
                return response
            except OpenClawRateLimitError:
                logger.warning("Fiverr OpenClaw rate limit hit, falling back to basic HTTP")
                self.use_openclaw = False
            except Exception as e:
                logger.error(f"Fiverr OpenClaw scraping failed: {e}")
                self.use_openclaw = False
        
        # Fallback to basic HTTP
        return await self._safe_fetch(url)
    
    async def parse(self, response: httpx.Response) -> list[dict]:
        """Parse gig listings (as proxy for demand/opportunities)."""
        try:
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(response.content, "html.parser")
            gigs = []
            
            # Find gig cards
            gig_cards = (
                soup.select(".gig-card-layout") or
                soup.select("[data-gig-id]") or
                soup.select(".gig-wrapper")
            )
            
            for card in gig_cards[:15]:  # Limit to 15 gigs
                try:
                    gig = self._parse_gig_card(card)
                    if gig:
                        gigs.append(gig)
                except Exception as e:
                    logger.warning(f"Failed to parse gig card: {e}")
                    continue
            
            logger.info(f"Fiverr: parsed {len(gigs)} gigs")
            return gigs
        except Exception as e:
            logger.error(f"Fiverr parse failed: {e}")
            return []
    
    def _parse_gig_card(self, card) -> dict | None:
        """Parse individual gig card."""
        try:
            # Extract title
            title_elem = (
                card.select_one(".gig-card-layout__title") or
                card.select_one("h3") or
                card.select_one("a[data-impression-collected]")
            )
            title = title_elem.get_text(strip=True) if title_elem else None
            
            if not title:
                return None
            
            # Extract seller name (as "company")
            seller_elem = (
                card.select_one(".seller-name") or
                card.select_one(".username")
            )
            seller = seller_elem.get_text(strip=True) if seller_elem else "Fiverr Seller"
            
            # Extract URL
            link_elem = card.select_one("a[href*='/gigs/']")
            url = link_elem.get("href") if link_elem else None
            if url and not url.startswith("http"):
                url = f"https://www.fiverr.com{url}"
            
            # Extract price
            price_elem = card.select_one(".price, .gig-price")
            price = price_elem.get_text(strip=True) if price_elem else None
            
            # Extract rating
            rating_elem = card.select_one(".rating-score, .gig-rating")
            rating = rating_elem.get_text(strip=True) if rating_elem else None
            
            # Extract tags/skills
            tags = []
            tag_elems = card.select(".tag, .gig-tag")
            for tag_elem in tag_elems:
                tag = tag_elem.get_text(strip=True)
                if tag:
                    tags.append(tag)
            
            return {
                "title": title,
                "seller": seller,
                "url": url,
                "price": price,
                "rating": rating,
                "tags": tags,
                "source": "fiverr"
            }
        except Exception as e:
            logger.warning(f"Gig card parsing failed: {e}")
            return None
    
    async def normalize(self, raw_item: dict) -> dict | None:
        """
        Normalize to opportunity schema.
        
        Note: Fiverr gigs represent market demand, not direct job postings.
        We convert them to "opportunities" to track what skills are in demand.
        """
        try:
            title = raw_item.get("title")
            url = raw_item.get("url")
            
            if not title or not url:
                return None
            
            source_hash = self._compute_source_hash(url, title)
            
            # Convert gig to opportunity format
            # Title becomes "Market demand: [original title]"
            opportunity_title = f"Market demand: {title}"
            
            # Extract skills from tags
            skills = raw_item.get("tags", [])
            
            return {
                "title": opportunity_title,
                "company": raw_item.get("seller", "Fiverr Market"),
                "source_platform": "fiverr",
                "source_url": url,
                "location": "Remote",
                "job_type": "freelance",
                "description": f"Fiverr gig: {title}. Price: {raw_item.get('price', 'N/A')}. Rating: {raw_item.get('rating', 'N/A')}",
                "required_skills": skills,
                "source_hash": source_hash,
                "raw_data": raw_item
            }
        except Exception as e:
            logger.warning(f"Fiverr normalize failed: {e}")
            return None
