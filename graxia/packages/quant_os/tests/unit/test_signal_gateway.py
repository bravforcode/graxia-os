"""Unit tests for the real async SignalGateway.

Imports from core.signal_gateway -- no inline class definitions.
"""

import asyncio

import pytest

from graxia.packages.quant_os.core.signal_gateway import (
    Side,
    SignalGateway,
)


@pytest.fixture
def gateway():
    queue = asyncio.Queue()
    return SignalGateway(queue=queue), queue


def _valid_raw(**overrides) -> dict:
    """Build a valid raw signal payload."""
    base = {
        "symbol": "XAUUSD",
        "asset_class": "metals",
        "side": "BUY",
        "conviction": 0.8,
        "strategy": "test_strategy",
        "entry_price": 2400.0,
        "stop_loss": 2390.0,
        "take_profit": 2420.0,
    }
    base.update(overrides)
    return base


class TestSignalIngestion:
    @pytest.mark.asyncio
    async def test_valid_signal_accepted(self, gateway):
        gw, queue = gateway
        sig = await gw.ingest(_valid_raw(), source="python")
        assert sig is not None
        assert sig.symbol == "XAUUSD"
        assert sig.side == Side.BUY
        assert not queue.empty()

    @pytest.mark.asyncio
    async def test_invalid_symbol_rejected(self, gateway):
        gw, queue = gateway
        result = await gw.ingest(_valid_raw(symbol=""), source="python")
        assert result is None
        assert queue.empty()

    @pytest.mark.asyncio
    async def test_invalid_side_rejected(self, gateway):
        gw, queue = gateway
        result = await gw.ingest(_valid_raw(side="HOLD"), source="python")
        assert result is None
        assert queue.empty()


class TestSignalDeduplication:
    @pytest.mark.asyncio
    async def test_duplicate_signal_rejected(self, gateway):
        gw, queue = gateway
        sig1 = await gw.ingest(_valid_raw(), source="python")
        assert sig1 is not None
        sig2 = await gw.ingest(_valid_raw(), source="python")
        assert sig2 is None  # deduped
        assert queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_different_signals_all_accepted(self, gateway):
        gw, queue = gateway
        r1 = await gw.ingest(_valid_raw(), source="python")
        r2 = await gw.ingest(_valid_raw(side="SELL"), source="python")
        r3 = await gw.ingest(_valid_raw(symbol="EURUSD"), source="python")
        assert r1 is not None
        assert r2 is not None
        assert r3 is not None
        assert queue.qsize() == 3
