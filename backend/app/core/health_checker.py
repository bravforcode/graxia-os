"""
Enterprise Health Checker

Comprehensive health checks for all system components.
"""
import logging
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from sqlalchemy import text

from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


class HealthChecker:
    """
    Enterprise-grade health checker.
    
    Checks:
    - Database connectivity
    - Redis connectivity
    - LLM API availability
    - Scraper health
    - Event bus status
    - Disk space
    - Memory usage
    """
    
    async def check_all(self) -> dict[str, Any]:
        """Run all health checks."""
        results = {
            "status": "healthy",
            "timestamp": datetime.now(UTC).isoformat(),
            "checks": {}
        }
        
        # Database
        db_health = await self._check_database()
        results["checks"]["database"] = db_health
        if db_health["status"] != "healthy":
            results["status"] = "degraded"
        
        # Redis
        redis_health = await self._check_redis()
        results["checks"]["redis"] = redis_health
        if redis_health["status"] != "healthy":
            results["status"] = "degraded"
        
        # LLM APIs
        llm_health = await self._check_llm_apis()
        results["checks"]["llm"] = llm_health
        
        # Scrapers
        scraper_health = await self._check_scrapers()
        results["checks"]["scrapers"] = scraper_health
        
        # Event Bus
        event_bus_health = await self._check_event_bus()
        results["checks"]["event_bus"] = event_bus_health
        
        # System Resources
        system_health = await self._check_system_resources()
        results["checks"]["system"] = system_health
        
        return results
    
    async def _check_database(self) -> dict[str, Any]:
        """Check database connectivity and performance."""
        try:
            async with AsyncSessionLocal() as db:
                start = perf_counter()
                await db.execute(text("SELECT 1"))
                latency_ms = (perf_counter() - start) * 1000
                
                return {
                    "status": "healthy",
                    "latency_ms": round(latency_ms, 2),
                    "message": "Database connection OK"
                }
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "message": "Database connection failed"
            }
    
    async def _check_redis(self) -> dict[str, Any]:
        """Check Redis connectivity."""
        try:
            import redis.asyncio as aioredis

            from app.config import settings
            
            r = aioredis.from_url(settings.REDIS_URL)
            start = perf_counter()
            await r.ping()
            latency_ms = (perf_counter() - start) * 1000
            await r.aclose()
            
            return {
                "status": "healthy",
                "latency_ms": round(latency_ms, 2),
                "message": "Redis connection OK"
            }
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "message": "Redis connection failed"
            }
    
    async def _check_llm_apis(self) -> dict[str, Any]:
        """Check LLM API availability."""
        results = {
            "openclaw": {"status": "unknown"},
            "gemini": {"status": "unknown"}
        }
        
        # Check OpenClaw
        try:
            from app.core.openclaw import openclaw_client
            # Simple availability check
            results["openclaw"] = {
                "status": "healthy" if openclaw_client else "unavailable",
                "message": "OpenClaw client initialized"
            }
        except Exception as e:
            results["openclaw"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Check Gemini
        try:
            from app.core.llm import llm_client
            results["gemini"] = {
                "status": "healthy" if llm_client else "unavailable",
                "message": "Gemini client initialized"
            }
        except Exception as e:
            results["gemini"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        return results
    
    async def _check_scrapers(self) -> dict[str, Any]:
        """Check scraper health."""
        try:
            from sqlalchemy import func, select

            from app.models.scraper_health import ScraperHealth
            
            async with AsyncSessionLocal() as db:
                # Get scraper health stats
                query = select(
                    func.count(ScraperHealth.scraper_name).label("total"),
                    func.sum(
                        func.case((ScraperHealth.status == "success", 1), else_=0)
                    ).label("healthy")
                )
                result = await db.execute(query)
                row = result.first()
                
                total = row.total if row else 0
                healthy = row.healthy if row else 0
                
                status = "healthy" if healthy == total else "degraded" if healthy > 0 else "unhealthy"
                
                return {
                    "status": status,
                    "total_scrapers": total,
                    "healthy_scrapers": healthy,
                    "unhealthy_scrapers": total - healthy
                }
        except Exception as e:
            logger.error(f"Scraper health check failed: {e}")
            return {
                "status": "unknown",
                "error": str(e)
            }
    
    async def _check_event_bus(self) -> dict[str, Any]:
        """Check event bus status."""
        try:
            from app.core.event_bus import event_bus
            
            stats = event_bus.get_event_stats()
            failed = event_bus.get_failed_events()
            
            status = "healthy" if len(failed) < 10 else "degraded"
            
            return {
                "status": status,
                "running": event_bus._running,
                "queue_size": event_bus._queue.qsize(),
                "total_events": sum(stats.values()),
                "failed_events": len(failed)
            }
        except Exception as e:
            logger.error(f"Event bus health check failed: {e}")
            return {
                "status": "unknown",
                "error": str(e)
            }
    
    async def _check_system_resources(self) -> dict[str, Any]:
        """Check system resources (disk, memory)."""
        try:
            import psutil
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            status = "healthy"
            if disk_percent > 90 or memory_percent > 90:
                status = "critical"
            elif disk_percent > 80 or memory_percent > 80:
                status = "warning"
            
            return {
                "status": status,
                "disk_usage_percent": disk_percent,
                "memory_usage_percent": memory_percent,
                "disk_free_gb": round(disk.free / (1024**3), 2),
                "memory_available_gb": round(memory.available / (1024**3), 2)
            }
        except Exception as e:
            logger.warning(f"System resource check failed: {e}")
            return {
                "status": "unknown",
                "error": str(e),
                "message": "psutil not available"
            }


# Global instance
health_checker = HealthChecker()
