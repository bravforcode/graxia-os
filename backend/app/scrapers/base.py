"""
Universal scraper interface — ALL scrapers must implement this contract.
Guarantees consistent health tracking and graceful degradation.
Supports Residential Proxy and Session Cookies.
"""
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
]
_ua_idx = 0


def _next_ua() -> str:
    global _ua_idx
    ua = USER_AGENTS[_ua_idx % len(USER_AGENTS)]
    _ua_idx += 1
    return ua


class BaseScraper(ABC):
    source_name: str = "base"

    @abstractmethod
    async def fetch(self, url: str) -> httpx.Response | None:
        """GET request — returns None on failure (never raises)."""
        ...

    @abstractmethod
    async def parse(self, response: httpx.Response) -> list[dict]:
        """Extract raw items from HTML/JSON — returns [] on failure (never raises)."""
        ...

    @abstractmethod
    async def normalize(self, raw_item: dict) -> dict | None:
        """Map raw fields to opportunity schema — returns None if not normalizable."""
        ...

    async def run(self) -> list[dict]:
        if await self._is_muted():
            logger.info(f"Scraper {self.source_name}: muted — skipping")
            return []
        await self._record_attempt()
        results = []
        error_msg = None
        try:
            response = await self.fetch(self._get_url())
            if response is None:
                logger.info(f"Scraper {self.source_name}: fetch returned None, skipping gracefully")
                await self._record_result(success=True, item_count=0, error=None)
                return []
            raw_items = await self.parse(response)
            for raw in raw_items:
                try:
                    normalized = await self.normalize(raw)
                    if normalized:
                        normalized["source_platform"] = self.source_name
                        results.append(normalized)
                except Exception as e:
                    logger.warning(f"Scraper {self.source_name}: normalize failed: {e}")
            results = self._dedup(results)
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Scraper {self.source_name}: run failed: {e}")
        await self._record_result(success=error_msg is None, item_count=len(results), error=error_msg)
        return results

    def _get_url(self) -> str:
        return ""

    def _get_platform_cookies(self) -> str | None:
        """Resolve session cookies for this scraper's source_name."""
        try:
            from app.config import settings

            # 1. Platform-specific settings e.g. UPWORK_COOKIES, LINKEDIN_COOKIES
            specific_key = f"{self.source_name.upper()}_COOKIES"
            direct_cookies = (getattr(settings, specific_key, "") or "").strip()
            if direct_cookies:
                return direct_cookies

            # 2. JSON map in SCRAPER_SESSION_COOKIES
            raw_map = (getattr(settings, "SCRAPER_SESSION_COOKIES", "") or "").strip()
            if raw_map:
                cookies_dict = json.loads(raw_map)
                if isinstance(cookies_dict, dict) and self.source_name in cookies_dict:
                    val = cookies_dict[self.source_name]
                    if isinstance(val, dict):
                        return "; ".join(f"{k}={v}" for k, v in val.items())
                    return str(val).strip()
        except Exception:
            pass
        return None

    async def _is_muted(self) -> bool:
        try:
            from sqlalchemy import select

            from app.database import AsyncSessionLocal
            from app.models.scraper_health import ScraperHealth
            async with AsyncSessionLocal() as db:
                q = await db.execute(select(ScraperHealth).where(ScraperHealth.source_name == self.source_name))
                health = q.scalar_one_or_none()
                if health and health.is_muted:
                    if health.muted_until and datetime.now(UTC) > health.muted_until:
                        health.is_muted = False
                        health.muted_until = None
                        health.consecutive_failures = 0
                        await db.commit()
                        return False
                    return True
        except Exception:
            pass
        return False

    async def _record_attempt(self) -> None:
        try:
            from sqlalchemy import select

            from app.database import AsyncSessionLocal
            from app.models.scraper_health import ScraperHealth
            async with AsyncSessionLocal() as db:
                q = await db.execute(select(ScraperHealth).where(ScraperHealth.source_name == self.source_name))
                health = q.scalar_one_or_none()
                if not health:
                    health = ScraperHealth(source_name=self.source_name)
                    db.add(health)
                health.last_attempted_at = datetime.now(UTC)
                health.total_runs = (health.total_runs or 0) + 1
                await db.commit()
        except Exception as e:
            logger.warning(f"_record_attempt failed: {e}")

    async def _record_result(self, success: bool, item_count: int, error: str | None = None) -> None:
        try:
            from sqlalchemy import select

            from app.database import AsyncSessionLocal
            from app.models.scraper_health import ScraperHealth
            async with AsyncSessionLocal() as db:
                q = await db.execute(select(ScraperHealth).where(ScraperHealth.source_name == self.source_name))
                health = q.scalar_one_or_none()
                if not health:
                    health = ScraperHealth(source_name=self.source_name)
                    db.add(health)
                now = datetime.now(UTC)
                if success:
                    health.last_success_at = now
                    health.consecutive_failures = 0
                    health.total_successes = (health.total_successes or 0) + 1
                    runs = health.total_runs or 1
                    prev_avg = float(health.avg_items_per_run or 0)
                    health.avg_items_per_run = Decimal(
                        str((prev_avg * (runs - 1) + item_count) / runs)
                    )
                else:
                    health.consecutive_failures = (health.consecutive_failures or 0) + 1
                    health.last_error = error
                    if (health.consecutive_failures or 0) >= 3 and not health.is_muted:
                        health.is_muted = True
                        health.muted_until = now + timedelta(hours=24)
                        await self._notify_muted(health.consecutive_failures or 0)
                total_runs = health.total_runs or 1
                total_succ = health.total_successes or 0
                health.success_rate = Decimal(str(round((total_succ / total_runs) * 100, 2)))
                await db.commit()
        except Exception as e:
            logger.warning(f"_record_result failed: {e}")

    async def _notify_muted(self, consecutive_failures: int) -> None:
        try:
            import redis.asyncio as aioredis

            from app.config import settings
            r = aioredis.from_url(settings.REDIS_URL)
            flag_key = f"scraper_muted_notified:{self.source_name}"
            if not await r.get(flag_key):
                from app.core.event_bus import event_bus
                await event_bus.emit("scraper.failed", {"source_name": self.source_name, "consecutive_failures": consecutive_failures})
                await r.setex(flag_key, 86400, "1")
            await r.aclose()
            pool = getattr(r, "connection_pool", None)
            if pool is not None:
                await pool.disconnect()
        except Exception:
            pass

    def _compute_source_hash(self, url: str, title: str) -> str:
        raw = url + title[:100]
        return hashlib.sha256(raw.encode()).hexdigest()

    def _dedup(self, items: list[dict]) -> list[dict]:
        seen = set()
        result = []
        for item in items:
            h = item.get("source_hash")
            if h and h in seen:
                continue
            if h:
                seen.add(h)
            result.append(item)
        return result

    async def health_check(self) -> dict:
        try:
            from sqlalchemy import select

            from app.database import AsyncSessionLocal
            from app.models.scraper_health import ScraperHealth
            async with AsyncSessionLocal() as db:
                q = await db.execute(select(ScraperHealth).where(ScraperHealth.source_name == self.source_name))
                h = q.scalar_one_or_none()
                if h:
                    return {
                        "source_name": h.source_name,
                        "last_success_at": str(h.last_success_at),
                        "consecutive_failures": h.consecutive_failures,
                        "success_rate": float(h.success_rate or 0),
                        "is_muted": h.is_muted,
                        "avg_items_per_run": float(h.avg_items_per_run or 0),
                    }
        except Exception:
            pass
        return {"source_name": self.source_name, "status": "no_data"}

    async def _safe_fetch(
        self,
        url: str,
        headers: dict | None = None,
        cookies: dict | str | None = None,
        proxy: str | None = None,
    ) -> httpx.Response | None:
        _headers = {
            "User-Agent": _next_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        if headers:
            _headers.update(headers)

        # Attach session cookies
        session_cookie = cookies or self._get_platform_cookies()
        client_cookies = None
        if isinstance(session_cookie, str) and session_cookie:
            _headers["Cookie"] = session_cookie
        elif isinstance(session_cookie, dict) and session_cookie:
            client_cookies = session_cookie

        try:
            from app.config import settings

            proxy_target = proxy or getattr(settings, "ACTIVE_SCRAPER_PROXY", None)
            client_kwargs = {
                "timeout": 15.0,
                "follow_redirects": True,
            }
            if client_cookies:
                client_kwargs["cookies"] = client_cookies
            if proxy_target:
                client_kwargs["proxies"] = proxy_target

            async with httpx.AsyncClient(**client_kwargs) as client:
                resp = await client.get(url, headers=_headers)
                resp.raise_for_status()
                return resp
        except httpx.HTTPStatusError as e:
            logger.warning(f"Scraper {self.source_name}: fetch {url} returned HTTP {e.response.status_code}")
            return None
        except Exception as e:
            logger.warning(f"Scraper {self.source_name}: fetch {url} failed: {type(e).__name__} ({e})")
            return None
