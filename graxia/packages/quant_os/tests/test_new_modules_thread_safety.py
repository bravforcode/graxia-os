"""Thread safety tests for new modules.

Tests concurrent access to:
- OMS.submit_order() — already uses threading.Lock
- DynamicKellySizer.compute_kelly() — stateless, should be safe
- OrderBookFeatureExtractor.extract() — stateless, should be safe
- CircuitBreaker.record_trade()

Run with: python -m pytest tests/test_new_modules_thread_safety.py -v --tb=short
"""

import threading
import time

import pytest

from graxia.packages.quant_os.core.enums import OrderStatus
from graxia.packages.quant_os.core.kelly import DynamicKellySizer
from graxia.packages.quant_os.data_pipeline.orderbook_features import OrderBookFeatureExtractor
from graxia.packages.quant_os.execution.adapters.base import AccountInfo, BrokerAdapter, Order, OrderResult
from graxia.packages.quant_os.execution.oms import OMS

try:
    from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

    HAS_CIRCUIT_BREAKER = True
except ImportError:
    HAS_CIRCUIT_BREAKER = False

from unittest.mock import MagicMock


def _mock_risk_engine():
    """Create a mock risk engine that approves all orders."""
    re = MagicMock()
    result = MagicMock()
    result.passed = True
    result.reason = ""
    re.check_order_sync.return_value = result
    return re


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class ThreadSafeMockAdapter(BrokerAdapter):
    """Mock adapter that tracks concurrent calls."""

    def __init__(self):
        super().__init__("thread_mock")
        self._connected = True
        self._lock = threading.Lock()
        self._submit_count = 0
        self._max_concurrent = 0
        self._current_concurrent = 0

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def submit_order(self, order: Order) -> OrderResult:
        with self._lock:
            self._submit_count += 1
            self._current_concurrent += 1
            self._max_concurrent = max(self._max_concurrent, self._current_concurrent)

        # Simulate some work
        time.sleep(0.001)

        with self._lock:
            self._current_concurrent -= 1

        return OrderResult(
            status=OrderStatus.FILLED,
            broker_id=f"THREAD-{self._submit_count}",
            filled_quantity=order.quantity,
            avg_price=1.0,
            fee=0.0,
        )

    def cancel_order(self, broker_order_id: str) -> OrderResult:
        return OrderResult(status=OrderStatus.CANCELLED)

    def get_positions(self) -> list:
        return []

    def get_order_status(self, broker_order_id: str) -> OrderResult:
        return OrderResult(status=OrderStatus.FILLED)

    def close_position(self, broker_position_id: str, volume: float, symbol: str = "") -> OrderResult:
        return OrderResult(status=OrderStatus.FILLED)

    def set_stop_loss(
        self, position_ticket: int, symbol: str, stop_loss_price: float, take_profit: float | None = None
    ) -> bool:
        return True

    def get_account_info(self) -> AccountInfo:
        return AccountInfo(equity=10000.0, cash=10000.0, margin_used=0.0, margin_available=10000.0)


# ---------------------------------------------------------------------------
# Thread Safety Tests
# ---------------------------------------------------------------------------


