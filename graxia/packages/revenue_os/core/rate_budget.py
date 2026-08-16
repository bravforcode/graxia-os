"""Per-platform rate-limit budgets (token bucket) for outbound API calls.

Guards against blowing platform quotas (Shopee 300 req/min, SP-API per-
operation throttles, etc.). Optional — clients pass a budget into the signed
client; without one, behavior is unchanged (429 backoff still applies).
"""
from __future__ import annotations

import time
from typing import Optional


class TokenBucket:
    """Token bucket: acquire() waits until a token is available."""

    def __init__(self, rate_per_sec: float, burst: Optional[int] = None):
        if rate_per_sec <= 0:
            raise ValueError("rate_per_sec must be > 0")
        self.rate = rate_per_sec
        self.burst = burst or max(1, int(rate_per_sec))
        self._tokens = float(self.burst)
        self._last = time.monotonic()

    async def acquire(self) -> None:
        import asyncio
        while True:
            now = time.monotonic()
            self._tokens = min(self.burst, self._tokens + (now - self._last) * self.rate)
            self._last = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
            await asyncio.sleep((1.0 - self._tokens) / self.rate)


# platform -> TokenBucket; configured at boot / deployment (e.g. env-driven).
BUDGETS: dict[str, TokenBucket] = {}


def get_budget(platform: str, rate_per_sec: Optional[float] = None) -> Optional[TokenBucket]:
    """Lazily create a budget when a rate is provided; None otherwise."""
    if platform not in BUDGETS and rate_per_sec is not None:
        BUDGETS[platform] = TokenBucket(rate_per_sec)
    return BUDGETS.get(platform)
