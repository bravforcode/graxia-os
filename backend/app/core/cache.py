"""
Redis caching utilities for performance optimization
"""

import json
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

# Global Redis client for caching
_redis_client: aioredis.Redis | None = None


async def get_cache_client() -> aioredis.Redis:
    """Get or create Redis client for caching"""
    global _redis_client

    if _redis_client is None:
        try:
            _redis_client = await aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )
            await _redis_client.ping()
            logger.info("Cache Redis client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize cache Redis client: {e}")
            raise

    return _redis_client


async def close_cache_client():
    """Close Redis client connection"""
    global _redis_client

    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
        logger.info("Cache Redis client closed")


def cache(ttl: int = 300, key_prefix: str = ""):
    """
    Decorator to cache function results in Redis

    Args:
        ttl: Time to live in seconds (default: 5 minutes)
        key_prefix: Optional prefix for cache key

    Example:
        @cache(ttl=600, key_prefix="opportunities")
        async def get_opportunities_summary():
            # Expensive query
            return result
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Build cache key
            func_name = func.__name__
            args_str = str(args) if args else ""
            kwargs_str = str(sorted(kwargs.items())) if kwargs else ""
            cache_key = f"{key_prefix}:{func_name}:{args_str}:{kwargs_str}"

            try:
                redis_client = await get_cache_client()

                # Try to get from cache
                cached = await redis_client.get(cache_key)
                if cached:
                    logger.debug(f"Cache hit: {cache_key}")
                    return json.loads(cached)

                # Cache miss - execute function
                logger.debug(f"Cache miss: {cache_key}")
                result = await func(*args, **kwargs)

                # Store in cache
                await redis_client.setex(cache_key, ttl, json.dumps(result, default=str))

                return result

            except Exception as e:
                logger.warning(f"Cache error: {e}, executing function without cache")
                # If cache fails, just execute the function
                return await func(*args, **kwargs)

        return wrapper

    return decorator


async def invalidate_cache(pattern: str):
    """
    Invalidate cache entries matching pattern

    Args:
        pattern: Redis key pattern (e.g., "opportunities:*")

    Example:
        await invalidate_cache("opportunities:*")
    """
    try:
        redis_client = await get_cache_client()

        # Find all keys matching pattern
        keys = []
        async for key in redis_client.scan_iter(match=pattern):
            keys.append(key)

        # Delete all matching keys
        if keys:
            await redis_client.delete(*keys)
            logger.info(f"Invalidated {len(keys)} cache entries matching '{pattern}'")

    except Exception as e:
        logger.error(f"Failed to invalidate cache: {e}")


async def get_cached(key: str) -> Any | None:
    """
    Get value from cache

    Args:
        key: Cache key

    Returns:
        Cached value or None if not found
    """
    try:
        redis_client = await get_cache_client()
        cached = await redis_client.get(key)

        if cached:
            return json.loads(cached)

        return None

    except Exception as e:
        logger.error(f"Failed to get from cache: {e}")
        return None


async def set_cached(key: str, value: Any, ttl: int = 300):
    """
    Set value in cache

    Args:
        key: Cache key
        value: Value to cache
        ttl: Time to live in seconds (default: 5 minutes)
    """
    try:
        redis_client = await get_cache_client()
        await redis_client.setex(key, ttl, json.dumps(value, default=str))

    except Exception as e:
        logger.error(f"Failed to set cache: {e}")


async def delete_cached(key: str):
    """
    Delete value from cache

    Args:
        key: Cache key
    """
    try:
        redis_client = await get_cache_client()
        await redis_client.delete(key)

    except Exception as e:
        logger.error(f"Failed to delete from cache: {e}")  # nosec B608


class CacheManager:
    """Context manager for cache operations"""

    def __init__(self, key_prefix: str = ""):
        self.key_prefix = key_prefix

    async def get(self, key: str) -> Any | None:
        """Get value from cache"""
        full_key = f"{self.key_prefix}:{key}" if self.key_prefix else key
        return await get_cached(full_key)

    async def set(self, key: str, value: Any, ttl: int = 300):
        """Set value in cache"""
        full_key = f"{self.key_prefix}:{key}" if self.key_prefix else key
        await set_cached(full_key, value, ttl)

    async def delete(self, key: str):
        """Delete value from cache"""
        full_key = f"{self.key_prefix}:{key}" if self.key_prefix else key
        await delete_cached(full_key)

    async def invalidate_all(self):
        """Invalidate all cache entries with this prefix"""
        pattern = f"{self.key_prefix}:*" if self.key_prefix else "*"
        await invalidate_cache(pattern)


# Pre-configured cache managers for common use cases
opportunities_cache = CacheManager("opportunities")
submissions_cache = CacheManager("submissions")
contacts_cache = CacheManager("contacts")
tasks_cache = CacheManager("tasks")
drafts_cache = CacheManager("drafts")


# ═══════════════════════════════════════════════════════════════════════════════
# ULTRA: Multi-Tenancy Cache with Organization Isolation
# ═══════════════════════════════════════════════════════════════════════════════

class TenantCacheManager:
    """
    Multi-tenancy aware cache manager with automatic organization isolation.
    Ensures tenants cannot access each other's cached data.
    """

    def __init__(self, key_prefix: str = "", default_ttl: int = 300):
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl

    def _build_tenant_key(self, organization_id: str | None, key: str) -> str:
        """Build cache key with tenant isolation"""
        tenant_segment = f"org:{organization_id}" if organization_id else "org:public"
        prefix = f"{self.key_prefix}:{tenant_segment}" if self.key_prefix else tenant_segment
        return f"{prefix}:{key}"

    async def get(
        self,
        key: str,
        organization_id: str | None = None,
    ) -> Any | None:
        """Get value from cache with tenant isolation"""
        full_key = self._build_tenant_key(organization_id, key)
        return await get_cached(full_key)

    async def set(
        self,
        key: str,
        value: Any,
        organization_id: str | None = None,
        ttl: int | None = None,
    ):
        """Set value in cache with tenant isolation"""
        full_key = self._build_tenant_key(organization_id, key)
        await set_cached(full_key, value, ttl or self.default_ttl)

    async def delete(
        self,
        key: str,
        organization_id: str | None = None,
    ):
        """Delete value from cache with tenant isolation"""
        full_key = self._build_tenant_key(organization_id, key)
        await delete_cached(full_key)

    async def invalidate_tenant(self, organization_id: str | None = None):
        """Invalidate all cache entries for a specific tenant"""
        tenant_segment = f"org:{organization_id}" if organization_id else "org:public"
        pattern = f"{self.key_prefix}:{tenant_segment}:*" if self.key_prefix else f"{tenant_segment}:*"
        await invalidate_cache(pattern)

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Any],
        organization_id: str | None = None,
        ttl: int | None = None,
    ) -> Any:
        """Get from cache or compute and store (cache-aside pattern)"""
        cached = await self.get(key, organization_id)
        if cached is not None:
            return cached

        value = await factory()
        await self.set(key, value, organization_id, ttl)
        return value


def tenant_cache(
    ttl: int = 300,
    key_prefix: str = "",
    organization_param: str = "organization_id",
):
    """
    Decorator to cache function results with automatic tenant isolation.

    Args:
        ttl: Time to live in seconds
        key_prefix: Cache key prefix
        organization_param: Parameter name containing organization_id

    Example:
        @tenant_cache(ttl=600, key_prefix="opportunities")
        async def get_opportunities(organization_id: str):
            return await db.query(...)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Extract organization_id from kwargs or args
            org_id = kwargs.get(organization_param)
            if org_id is None and args:
                # Try to find in positional args (assumes first arg if single)
                org_id = args[0] if len(args) == 1 else None

            # Build cache key
            func_name = func.__name__
            args_str = str(args[1:]) if len(args) > 1 else str(args) if args and not org_id else ""
            kwargs_str = str(sorted({k: v for k, v in kwargs.items() if k != organization_param}.items()))
            cache_key = f"{key_prefix}:{func_name}:{args_str}:{kwargs_str}"

            # Use tenant-aware cache manager
            cache_mgr = TenantCacheManager(key_prefix, ttl)

            try:
                # Try cache first
                cached = await cache_mgr.get(cache_key, org_id)
                if cached is not None:
                    logger.debug(f"Tenant cache hit: {cache_key} (org: {org_id})")
                    return cached

                # Cache miss - execute function
                logger.debug(f"Tenant cache miss: {cache_key} (org: {org_id})")
                result = await func(*args, **kwargs)

                # Store with tenant isolation
                await cache_mgr.set(cache_key, result, org_id, ttl)
                return result

            except Exception as e:
                logger.warning(f"Tenant cache error: {e}, executing without cache")
                return await func(*args, **kwargs)

        return wrapper
    return decorator


