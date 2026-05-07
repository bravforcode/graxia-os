"""
Smart Scraper Base Class with Intelligent Failure Handling
แยกประเภท error และให้ weight ต่างกัน - แก้ปัญหา: auto-mute ที่ดีเกินไป
"""
import asyncio
import logging
from datetime import UTC, datetime, timedelta
from enum import Enum

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.scraper_health import ScraperHealth
from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """Classification of scraper errors with different weights."""
    NETWORK_TIMEOUT = "network_timeout"      # น้ำหนัก: 0.5 - transient
    RATE_LIMIT = "rate_limit"                # น้ำหนัก: 0.3 - temporary
    PARSING_ERROR = "parsing_error"          # น้ำหนัก: 0.8 - site structure issue
    SITE_CHANGED = "site_changed"            # น้ำหนัก: 1.0 - critical
    AUTHENTICATION = "authentication"          # น้ำหนัก: 1.0 - critical
    UNKNOWN = "unknown"                      # น้ำหนัก: 0.7


# Error weights - higher = more serious
ERROR_WEIGHTS = {
    ErrorType.NETWORK_TIMEOUT: 0.5,
    ErrorType.RATE_LIMIT: 0.3,
    ErrorType.PARSING_ERROR: 0.8,
    ErrorType.SITE_CHANGED: 1.0,
    ErrorType.AUTHENTICATION: 1.0,
    ErrorType.UNKNOWN: 0.7,
}


