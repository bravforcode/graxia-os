"""Rate-budget tests — token bucket math + client wiring."""
import pytest
from httpx import AsyncClient, MockTransport, Response

from ..core.rate_budget import TokenBucket, get_budget
from ..channels.platform_auth import ShopeeClient


@pytest.mark.asyncio
async def test_bucket_allows_burst_then_throttles():
    bucket = TokenBucket(rate_per_sec=2.0, burst=2)
    import time as _time
    # burst of 2 passes instantly
    t0 = _time.monotonic()
    await bucket.acquire()
    await bucket.acquire()
    assert _time.monotonic() - t0 < 0.2
    # third acquire waits ~0.5s for refill (real clock)
    t0 = _time.monotonic()
    await bucket.acquire()
    assert _time.monotonic() - t0 >= 0.4


@pytest.mark.asyncio
async def test_get_budget_lazy_and_cached():
    assert get_budget("shopee") is None  # no rate -> no budget
    b1 = get_budget("shopee", rate_per_sec=5.0)
    b2 = get_budget("shopee")
    assert b1 is b2  # cached


@pytest.mark.asyncio
async def test_client_honors_rate_budget(monkeypatch):
    calls = {"n": 0}

    class _Budget:
        async def acquire(self):
            calls["n"] += 1

    transport = MockTransport(lambda req: Response(200, json={"response": {"order_list": []}}))
    async with AsyncClient(transport=transport) as client:
        c = ShopeeClient(partner_id=1, partner_key="k", shop_id=2, mode="sandbox",
                         http_client=client, rate_budget=_Budget())
        await c.get_json("/order/get_order_list")
        await c.get_json("/order/get_order_list")
    assert calls["n"] == 2  # budget acquired per request
