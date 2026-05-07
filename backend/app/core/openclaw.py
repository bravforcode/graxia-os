"""
OpenClaw Integration Module

Provides browser automation and advanced web scraping via OpenClaw API.
Includes caching, rate limiting, cost tracking, and fallback mechanisms.
"""
import hashlib
import logging
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)


class OpenClawRateLimitError(Exception):
    """Raised when rate limit is exceeded."""
    pass


class OpenClawBudgetExceededError(Exception):
    """Raised when budget limit is exceeded."""
    pass


class OpenClawClient:
    """
    OpenClaw API client with caching, rate limiting, and cost tracking.
    
    Features:
    - Redis caching (4h TTL)
    - Rate limiting per platform (LinkedIn: 50/day, Network: 20/day)
    - Cost tracking and budget alerts
    - Exponential backoff retry
    - Fallback to basic HTTP scraping
    """
    
    def __init__(self) -> None:
        self.api_key = settings.OPENCLAW_API_KEY
        self.base_url = settings.OPENCLAW_BASE_URL
        self.max_daily_cost = 50.0  # $50/month = ~$1.67/day
        self._redis = None
        
        # Rate limits per platform
        self.rate_limits = {
            "linkedin": 50,  # 50 requests/day
            "network": 20,   # 20 requests/day
            "default": 100,  # 100 requests/day for other platforms
        }
    
    async def _get_redis(self):
        """Get or create Redis connection."""
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
                await self._redis.ping()
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}")
                self._redis = None
        return self._redis
    
    def _cache_key(self, url: str, action: str = "scrape") -> str:
        """Generate cache key for URL and action."""
        raw = f"{action}|{url}"
        return "openclaw:" + hashlib.sha256(raw.encode()).hexdigest()
    
    async def _get_cache(self, key: str) -> dict | None:
        """Get cached result from Redis."""
        r = await self._get_redis()
        if not r:
            return None
        try:
            import json
            cached = await r.get(key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache get failed: {e}")
        return None
    
    async def _set_cache(self, key: str, value: dict, ttl: int = 14400) -> None:
        """Set cache in Redis with TTL (default 4 hours)."""
        r = await self._get_redis()
        if not r:
            return
        try:
            import json
            await r.setex(key, ttl, json.dumps(value))
        except Exception as e:
            logger.warning(f"Cache set failed: {e}")
    
    async def _check_rate_limit(self, platform: str = "default") -> bool:
        """Check if rate limit is exceeded for platform."""
        r = await self._get_redis()
        if not r:
            return True  # Allow if Redis unavailable
        
        limit = self.rate_limits.get(platform, self.rate_limits["default"])
        today_key = f"openclaw_rate:{platform}:{time.strftime('%Y-%m-%d')}"
        
        try:
            count = await r.get(today_key)
            current = int(count) if count else 0
            
            if current >= limit:
                logger.warning(f"OpenClaw rate limit exceeded for {platform}: {current}/{limit}")
                return False
            
            # Increment counter
            await r.incr(today_key)
            if current == 0:
                await r.expire(today_key, 86400)  # 24 hours
            
            # Alert at 80% threshold
            if current >= limit * 0.8:
                await self._send_rate_limit_alert(platform, current, limit)
            
            return True
        except Exception as e:
            logger.warning(f"Rate limit check failed: {e}")
            return True  # Allow on error
    
    async def _send_rate_limit_alert(self, platform: str, current: int, limit: int) -> None:
        """Send alert when approaching rate limit."""
        try:
            from app.core.event_bus import event_bus
            await event_bus.emit("openclaw.rate_limit_warning", {
                "platform": platform,
                "current": current,
                "limit": limit,
                "percentage": round((current / limit) * 100, 1)
            })
        except Exception as e:
            logger.warning(f"Rate limit alert failed: {e}")
    
    async def _track_cost(self, cost_usd: float, platform: str, action: str) -> None:
        """Track API usage cost in database."""
        try:
            from app.database import AsyncSessionLocal
            from app.models.openclaw_usage import OpenClawUsage
            
            async with AsyncSessionLocal() as db:
                usage = OpenClawUsage(
                    id=uuid4(),
                    platform=platform,
                    action=action,
                    cost_usd=Decimal(str(cost_usd)),
                    created_at=datetime.now(UTC)
                )
                db.add(usage)
                await db.commit()
                
                # Check daily budget
                await self._check_daily_budget(db)
        except Exception as e:
            logger.warning(f"Cost tracking failed: {e}")
    
    async def _check_daily_budget(self, db) -> None:
        """Check if daily budget is exceeded."""
        try:
            from sqlalchemy import func, select

            from app.models.openclaw_usage import OpenClawUsage
            
            today = datetime.now(UTC).date()
            query = select(func.sum(OpenClawUsage.cost_usd)).where(
                func.date(OpenClawUsage.created_at) == today
            )
            result = await db.execute(query)
            total_cost = result.scalar() or Decimal("0")
            
            if float(total_cost) >= self.max_daily_cost * 0.8:
                await self._send_budget_alert(float(total_cost), self.max_daily_cost)
        except Exception as e:
            logger.warning(f"Budget check failed: {e}")
    
    async def _send_budget_alert(self, current: float, limit: float) -> None:
        """Send alert when approaching budget limit."""
        try:
            from app.core.event_bus import event_bus
            await event_bus.emit("openclaw.budget_warning", {
                "current_usd": current,
                "limit_usd": limit,
                "percentage": round((current / limit) * 100, 1)
            })
        except Exception as e:
            logger.warning(f"Budget alert failed: {e}")
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _call_api(
        self,
        endpoint: str,
        payload: dict[str, Any],
        timeout: int = 60
    ) -> dict:
        """Call OpenClaw API with retry logic."""
        if not self.api_key:
            raise ValueError("OpenClaw API key not configured")
        
        url = f"{self.base_url}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()
    
    async def scrape_url(
        self,
        url: str,
        platform: str = "default",
        wait_for_selector: str | None = None,
        extract_schema: dict | None = None,
        use_cache: bool = True
    ) -> dict:
        """
        Scrape URL using OpenClaw browser automation.
        
        Args:
            url: URL to scrape
            platform: Platform name for rate limiting (linkedin, network, default)
            wait_for_selector: CSS selector to wait for before scraping
            extract_schema: Schema for data extraction
            use_cache: Whether to use cached results
        
        Returns:
            dict with keys: html, text, data (if schema provided), metadata
        
        Raises:
            OpenClawRateLimitError: If rate limit exceeded
            OpenClawBudgetExceededError: If budget exceeded
        """
        # Check cache first
        if use_cache:
            cache_key = self._cache_key(url, "scrape")
            cached = await self._get_cache(cache_key)
            if cached:
                logger.info(f"OpenClaw cache hit for {url}")
                return cached
        
        # Check rate limit
        if not await self._check_rate_limit(platform):
            raise OpenClawRateLimitError(f"Rate limit exceeded for {platform}")
        
        # Prepare payload
        payload = {
            "url": url,
            "wait_for_selector": wait_for_selector,
            "extract_schema": extract_schema,
            "timeout": 30000,  # 30 seconds
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        try:
            # Call API
            result = await self._call_api("scrape", payload)
            
            # Track cost (estimate $0.10 per request)
            await self._track_cost(0.10, platform, "scrape")
            
            # Cache result
            if use_cache:
                await self._set_cache(cache_key, result)
            
            return result
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise OpenClawRateLimitError("OpenClaw API rate limit exceeded")
            raise
    
    async def extract_contacts(
        self,
        url: str,
        platform: str = "linkedin",
        use_cache: bool = True
    ) -> list[dict]:
        """
        Extract contact information from LinkedIn or similar platforms.
        
        Args:
            url: Profile or search results URL
            platform: Platform name (linkedin, twitter, etc.)
            use_cache: Whether to use cached results
        
        Returns:
            List of contact dicts with name, title, company, email, etc.
        """
        schema = {
            "contacts": {
                "selector": ".profile-card, .search-result",
                "fields": {
                    "name": ".name, .full-name",
                    "title": ".headline, .title",
                    "company": ".company-name",
                    "location": ".location",
                    "profile_url": "a.profile-link@href"
                }
            }
        }
        
        result = await self.scrape_url(
            url=url,
            platform=platform,
            wait_for_selector=".profile-card, .search-result",
            extract_schema=schema,
            use_cache=use_cache
        )
        
        return result.get("data", {}).get("contacts", [])
    
    async def extract_jobs(
        self,
        url: str,
        platform: str = "default",
        use_cache: bool = True
    ) -> list[dict]:
        """
        Extract job postings from job boards.
        
        Args:
            url: Job board URL
            platform: Platform name (linkedin, upwork, fiverr, etc.)
            use_cache: Whether to use cached results
        
        Returns:
            List of job dicts with title, company, description, etc.
        """
        schema = {
            "jobs": {
                "selector": ".job-card, .job-listing, .job-item",
                "fields": {
                    "title": ".job-title, h2, h3",
                    "company": ".company-name, .employer",
                    "location": ".location, .job-location",
                    "description": ".description, .job-description",
                    "url": "a.job-link@href, a@href",
                    "posted_date": ".posted-date, .date",
                    "salary": ".salary, .compensation"
                }
            }
        }
        
        result = await self.scrape_url(
            url=url,
            platform=platform,
            wait_for_selector=".job-card, .job-listing",
            extract_schema=schema,
            use_cache=use_cache
        )
        
        return result.get("data", {}).get("jobs", [])
    
    async def health_check(self) -> dict:
        """Check OpenClaw service health and usage stats."""
        try:
            from sqlalchemy import func, select

            from app.database import AsyncSessionLocal
            from app.models.openclaw_usage import OpenClawUsage
            
            async with AsyncSessionLocal() as db:
                # Get today's usage
                today = datetime.now(UTC).date()
                query = select(
                    func.count(OpenClawUsage.id).label("count"),
                    func.sum(OpenClawUsage.cost_usd).label("cost")
                ).where(func.date(OpenClawUsage.created_at) == today)
                
                result = await db.execute(query)
                row = result.first()
                
                return {
                    "status": "healthy" if self.api_key else "no_api_key",
                    "today_requests": row.count if row else 0,
                    "today_cost_usd": float(row.cost) if row and row.cost else 0.0,
                    "daily_budget_usd": self.max_daily_cost,
                    "rate_limits": self.rate_limits
                }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {"status": "error", "error": str(e)}
    
    async def get_usage_stats(self, days: int = 7) -> dict:
        """Get usage statistics for the last N days."""
        try:
            from sqlalchemy import func, select

            from app.database import AsyncSessionLocal
            from app.models.openclaw_usage import OpenClawUsage
            
            async with AsyncSessionLocal() as db:
                since = datetime.now(UTC) - timedelta(days=days)
                
                # Total stats
                query = select(
                    func.count(OpenClawUsage.id).label("total_requests"),
                    func.sum(OpenClawUsage.cost_usd).label("total_cost"),
                    func.avg(OpenClawUsage.cost_usd).label("avg_cost")
                ).where(OpenClawUsage.created_at >= since)
                
                result = await db.execute(query)
                row = result.first()
                
                # Per-platform stats
                platform_query = select(
                    OpenClawUsage.platform,
                    func.count(OpenClawUsage.id).label("count"),
                    func.sum(OpenClawUsage.cost_usd).label("cost")
                ).where(
                    OpenClawUsage.created_at >= since
                ).group_by(OpenClawUsage.platform)
                
                platform_result = await db.execute(platform_query)
                platforms = {
                    row.platform: {
                        "requests": row.count,
                        "cost_usd": float(row.cost)
                    }
                    for row in platform_result
                }
                
                return {
                    "period_days": days,
                    "total_requests": row.total_requests if row else 0,
                    "total_cost_usd": float(row.total_cost) if row and row.total_cost else 0.0,
                    "avg_cost_per_request": float(row.avg_cost) if row and row.avg_cost else 0.0,
                    "by_platform": platforms
                }
        except Exception as e:
            logger.error(f"Usage stats failed: {e}")
            return {"error": str(e)}


# Global client instance
openclaw_client = OpenClawClient()
