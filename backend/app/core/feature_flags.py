"""
ULTRA: Feature Flags System
Dynamic feature toggling with plan-based, percentage-based, and user-based targeting
"""
import hashlib
import logging
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user_from_token
from app.models.organization import Organization
from app.models.user import User

logger = logging.getLogger(__name__)


class FlagType(Enum):
    """Feature flag types"""
    BOOLEAN = "boolean"  # Simple on/off
    PERCENTAGE = "percentage"  # Percentage of users
    PLAN_BASED = "plan_based"  # Based on subscription plan
    USER_BASED = "user_based"  # Specific users
    TIME_BASED = "time_based"  # Time window


@dataclass
class FeatureFlag:
    """Feature flag definition"""
    key: str
    flag_type: FlagType
    enabled: bool = False
    percentage: int = 0  # 0-100 for percentage-based
    allowed_plans: list[str] | None = None  # For plan-based
    allowed_user_ids: list[str] | None = None  # For user-based
    start_time: datetime | None = None  # For time-based
    end_time: datetime | None = None  # For time-based
    description: str = ""
    created_at: datetime = None
    updated_at: datetime = None


class FeatureFlagManager:
    """
    ULTRA: Feature flag manager with multiple targeting strategies.
    Supports Redis caching for high-performance flag checks.
    """

    def __init__(self):
        self._flags: dict[str, FeatureFlag] = {}
        self._redis = None
        self._cache_ttl = 60  # 60 seconds cache

    async def _get_redis(self):
        """Get Redis client"""
        if self._redis is None:
            from app.middleware.rate_limit import get_redis_client
            self._redis = await get_redis_client()
        return self._redis

    def register(self, flag: FeatureFlag) -> None:
        """Register a feature flag"""
        flag.created_at = datetime.now(UTC)
        flag.updated_at = datetime.now(UTC)
        self._flags[flag.key] = flag
        logger.info(f"Registered feature flag: {flag.key} ({flag.flag_type.value})")

    def unregister(self, key: str) -> None:
        """Unregister a feature flag"""
        if key in self._flags:
            del self._flags[key]
            logger.info(f"Unregistered feature flag: {key}")

    async def is_enabled(
        self,
        key: str,
        user: User | None = None,
        organization: Organization | None = None,
    ) -> bool:
        """
        Check if feature is enabled for user/organization.

        Args:
            key: Feature flag key
            user: Optional user context
            organization: Optional organization context

        Returns:
            True if feature is enabled
        """
        flag = self._flags.get(key)
        if not flag:
            return False  # Unknown flags default to disabled

        # Check Redis cache first
        try:
            redis = await self._get_redis()
            cache_key = f"featureflag:{key}:{user.id if user else 'anon'}:{organization.id if organization else 'none'}"
            cached = await redis.get(cache_key)
            if cached is not None:
                return cached.decode() == "1"
        except Exception as e:
            logger.error(f"Feature flag cache error: {e}")

        # Evaluate flag
        result = await self._evaluate_flag(flag, user, organization)

        # Cache result
        try:
            redis = await self._get_redis()
            await redis.setex(cache_key, self._cache_ttl, "1" if result else "0")
        except Exception as e:
            logger.error(f"Feature flag cache write error: {e}")

        return result

    async def _evaluate_flag(
        self,
        flag: FeatureFlag,
        user: User | None,
        org: Organization | None,
    ) -> bool:
        """Evaluate feature flag based on its type"""

        # Check time window first (applies to all types)
        if flag.start_time and datetime.now(UTC) < flag.start_time:
            return False
        if flag.end_time and datetime.now(UTC) > flag.end_time:
            return False

        if flag.flag_type == FlagType.BOOLEAN:
            return flag.enabled

        elif flag.flag_type == FlagType.PERCENTAGE:
            if not user:
                # Without user, use random
                return random.random() < (flag.percentage / 100)

            # Use consistent hash of user ID for stable assignment
            hash_input = f"{flag.key}:{user.id}"
            hash_value = int(hashlib.sha256(hash_input.encode()).hexdigest(), 16)
            user_percentage = (hash_value % 10000) / 100  # 0-100 with 2 decimal precision
            return user_percentage < flag.percentage

        elif flag.flag_type == FlagType.PLAN_BASED:
            if not org:
                return False
            plan = org.plan.lower()
            return plan in [p.lower() for p in (flag.allowed_plans or [])]

        elif flag.flag_type == FlagType.USER_BASED:
            if not user:
                return False
            return str(user.id) in (flag.allowed_user_ids or [])

        elif flag.flag_type == FlagType.TIME_BASED:
            now = datetime.now(UTC)
            if flag.start_time and now < flag.start_time:
                return False
            if flag.end_time and now > flag.end_time:
                return False
            return flag.enabled

        return False

    async def enable(self, key: str) -> None:
        """Enable a feature flag"""
        if key in self._flags:
            self._flags[key].enabled = True
            self._flags[key].updated_at = datetime.now(UTC)
            await self._invalidate_cache(key)
            logger.info(f"Enabled feature flag: {key}")

    async def disable(self, key: str) -> None:
        """Disable a feature flag"""
        if key in self._flags:
            self._flags[key].enabled = False
            self._flags[key].updated_at = datetime.now(UTC)
            await self._invalidate_cache(key)
            logger.info(f"Disabled feature flag: {key}")

    async def _invalidate_cache(self, key: str) -> None:
        """Invalidate Redis cache for a flag"""
        try:
            redis = await self._get_redis()
            pattern = f"featureflag:{key}:*"
            keys = []
            async for k in redis.scan_iter(match=pattern):
                keys.append(k)
            if keys:
                await redis.delete(*keys)
        except Exception as e:
            logger.error(f"Failed to invalidate feature flag cache: {e}")

    def get_all_flags(self) -> list[FeatureFlag]:
        """Get all registered feature flags"""
        return list(self._flags.values())

    def get_flag_state(self, key: str) -> dict[str, Any] | None:
        """Get detailed state of a feature flag"""
        flag = self._flags.get(key)
        if not flag:
            return None

        return {
            "key": flag.key,
            "type": flag.flag_type.value,
            "enabled": flag.enabled,
            "percentage": flag.percentage,
            "allowed_plans": flag.allowed_plans,
            "start_time": flag.start_time.isoformat() if flag.start_time else None,
            "end_time": flag.end_time.isoformat() if flag.end_time else None,
            "description": flag.description,
            "created_at": flag.created_at.isoformat() if flag.created_at else None,
            "updated_at": flag.updated_at.isoformat() if flag.updated_at else None,
        }


