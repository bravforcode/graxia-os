"""
NewsBlackout Integration Tests
===============================
Verifies that SignalGateway blocks signals during active news blackout
and allows them when no blackout is active.

Run:
  cd graxia/packages
  python -m pytest quant_os/tests/chaos/test_news_blackout_integration.py -v
"""

from __future__ import annotations

import asyncio

import pytest

from graxia.packages.quant_os.core.news_blackout import NewsBlackout
from graxia.packages.quant_os.core.signal_gateway import SignalGateway, SignalSource


@pytest.fixture
def queue():
    return asyncio.Queue()


@pytest.fixture
def blackout():
    return NewsBlackout()


def _make_raw(**overrides) -> dict:
    base = {
        "symbol": "XAUUSD",
        "asset_class": "forex",
        "side": "BUY",
        "conviction": 0.8,
        "strategy": "momentum_v2",
        "entry_price": 2350.0,
        "stop_loss": 2340.0,
        "take_profit": 2370.0,
    }
    base.update(overrides)
    return base


class TestNewsBlackoutIntegration:
    @pytest.mark.asyncio
    async def test_signal_blocked_during_blackout(self, queue, blackout):
        blackout.trigger("CRISIS", "Fed emergency cut")
        gw = SignalGateway(queue=queue, news_blackout=blackout)

        result = await gw.ingest(_make_raw(), SignalSource.PYTHON)

        assert result is None
        assert queue.empty()

    @pytest.mark.asyncio
    async def test_signal_allowed_when_no_blackout(self, queue, blackout):
        gw = SignalGateway(queue=queue, news_blackout=blackout)

        result = await gw.ingest(_make_raw(), SignalSource.PYTHON)

        assert result is not None
        assert result.symbol == "XAUUSD"
        assert not queue.empty()

    @pytest.mark.asyncio
    async def test_signal_allowed_after_blackout_expires(self, queue, blackout):
        blackout.trigger("HIGH_UNCERTAINTY", "NFP release")
        assert blackout.is_blocked()

        blackout.clear()
        assert not blackout.is_blocked()

        gw = SignalGateway(queue=queue, news_blackout=blackout)
        result = await gw.ingest(_make_raw(), SignalSource.PYTHON)

        assert result is not None
        assert not queue.empty()

    @pytest.mark.asyncio
    async def test_multiple_signals_all_blocked(self, queue, blackout):
        blackout.trigger("CRISIS", "War escalation")
        gw = SignalGateway(queue=queue, news_blackout=blackout)

        r1 = await gw.ingest(_make_raw(), SignalSource.PYTHON)
        r2 = await gw.ingest(_make_raw(side="SELL"), SignalSource.TRADINGVIEW)

        assert r1 is None
        assert r2 is None
        assert queue.empty()

    @pytest.mark.asyncio
    async def test_default_blackout_if_none_provided(self, queue):
        gw = SignalGateway(queue=queue, news_blackout=None)

        result = await gw.ingest(_make_raw(), SignalSource.PYTHON)

        assert result is not None
        assert not queue.empty()
