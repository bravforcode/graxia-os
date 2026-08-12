"""
ULTRA: Tiered Rate Limiting Middleware
Plan-based rate limits with burst allowance and grace periods
"""
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import UUID

from app.middleware.rate_limit import get_redis_client
from app.models.organization import Organization
from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PlanTier(Enum):
    """Plan tiers with different rate limits"""
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


@dataclass
class RateLimitConfig:
    """Rate limit configuration for a tier"""
    requests_per_minute: int
    requests_per_hour: int
    requests_per_day: int
    burst_allowance: int  # Extra requests allowed in burst
    grace_period_seconds: int  # Time before limits reset


# Tier configurations
TIER_LIMITS: dict[PlanTier, RateLimitConfig] = {
    PlanTier.FREE: RateLimitConfig(
        requests_per_minute=30,
        requests_per_hour=500,
        requests_per_day=2000,
        burst_allowance=10,
        grace_period_seconds=60,
    ),
    PlanTier.STARTER: RateLimitConfig(
        requests_per_minute=60,
        requests_per_hour=2000,
        requests_per_day=10000,
        burst_allowance=20,
        grace_period_seconds=30,
    ),
    PlanTier.PRO: RateLimitConfig(
        requests_per_minute=120,
        requests_per_hour=5000,
        requests_per_day=50000,
        burst_allowance=50,
        grace_period_seconds=10,
    ),
    PlanTier.ENTERPRISE: RateLimitConfig(
        requests_per_minute=300,
        requests_per_hour=20000,
        requests_per_day=200000,
        burst_allowance=100,
        grace_period_seconds=0,
    ),
}


