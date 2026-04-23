"""
Universal scraper interface — ALL scrapers must implement this contract.
Guarantees consistent health tracking and graceful degradation.
"""
import hashlib
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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
    async def fetch(self, url: str) -> Optional[httpx.Response]:
        """GET request — returns None on failure (never raises)."""
        ...

    @abstractmethod
    async def parse(self, response: httpx.Response) -> list[dict]:
        """Extract raw items from HTML/JSON — returns [] on failure (never raises)."""
        ...

    @abstractmethod
    async def normalize(self, raw_item: dict) -> Optional[dict]:
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
                raise RuntimeError("fetch returned None")
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

    async def _is_muted(self) -> bool:
        try:
            from app.database import AsyncSessionLocal
            from app.models.scraper_health import ScraperHealth
            from sqlalchemy import select
            async with AsyncSessionLocal() as db:
                q = await db.execute(select(ScraperHealth).where(ScraperHealth.source_name == self.source_name))
                health = q.scalar_one_or_none()
                if health and health.is_muted:
                    if health.muted_until and datetime.now(timezone.utc) > health.muted_until:
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
            from app.database import AsyncSessionLocal
            from app.models.scraper_health import ScraperHealth
            from sqlalchemy import select
            async with AsyncSessionLocal() as db:
                q = await db.execute(select(ScraperHealth).where(ScraperHealth.source_name == self.source_name))
                health = q.scalar_one_or_none()
                if not health:
                    health = ScraperHealth(source_name=self.source_name)
                    db.add(health)
                health.last_attempted_at = datetime.now(timezone.utc)
                health.total_runs = (health.total_runs or 0) + 1
                await db.commit()
        except Exception as e:
            logger.warning(f"_record_attempt failed: {e}")

    async def _record_result(self, success: bool, item_count: int, error: Optional[str] = None) -> None:
        try:
            from app.database import AsyncSessionLocal
            from app.models.scraper_health import ScraperHealth
            from sqlalchemy import select
            async with AsyncSessionLocal() as db:
                q = await db.execute(select(ScraperHealth).where(ScraperHealth.source_name == self.source_name))
                health = q.scalar_one_or_none()
                if not health:
                    health = ScraperHealth(source_name=self.source_name)
                    db.add(health)
                now = datetime.now(timezone.utc)
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
            from app.database import AsyncSessionLocal
            from app.models.scraper_health import ScraperHealth
            from sqlalchemy import select
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

    async def _safe_fetch(self, url: str, headers: Optional[dict] = None) -> Optional[httpx.Response]:
        _headers = {"User-Agent": _next_ua(), "Accept": "text/html,application/json,*/*"}
        if headers:
            _headers.update(headers)
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=_headers)
                resp.raise_for_status()
                return resp
        except Exception as e:
            logger.warning(f"Scraper {self.source_name}: fetch {url} failed: {e}")
            return None