# ULTRA: Pre-configured tenant-aware cache managers
tenant_opportunities_cache = TenantCacheManager("opportunities", 600)
tenant_submissions_cache = TenantCacheManager("submissions", 300)
tenant_contacts_cache = TenantCacheManager("contacts", 300)
tenant_billing_cache = TenantCacheManager("billing", 60)  # Short TTL for billing
tenant_analytics_cache = TenantCacheManager("analytics", 300)


# ═══════════════════════════════════════════════════════════════════════════════
# ULTRA: Cache Warming & Pre-computation
# ═══════════════════════════════════════════════════════════════════════════════

class CacheWarmer:
    """Background cache warming for expensive computations"""

    def __init__(self):
        self.warm_tasks: dict[str, Callable] = {}

    def register(
        self,
        key: str,
        factory: Callable[[], Any],
        ttl: int = 300,
    ):
        """Register a cache warming task"""
        self.warm_tasks[key] = {"factory": factory, "ttl": ttl}

    async def warm_all(self):
        """Execute all registered warming tasks"""
        for key, config in self.warm_tasks.items():
            try:
                value = await config["factory"]()
                await set_cached(key, value, config["ttl"])
                logger.info(f"Cache warmed: {key}")
            except Exception as e:
                logger.error(f"Failed to warm cache {key}: {e}")

    async def warm_tenant(
        self,
        organization_id: str,
        factory_map: dict[str, Callable],
    ):
        """Warm cache for specific tenant"""
        cache_mgr = TenantCacheManager("warm", 300)
        for key, factory in factory_map.items():
            try:
                value = await factory()
                await cache_mgr.set(key, value, organization_id)
                logger.info(f"Tenant cache warmed: {key} (org: {organization_id})")
            except Exception as e:
                logger.error(f"Failed to warm tenant cache {key}: {e}")


# Global cache warmer instance
cache_warmer = CacheWarmer()