class TieredRateLimiter:
    """
    ULTRA: Tiered rate limiter with plan-based limits.
    Supports burst allowance, grace periods, and usage tracking.
    """

    def __init__(self):
        self._redis = None

    async def _get_redis(self):
        """Get Redis client"""
        if self._redis is None:
            self._redis = await get_redis_client()
        return self._redis

    async def get_user_tier(
        self,
        user_id: UUID,
        db: AsyncSession,
    ) -> PlanTier:
        """Get user's plan tier from organization"""
        try:
            from app.models.user import User
            
            # Get user with organization
            result = await db.execute(
                select(User, Organization)
                .join(Organization, User.organization_id == Organization.id, isouter=True)
                .where(User.id == user_id)
            )
            row = result.first()
            
            if not row:
                return PlanTier.FREE
            
            user, org = row
            if not org:
                return PlanTier.FREE
            
            # Map plan to tier
            plan = org.plan.lower()
            if plan == "enterprise":
                return PlanTier.ENTERPRISE
            elif plan == "pro":
                return PlanTier.PRO
            elif plan == "starter":
                return PlanTier.STARTER
            else:
                return PlanTier.FREE
                
        except Exception as e:
            logger.error(f"Error getting user tier: {e}")
            return PlanTier.FREE  # Default to free on error

    def _get_limit_config(self, tier: PlanTier) -> RateLimitConfig:
        """Get rate limit config for tier"""
        return TIER_LIMITS.get(tier, TIER_LIMITS[PlanTier.FREE])

    async def check_rate_limit(
        self,
        user_id: UUID,
        tier: PlanTier,
        endpoint: str,
    ) -> dict[str, Any]:
        """
        Check rate limit for user
        Returns dict with allowed status and remaining requests
        """
        redis = await self._get_redis()
        config = self._get_limit_config(tier)
        
        now = time.time()
        
        # Build Redis keys for different time windows
        minute_key = f"ratelimit:{user_id}:{endpoint}:minute:{int(now // 60)}"
        hour_key = f"ratelimit:{user_id}:{endpoint}:hour:{int(now // 3600)}"
        day_key = f"ratelimit:{user_id}:{endpoint}:day:{int(now // 86400)}"
        burst_key = f"ratelimit:{user_id}:{endpoint}:burst"
        
        try:
            # Use Redis pipeline for atomic operations
            pipe = redis.pipeline()
            
            # Increment counters
            pipe.incr(minute_key)
            pipe.incr(hour_key)
            pipe.incr(day_key)
            
            # Set expiry
            pipe.expire(minute_key, 120)  # 2 minutes
            pipe.expire(hour_key, 7200)   # 2 hours
            pipe.expire(day_key, 172800)  # 2 days
            
            # Get burst count
            pipe.get(burst_key)
            
            results = await pipe.execute()
            
            minute_count = results[0]
            hour_count = results[1]
            day_count = results[2]
            burst_count = int(results[-1] or 0)
            
            # Check limits
            remaining_minute = max(0, config.requests_per_minute - minute_count)
            remaining_hour = max(0, config.requests_per_hour - hour_count)
            remaining_day = max(0, config.requests_per_day - day_count)
            
            # Burst allowance
            burst_remaining = max(0, config.burst_allowance - burst_count)
            
            # Determine if allowed
            is_allowed = (
                minute_count <= config.requests_per_minute + (burst_remaining if minute_count > config.requests_per_minute else 0) and
                hour_count <= config.requests_per_hour and
                day_count <= config.requests_per_day
            )
            
            # Track burst usage if over normal limit
            if minute_count > config.requests_per_minute and is_allowed:
                await redis.incr(burst_key)
                await redis.expire(burst_key, config.grace_period_seconds)
            
            # Calculate reset time
            reset_time = int(now // 60 + 1) * 60
            
            return {
                "allowed": is_allowed,
                "tier": tier.value,
                "limit_minute": config.requests_per_minute,
                "limit_hour": config.requests_per_hour,
                "limit_day": config.requests_per_day,
                "remaining_minute": remaining_minute,
                "remaining_hour": remaining_hour,
                "remaining_day": remaining_day,
                "burst_remaining": burst_remaining,
                "reset_time": reset_time,
            }
            
        except Exception as e:
            logger.error(f"Rate limit check error: {e}")
            # Fail open - allow request on error
            return {
                "allowed": True,
                "tier": tier.value,
                "error": str(e),
            }

    async def enforce_rate_limit(
        self,
        request: Request,
        user_id: UUID,
        db: AsyncSession,
    ) -> None:
        """
        Enforce rate limit, raise HTTPException if exceeded
        """
        tier = await self.get_user_tier(user_id, db)
        endpoint = f"{request.method}:{request.url.path}"
        
        result = await self.check_rate_limit(user_id, tier, endpoint)
        
        if not result.get("allowed", True):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "tier": result.get("tier"),
                    "retry_after": result.get("reset_time", 60),
                    "limits": {
                        "minute": result.get("limit_minute"),
                        "hour": result.get("limit_hour"),
                        "day": result.get("limit_day"),
                    },
                },
                headers={
                    "Retry-After": str(result.get("reset_time", 60)),
                    "X-RateLimit-Limit": str(result.get("limit_minute", 60)),
                    "X-RateLimit-Remaining": str(result.get("remaining_minute", 0)),
                    "X-RateLimit-Tier": result.get("tier", "free"),
                },
            )
        
        # Store rate limit info in request state for response headers
        request.state.rate_limit_info = {
            "tier": result.get("tier"),
            "remaining_minute": result.get("remaining_minute"),
            "remaining_hour": result.get("remaining_hour"),
            "remaining_day": result.get("remaining_day"),
        }


# Global instance
tiered_limiter = TieredRateLimiter()


async def check_tiered_rate_limit(request: Request) -> None:
    """
    Dependency to check tiered rate limit
    Usage: from app.middleware.tiered_rate_limit import check_tiered_rate_limit
    """
    from app.database import get_db
    from app.middleware.auth import get_current_user_from_token
    
    try:
        # Get current user and database session
        user = await get_current_user_from_token(request)
        db_gen = get_db()
        db = await db_gen.__anext__()
        
        await tiered_limiter.enforce_rate_limit(request, user.id, db)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rate limit middleware error: {e}")
        # Fail open
        pass


class RateLimitByPlan:
    """
    Decorator for plan-based rate limiting
    
    Usage:
        @RateLimitByPlan()
        async def expensive_endpoint(request: Request):
            return {"data": ...}
    """
    
    def __init__(self, skip_for_admin: bool = True):
        self.skip_for_admin = skip_for_admin
    
    def __call__(self, func):
        async def wrapper(*args, **kwargs):
            # Extract request from args/kwargs
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                for value in kwargs.values():
                    if isinstance(value, Request):
                        request = value
                        break
            
            if request:
                await check_tiered_rate_limit(request)
            
            return await func(*args, **kwargs)
        
        return wrapper
