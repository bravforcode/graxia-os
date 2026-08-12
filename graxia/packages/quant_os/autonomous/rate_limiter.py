"""Token-bucket rate limiter for LLM API calls.

Enforces per-provider daily request limits with a 10% buffer.
Bucket refills linearly over 24h so requests spread evenly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import structlog

from .config import (
    RATE_LIMIT_CEREBRAS_DAILY,
    RATE_LIMIT_GROQ_DAILY,
    RATE_LIMIT_OPENROUTER_DAILY,
)

logger = structlog.get_logger(__name__)

PROVIDER_LIMITS: dict[str, int] = {
    "groq": RATE_LIMIT_GROQ_DAILY,
    "cerebras": RATE_LIMIT_CEREBRAS_DAILY,
    "openrouter": RATE_LIMIT_OPENROUTER_DAILY,
}

_SECONDS_PER_DAY = 86400.0


@dataclass
class _Bucket:
    capacity: float
    tokens: float
    refill_rate: float
    last_refill: float


class RateLimiter:
    """Token-bucket rate limiter per LLM provider.

    Each provider gets a bucket sized to its daily limit (with 10% buffer).
    Tokens refill linearly over 24 hours so bursts are smoothed.
    """

    def __init__(self, limits: dict[str, int] | None = None) -> None:
        now = time.monotonic()
        cfg = limits or PROVIDER_LIMITS
        self._buckets: dict[str, _Bucket] = {
            name: _Bucket(
                capacity=float(cap),
                tokens=float(cap),
                refill_rate=float(cap) / _SECONDS_PER_DAY,
                last_refill=now,
            )
            for name, cap in cfg.items()
        }

    def can_proceed(self, provider: str) -> bool:
        """Check if a request can proceed without exceeding the limit."""
        bucket = self._get_bucket(provider)
        self._refill(bucket)
        return bucket.tokens >= 1.0

    def record_request(self, provider: str) -> None:
        """Consume one token from the provider's bucket."""
        bucket = self._get_bucket(provider)
        self._refill(bucket)
        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
        else:
            logger.warning(
                "rate_limiter_overdraw",
                provider=provider,
                remaining=bucket.tokens,
            )
            bucket.tokens = 0.0

    def get_wait_time(self, provider: str) -> float:
        """Seconds until the next token is available."""
        bucket = self._get_bucket(provider)
        self._refill(bucket)
        if bucket.tokens >= 1.0:
            return 0.0
        deficit = 1.0 - bucket.tokens
        return deficit / bucket.refill_rate

    def get_status(self) -> dict[str, dict[str, float]]:
        """Return current bucket state for all providers."""
        status: dict[str, dict[str, float]] = {}
        for name, bucket in self._buckets.items():
            self._refill(bucket)
            status[name] = {
                "remaining": round(bucket.tokens, 2),
                "capacity": bucket.capacity,
                "wait_seconds": round(self.get_wait_time(name), 1),
            }
        return status

    def _get_bucket(self, provider: str) -> _Bucket:
        key = provider.lower()
        if key not in self._buckets:
            logger.warning("rate_limiter_unknown_provider", provider=provider)
            return _Bucket(capacity=100.0, tokens=100.0, refill_rate=0.001, last_refill=time.monotonic())
        return self._buckets[key]

    def _refill(self, bucket: _Bucket) -> None:
        now = time.monotonic()
        elapsed = now - bucket.last_refill
        bucket.tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.refill_rate)
        bucket.last_refill = now