class SmartBaseScraper(BaseScraper):
    """
    Smart scraper with:
    - Weighted failure scoring (ไม่ใช่นับ 1, 2, 3)
    - Self-healing retry with exponential backoff
    - Early warning system (ก่อน mute)
    - Shorter mute duration (6 hours vs 24 hours)
    
    Features:
    - Transient errors (timeout, rate limit) มี weight ต่ำ
    - Critical errors (site changed, auth) มี weight สูง
    - Early warning ที่ 2.0 คะแนน
    - Auto-mute ที่ 3.0 คะแนน
    """
    
    # Thresholds
    WEIGHTED_FAILURE_THRESHOLD = 3.0  # คะแนนรวมถึงจะ mute
    MUTE_DURATION_HOURS = 6          # ลดจาก 24 ชั่วโมงเหลือ 6
    EARLY_WARNING_THRESHOLD = 2.0   # แจ้งเตือนก่อน mute
    DECAY_FACTOR = 0.8              # Decay คะแนนเก่า
    
    async def _classify_error(self, error: Exception) -> ErrorType:
        """Classify error type from exception message."""
        error_str = str(error).lower()
        
        if "timeout" in error_str or "timed out" in error_str:
            return ErrorType.NETWORK_TIMEOUT
        elif "rate limit" in error_str or "429" in error_str or "402" in error_str:
            return ErrorType.RATE_LIMIT
        elif "parse" in error_str or "element" in error_str or "selector" in error_str:
            return ErrorType.PARSING_ERROR
        elif "401" in error_str or "403" in error_str or "auth" in error_str:
            return ErrorType.AUTHENTICATION
        elif "404" in error_str or "not found" in error_str:
            return ErrorType.SITE_CHANGED
        else:
            return ErrorType.UNKNOWN
    
    async def _record_weighted_failure(self, error: Exception):
        """Record failure with weight instead of simple count."""
        error_type = await self._classify_error(error)
        weight = ERROR_WEIGHTS[error_type]
        
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ScraperHealth).where(ScraperHealth.source_name == self.source_name)
            )
            health = result.scalar_one_or_none()
            
            if health is None:
                health = ScraperHealth(source_name=self.source_name)
                db.add(health)
            
            # Calculate weighted score with decay
            current_weighted = (health.consecutive_failures or 0) * self.DECAY_FACTOR
            new_weighted = current_weighted + weight
            health.consecutive_failures = int(new_weighted)
            health.last_error = f"[{error_type.value}] {str(error)[:200]}"
            
            # Early warning before muting
            if new_weighted >= self.EARLY_WARNING_THRESHOLD and not health.is_muted:
                if new_weighted < self.WEIGHTED_FAILURE_THRESHOLD:
                    await self._send_early_warning(error_type, new_weighted)
            
            # Mute decision at threshold
            if new_weighted >= self.WEIGHTED_FAILURE_THRESHOLD and not health.is_muted:
                health.is_muted = True
                health.muted_until = datetime.now(UTC) + timedelta(
                    hours=self.MUTE_DURATION_HOURS
                )
                await self._notify_muted(health.consecutive_failures or 0)
                logger.warning(
                    f"Scraper {self.source_name}: MUTED "
                    f"(weighted={new_weighted:.1f}, type={error_type.value})"
                )
            
            await db.commit()
    
    async def _send_early_warning(self, error_type: ErrorType, weighted_score: float):
        """Send warning before muting."""
        try:
            from app.telegram_bot.bot import send_message
            await send_message(
                f"⚠️ Early Warning: {self.source_name} scraper\n"
                f"Error type: {error_type.value}\n"
                f"Weighted score: {weighted_score:.1f}/{self.WEIGHTED_FAILURE_THRESHOLD}\n"
                f"Will auto-mute if reaches threshold.",
                parse_mode=None
            )
        except Exception as e:
            logger.debug(f"Failed to send early warning: {e}")
    
    async def _record_weighted_success(self):
        """Decay failure count on success (prevents flapping)."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ScraperHealth).where(ScraperHealth.source_name == self.source_name)
            )
            health = result.scalar_one_or_none()
            if health:
                # Decay failures instead of full reset
                health.consecutive_failures = max(
                    0, int((health.consecutive_failures or 0) * 0.3)
                )
                await db.commit()
    
    async def run(self) -> list[dict]:
        """
        Enhanced run with:
        - Smart error classification
        - Exponential backoff retry
        - Weighted failure scoring
        """
        if await self._is_muted():
            logger.info(f"Scraper {self.source_name}: muted - skipping")
            return []
        
        await self._record_attempt()
        results = []
        
        # Retry with exponential backoff: 1s, 2s, 4s
        max_retries = 3
        for attempt in range(max_retries):
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
                        logger.warning(f"{self.source_name}: normalize failed: {e}")
                
                results = self._dedup(results)
                
                # Success - reset weighted failures
                if results:
                    await self._record_weighted_success()
                break
                
            except Exception as e:
                wait_time = 2 ** attempt  # 1, 2, 4 seconds
                logger.warning(
                    f"{self.source_name}: attempt {attempt + 1} failed: {e}. "
                    f"Retrying in {wait_time}s..."
                )
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                else:
                    # Final failure - record weighted
                    await self._record_weighted_failure(e)
        
        await self._record_result(
            success=len(results) > 0,
            item_count=len(results),
            error=None if results else "All retries exhausted"
        )
        return results


# Convenience function for manual unmute
async def unmute_scraper(source_name: str) -> bool:
    """Manually unmute a scraper (for recovery procedures)."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ScraperHealth).where(ScraperHealth.source_name == source_name)
        )
        health = result.scalar_one_or_none()
        
        if health and health.is_muted:
            health.is_muted = False
            health.muted_until = None
            health.consecutive_failures = 0
            health.last_error = None
            await db.commit()
            logger.info(f"Scraper {source_name} manually unmuted")
            return True
        
        return False


async def get_scraper_health(source_name: str) -> dict | None:
    """Get detailed health status for a scraper."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ScraperHealth).where(ScraperHealth.source_name == source_name)
        )
        health = result.scalar_one_or_none()
        
        if not health:
            return None
        
        return {
            "source_name": health.source_name,
            "is_muted": health.is_muted,
            "muted_until": health.muted_until.isoformat() if health.muted_until else None,
            "consecutive_failures": health.consecutive_failures,
            "success_rate": float(health.success_rate or 0),
            "last_success": health.last_success_at.isoformat() if health.last_success_at else None,
            "last_error": health.last_error,
        }
