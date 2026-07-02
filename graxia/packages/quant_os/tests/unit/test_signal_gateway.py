import pytest
from dataclasses import dataclass
from typing import List
import hashlib
import json


@dataclass(frozen=True)
class Signal:
    symbol: str
    direction: str
    source: str
    strength: float = 1.0

    @property
    def dedup_key(self) -> str:
        payload = json.dumps({"symbol": self.symbol, "direction": self.direction}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


class SignalGateway:
    def __init__(self):
        self._seen: set[str] = set()
        self._queue: List[Signal] = []

    def submit(self, signal: Signal) -> bool:
        if signal.strength <= 0 or signal.direction not in ("BUY", "SELL"):
            return False
        key = signal.dedup_key
        if key in self._seen:
            return False
        self._seen.add(key)
        self._queue.append(signal)
        return True

    @property
    def queue(self) -> List[Signal]:
        return list(self._queue)


@pytest.fixture
def gateway():
    return SignalGateway()


class TestSignalDeduplication:
    def test_same_signal_from_3_sources_only_1_queued(self, gateway):
        sig1 = Signal(symbol="XAUUSD", direction="BUY", source="tradingview")
        sig2 = Signal(symbol="XAUUSD", direction="BUY", source="ml_model")
        sig3 = Signal(symbol="XAUUSD", direction="BUY", source="manual")

        results = [gateway.submit(sig) for sig in [sig1, sig2, sig3]]

        assert results[0] is True
        assert results[1] is False
        assert results[2] is False
        assert len(gateway.queue) == 1

    def test_different_signals_all_accepted(self, gateway):
        sig1 = Signal(symbol="XAUUSD", direction="BUY", source="tv")
        sig2 = Signal(symbol="EURUSD", direction="SELL", source="tv")
        sig3 = Signal(symbol="XAUUSD", direction="SELL", source="tv")

        results = [gateway.submit(sig) for sig in [sig1, sig2, sig3]]

        assert all(results)
        assert len(gateway.queue) == 3

    def test_invalid_signal_rejected(self, gateway):
        bad1 = Signal(symbol="XAUUSD", direction="HOLD", source="tv")
        bad2 = Signal(symbol="XAUUSD", direction="BUY", source="tv", strength=-1.0)
        good = Signal(symbol="XAUUSD", direction="BUY", source="tv", strength=0.5)

        assert gateway.submit(bad1) is False
        assert gateway.submit(bad2) is False
        assert gateway.submit(good) is True
        assert len(gateway.queue) == 1