# Global feature flag manager
feature_flags = FeatureFlagManager()


# ═══════════════════════════════════════════════════════════════════════════════
# ULTRA: Pre-configured Feature Flags
# ═══════════════════════════════════════════════════════════════════════════════

def init_default_feature_flags():
    """Initialize default feature flags"""

    # New AI scoring algorithm (gradual rollout)
    feature_flags.register(FeatureFlag(
        key="ai_v2_scoring",
        flag_type=FlagType.PERCENTAGE,
        enabled=True,
        percentage=10,  # Start with 10% of users
        description="New AI scoring algorithm v2",
    ))

    # Advanced analytics (pro+ only)
    feature_flags.register(FeatureFlag(
        key="advanced_analytics",
        flag_type=FlagType.PLAN_BASED,
        enabled=True,
        allowed_plans=["pro", "enterprise"],
        description="Advanced analytics dashboard",
    ))

    # Beta API (specific users)
    feature_flags.register(FeatureFlag(
        key="beta_api",
        flag_type=FlagType.USER_BASED,
        enabled=True,
        allowed_user_ids=[],  # Add beta tester IDs here
        description="Beta API endpoints",
    ))

    # Holiday promotion (time-based)
    feature_flags.register(FeatureFlag(
        key="holiday_promo",
        flag_type=FlagType.TIME_BASED,
        enabled=True,
        start_time=datetime(2025, 12, 1, tzinfo=UTC),
        end_time=datetime(2026, 1, 1, tzinfo=UTC),
        description="Holiday promotion pricing",
    ))

    # Bulk import v2 (kill switch)
    feature_flags.register(FeatureFlag(
        key="bulk_import_v2",
        flag_type=FlagType.BOOLEAN,
        enabled=True,
        description="Bulk import v2 (kill switch available)",
    ))


# ═══════════════════════════════════════════════════════════════════════════════
# FastAPI Dependencies
# ═══════════════════════════════════════════════════════════════════════════════

async def require_feature_flag(key: str):
    """
    Dependency to require a feature flag.

    Usage:
        @router.get("/beta-feature")
        async def beta_endpoint(
            user: User = Depends(get_current_user_from_token),
            _: None = Depends(require_feature_flag("beta_api"))
        ):
            return {"message": "Beta feature"}
    """
    async def _check_flag(
        request: Request,
        user: User = Depends(get_current_user_from_token),
        db: AsyncSession = Depends(get_db),
    ):
        # Get organization
        org = None
        if user and user.organization_id:
            result = await db.execute(
                select(Organization).where(Organization.id == user.organization_id)
            )
            org = result.scalar_one_or_none()

        if not await feature_flags.is_enabled(key, user, org):
            raise HTTPException(
                status_code=403,
                detail=f"Feature '{key}' is not enabled for your account"
            )

        return None

    return _check_flag


# ═══════════════════════════════════════════════════════════════════════════════
# Decorators
# ═══════════════════════════════════════════════════════════════════════════════

def feature_enabled(key: str, fallback: Callable | None = None):
    """
    Decorator to conditionally execute based on feature flag.

    Usage:
        @feature_enabled("ai_v2_scoring", fallback=legacy_scoring)
        async def new_scoring_algorithm(...):
            return await ai_v2_score(...)
    """
    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            # Try to extract user/org from kwargs
            user = kwargs.get('user')
            org = kwargs.get('organization')

            if await feature_flags.is_enabled(key, user, org):
                return await func(*args, **kwargs)
            elif fallback:
                return await fallback(*args, **kwargs)
            else:
                raise HTTPException(
                    status_code=403,
                    detail=f"Feature '{key}' is not enabled"
                )
        return wrapper
    return decorator