class TestOMSThreadSafety:
    """Test OMS concurrent order submission."""

    def test_concurrent_submissions_no_duplicates(self, tmp_path):
        """Multiple threads submitting orders simultaneously — no duplicates."""
        adapter = ThreadSafeMockAdapter()
        oms = OMS(
            adapters={"mt5": adapter},
            ledger_path=tmp_path / "thread_test_ledger.jsonl",
            risk_engine=_mock_risk_engine(),
        )

        results = []
        errors = []

        def submit_order(signal_id):
            try:
                order = oms.submit_order(
                    signal_id=signal_id,
                    symbol="XAUUSD",
                    asset_class="metals",
                    side="BUY",
                    quantity=0.1,
                )
                results.append(order)
            except Exception as e:
                errors.append(e)

        # Launch 20 threads simultaneously
        threads = []
        for i in range(20):
            t = threading.Thread(target=submit_order, args=(f"signal-{i}",))
            threads.append(t)

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=10)

        # All should succeed
        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 20

        # All should be filled
        filled = [r for r in results if r.status == OrderStatus.FILLED]
        assert len(filled) == 20

    def test_concurrent_same_signal_idempotent(self, tmp_path):
        """Same signal_id submitted from multiple threads — only one order."""
        adapter = ThreadSafeMockAdapter()
        oms = OMS(
            adapters={"mt5": adapter},
            ledger_path=tmp_path / "idempotent_test_ledger.jsonl",
            risk_engine=_mock_risk_engine(),
        )

        results = []
        lock = threading.Lock()

        def submit_same_signal():
            order = oms.submit_order(
                signal_id="same-signal-123",
                symbol="XAUUSD",
                asset_class="metals",
                side="BUY",
                quantity=0.1,
            )
            with lock:
                results.append(order)

        # Launch 10 threads with same signal_id
        threads = []
        for _ in range(10):
            t = threading.Thread(target=submit_same_signal)
            threads.append(t)

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=10)

        # Only one should be FILLED, rest should return existing
        assert len(results) == 10
        unique_orders = set(r.order_id for r in results)
        assert len(unique_orders) == 1, f"Expected 1 unique order, got {len(unique_orders)}"

    def test_concurrent_different_symbols(self, tmp_path):
        """Different symbols submitted concurrently — all succeed."""
        adapter = ThreadSafeMockAdapter()
        oms = OMS(
            adapters={"mt5": adapter},
            ledger_path=tmp_path / "multi_sym_ledger.jsonl",
            risk_engine=_mock_risk_engine(),
        )

        symbols = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD"]
        results = []
        lock = threading.Lock()

        def submit_for_symbol(symbol, idx):
            order = oms.submit_order(
                signal_id=f"sig-{symbol}-{idx}",
                symbol=symbol,
                asset_class="metals",
                side="BUY",
                quantity=0.1,
            )
            with lock:
                results.append(order)

        threads = []
        for i in range(5):
            for j in range(4):  # 4 orders per symbol
                t = threading.Thread(target=submit_for_symbol, args=(symbols[i], j))
                threads.append(t)

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=10)

        assert len(results) == 20
        filled = [r for r in results if r.status == OrderStatus.FILLED]
        assert len(filled) == 20


class TestDynamicKellyThreadSafety:
    """Test DynamicKellySizer is safe for concurrent use."""

    def test_concurrent_compute_kelly(self):
        """Multiple threads calling compute_kelly simultaneously."""
        sizer = DynamicKellySizer(base_kelly=0.25, vol_target=0.15)
        results = []
        lock = threading.Lock()

        def compute(regime, vol):
            r = sizer.compute_kelly(0.55, 1.5, 1.0, vol, regime, 0.05)
            with lock:
                results.append(r)

        threads = []
        regimes = ["trending", "ranging", "volatile", "crisis", "normal"]
        for regime in regimes:
            for vol in [0.10, 0.15, 0.20, 0.30]:
                t = threading.Thread(target=compute, args=(regime, vol))
                threads.append(t)

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=10)

        assert len(results) == 20
        # All results should be valid
        for r in results:
            assert 0 < r.fraction <= 0.50
            assert r.vol_mult > 0


class TestOrderBookThreadSafety:
    """Test OrderBookFeatureExtractor is safe for concurrent use."""

    def test_concurrent_extract(self):
        """Multiple threads calling extract simultaneously."""
        extractor = OrderBookFeatureExtractor(depth=20)
        orderbook = {
            "bids": [[100.0 - i * 0.01, 10.0 + i] for i in range(20)],
            "asks": [[100.1 + i * 0.01, 8.0 + i] for i in range(20)],
        }

        results = []
        lock = threading.Lock()

        def extract():
            features = extractor.extract(orderbook)
            with lock:
                results.append(features)

        threads = [threading.Thread(target=extract) for _ in range(50)]

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=10)

        assert len(results) == 50
        # All results should be identical (stateless)
        for r in results:
            assert r.spread == results[0].spread
            assert r.ob_imbalance == results[0].ob_imbalance


@pytest.mark.skipif(not HAS_CIRCUIT_BREAKER, reason="CircuitBreaker not implemented")
class TestCircuitBreakerThreadSafety:
    """Test CircuitBreaker concurrent access."""

    def test_concurrent_record_trade(self):
        """Multiple threads recording losses simultaneously — breaker must trip."""
        cb = CircuitBreaker()

        results = []
        lock = threading.Lock()

        def record():
            tripped = cb.record_trade("forex", -0.01)
            with lock:
                results.append(tripped)

        threads = [threading.Thread(target=record) for _ in range(20)]

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=10)

        assert len(results) == 20
        # Default threshold is 3 consecutive losses — 20 losses must trip the breaker
        assert any(results), "breaker never tripped under concurrent losses"
        assert cb.is_open("forex") is True
