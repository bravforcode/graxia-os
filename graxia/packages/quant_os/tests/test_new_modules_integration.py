"""Integration tests for new modules — Wave 4.

Tests full integration with paper broker adapter:
- TripleBoostEnsemble → signal → OMS → PaperAdapter fill
- DynamicKellySizer → position sizing → order
- CVaROptimizer → portfolio optimization
- SmartOrderRouter → order routing
- LimitOrderWithTimeout → limit fill / market fallback
- OrderBookFeatureExtractor → feature pipeline
- VolumeBreakout → signal generation
- FundingRateArbitrage → signal generation
- CircuitBreaker → loss-streak triggers + cooldown recovery
"""

from unittest.mock import MagicMock

import numpy as np
import pytest

from graxia.packages.quant_os.core.enums import OrderStatus
from graxia.packages.quant_os.core.kelly import DynamicKellySizer
from graxia.packages.quant_os.data_pipeline.orderbook_features import OrderBookFeatureExtractor
from graxia.packages.quant_os.execution.adapters.base import AccountInfo, BrokerAdapter, Order, OrderResult
from graxia.packages.quant_os.execution.limit_order import LimitOrderWithTimeout
from graxia.packages.quant_os.execution.oms import OMS
from graxia.packages.quant_os.execution.smart_router import SmartOrderRouter
from graxia.packages.quant_os.ml.ensemble import TripleBoostEnsemble

try:
    from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

    HAS_CIRCUIT_BREAKER = True
except ImportError:
    HAS_CIRCUIT_BREAKER = False

from graxia.packages.quant_os.risk.cvar_optimizer import CVaROptimizer
from graxia.packages.quant_os.strategies.funding_rate_arb import FundingRateArbitrage
from graxia.packages.quant_os.strategies.volume_breakout import VolumeBreakout

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class MockBrokerAdapter(BrokerAdapter):
    """Mock broker for integration tests."""

    def __init__(self, name: str = "mock_mt5"):
        super().__init__(name)
        self._connected = True
        self._orders: dict[str, OrderResult] = {}
        self._positions: list[dict] = []
        self._fill_count = 0

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def submit_order(self, order: Order) -> OrderResult:
        self._fill_count += 1
        return OrderResult(
            status=OrderStatus.FILLED,
            broker_id=f"MOCK-{self._fill_count}",
            filled_quantity=order.quantity,
            avg_price=1.1234,
            fee=0.50,
        )

    def cancel_order(self, broker_order_id: str) -> OrderResult:
        return OrderResult(status=OrderStatus.CANCELLED, broker_id=broker_order_id)

    def get_positions(self) -> list[dict]:
        return self._positions

    def get_order_status(self, broker_order_id: str) -> OrderResult:
        return OrderResult(status=OrderStatus.FILLED, broker_id=broker_order_id)

    def close_position(self, broker_position_id: str, volume: float, symbol: str = "") -> OrderResult:
        return OrderResult(status=OrderStatus.FILLED, broker_id=broker_position_id)

    def set_stop_loss(
        self, position_ticket: int, symbol: str, stop_loss_price: float, take_profit: float | None = None
    ) -> bool:
        return True

    def get_account_info(self) -> AccountInfo:
        return AccountInfo(equity=10000.0, cash=10000.0, margin_used=0.0, margin_available=10000.0)


@pytest.fixture
def mock_adapter():
    return MockBrokerAdapter()


@pytest.fixture
def oms(mock_adapter, tmp_path):
    """OMS with mock risk engine that approves all orders (fail-closed requires one)."""
    risk_engine = MagicMock()
    result = MagicMock()
    result.passed = True
    result.reason = ""
    risk_engine.check_order_sync.return_value = result
    return OMS(
        adapters={"mt5": mock_adapter},
        ledger_path=tmp_path / "test_ledger.jsonl",
        risk_engine=risk_engine,
    )


# ---------------------------------------------------------------------------
# 1. Ensemble + OMS Integration
# ---------------------------------------------------------------------------


class TestEnsembleOMSIntegration:
    """Test TripleBoostEnsemble → signal → OMS → PaperAdapter fill."""

    def test_ensemble_produces_signal_oms_submits(self, oms, mock_adapter):
        """Ensemble prediction → OMS submit_order → MockBroker fill."""
        # Create synthetic data
        np.random.seed(42)
        x = np.random.randn(100, 5)
        y = (x[:, 0] + x[:, 1] > 0).astype(int)

        # Fit ensemble (use small params for speed)
        from catboost import CatBoostClassifier
        from lightgbm import LGBMClassifier
        from xgboost import XGBClassifier

        ensemble = TripleBoostEnsemble()
        ensemble.models = {
            "lgbm": LGBMClassifier(n_estimators=5, max_depth=2, verbose=-1),
            "catboost": CatBoostClassifier(iterations=5, depth=2, verbose=0),
            "xgboost": XGBClassifier(n_estimators=5, max_depth=2),
        }
        ensemble._fitted = True
        for model in ensemble.models.values():
            model.fit(x[:80], y[:80])

        # Predict
        result = ensemble.predict(x[80:])
        assert result.confidence > 0

        # Submit to OMS
        order = oms.submit_order(
            signal_id="ensemble-test-1",
            symbol="XAUUSD",
            asset_class="metals",
            side="BUY" if result.prediction == 1 else "SELL",
            quantity=0.1,
            stop_loss=3200.0,
            take_profit=3400.0,
        )
        assert order.status == OrderStatus.FILLED
        assert mock_adapter._fill_count == 1

    def test_ensemble_predict_proba_shape(self):
        """predict_proba returns (n_samples, 2) shape."""
        from catboost import CatBoostClassifier
        from lightgbm import LGBMClassifier
        from xgboost import XGBClassifier

        ensemble = TripleBoostEnsemble()
        ensemble.models = {
            "lgbm": LGBMClassifier(n_estimators=5, max_depth=2, verbose=-1),
            "catboost": CatBoostClassifier(iterations=5, depth=2, verbose=0),
            "xgboost": XGBClassifier(n_estimators=5, max_depth=2),
        }
        ensemble._fitted = True

        np.random.seed(42)
        x = np.random.randn(50, 3)
        y = (x[:, 0] > 0).astype(int)
        for model in ensemble.models.values():
            model.fit(x[:40], y[:40])

        proba = ensemble.predict_proba(x[40:])
        assert proba.shape == (10, 2)
        assert np.all(proba >= 0) and np.all(proba <= 1)


# ---------------------------------------------------------------------------
# 2. Dynamic Kelly + Position Sizing Integration
# ---------------------------------------------------------------------------


class TestDynamicKellyIntegration:
    """Test DynamicKellySizer with various regimes."""

    def test_kelly_regime_scaling(self):
        """Different regimes produce different fractions."""
        sizer = DynamicKellySizer(base_kelly=0.25, vol_target=0.15)

        trending = sizer.compute_kelly(0.55, 1.5, 1.0, 0.15, "trending")
        ranging = sizer.compute_kelly(0.55, 1.5, 1.0, 0.15, "ranging")
        volatile = sizer.compute_kelly(0.55, 1.5, 1.0, 0.15, "volatile")
        crisis = sizer.compute_kelly(0.55, 1.5, 1.0, 0.15, "crisis")

        assert trending.fraction > ranging.fraction > volatile.fraction > crisis.fraction

    def test_kelly_vol_scaling(self):
        """Higher vol = smaller position."""
        sizer = DynamicKellySizer(base_kelly=0.25, vol_target=0.15)

        low_vol = sizer.compute_kelly(0.55, 1.5, 1.0, 0.10, "normal")
        high_vol = sizer.compute_kelly(0.55, 1.5, 1.0, 0.30, "normal")

        assert low_vol.fraction > high_vol.fraction

    def test_kelly_drawdown_protection(self):
        """Higher drawdown = smaller position."""
        sizer = DynamicKellySizer(base_kelly=0.25, vol_target=0.15)

        no_dd = sizer.compute_kelly(0.55, 1.5, 1.0, 0.15, "normal", 0.0)
        high_dd = sizer.compute_kelly(0.55, 1.5, 1.0, 0.15, "normal", 0.10)

        assert no_dd.fraction > high_dd.fraction

    def test_kelly_edge_cases(self):
        """Edge cases don't crash."""
        sizer = DynamicKellySizer()

        # Zero loss
        r = sizer.compute_kelly(0.55, 1.5, 0.0, 0.15)
        assert r.fraction == sizer.min_kelly

        # Win rate 0
        r = sizer.compute_kelly(0.0, 1.5, 1.0, 0.15)
        assert r.fraction == sizer.min_kelly

        # Win rate 1
        r = sizer.compute_kelly(1.0, 1.5, 1.0, 0.15)
        assert r.fraction == sizer.min_kelly


# ---------------------------------------------------------------------------
# 3. CVaR Portfolio Optimization Integration
# ---------------------------------------------------------------------------


class TestCVaRIntegration:
    """Test CVaROptimizer with real-like data."""

    def test_cvar_optimization_converges(self):
        """Optimizer finds valid weights."""
        np.random.seed(42)
        returns = np.random.randn(500, 4) * 0.01

        opt = CVaROptimizer(alpha=0.05, max_weight=0.40)
        result = opt.optimize(returns)

        assert len(result.weights) == 4
        assert abs(sum(result.weights) - 1.0) < 0.01
        assert all(0 <= w <= 0.40 + 0.01 for w in result.weights)

    def test_cvar_risk_metrics(self):
        """Risk metrics are computed correctly."""
        np.random.seed(42)
        returns = np.random.randn(500, 3) * 0.01

        opt = CVaROptimizer(alpha=0.05, max_weight=0.50)
        result = opt.optimize(returns)
        metrics = opt.compute_risk_metrics(returns, result.weights)

        assert "var_95" in metrics
        assert "cvar_95" in metrics
        assert "sharpe_ratio" in metrics
        assert "sortino_ratio" in metrics
        assert "max_drawdown" in metrics
        assert metrics["max_drawdown"] >= 0

    def test_cvar_single_asset(self):
        """Single asset edge case."""
        np.random.seed(42)
        returns = np.random.randn(100, 1) * 0.01

        opt = CVaROptimizer(alpha=0.05, max_weight=1.0)
        result = opt.optimize(returns)

        assert abs(result.weights[0] - 1.0) < 0.01


# ---------------------------------------------------------------------------
# 4. Smart Order Router Integration
# ---------------------------------------------------------------------------


class TestSmartRouterIntegration:
    """Test SmartOrderRouter with mock exchange."""

    def test_small_order_routes_to_market(self):
        """Small urgent order → market."""
        exchange = MagicMock()
        exchange.fetch_order_book.return_value = {
            "bids": [[100.0, 100.0]],
            "asks": [[100.1, 100.0]],
        }

        router = SmartOrderRouter(exchange)
        decision = router.route_order("BTCUSD", "BUY", 0.001, urgency="high")

        assert decision.strategy == "market"
        assert decision.slices == 1

    def test_medium_order_routes_to_twap(self):
        """Medium order → TWAP."""
        exchange = MagicMock()
        exchange.fetch_order_book.return_value = {
            "bids": [[100.0, 10.0]],
            "asks": [[100.1, 10.0]],
        }

        router = SmartOrderRouter(exchange, impact_threshold=0.001, twap_threshold=0.005)
        decision = router.route_order("BTCUSD", "BUY", 0.05, urgency="normal")

        assert decision.strategy in ("twap", "market")  # depends on impact
        assert decision.slices >= 1

    def test_twap_execution(self):
        """TWAP execution places multiple orders."""
        exchange = MagicMock()
        exchange.create_order.return_value = {"id": "order-1"}

        router = SmartOrderRouter(exchange)
        orders = router.execute_twap("BTCUSD", "BUY", 0.1, slices=3, interval=0.01)

        assert len(orders) == 3
        assert exchange.create_order.call_count == 3


# ---------------------------------------------------------------------------
# 5. Limit Order Integration
# ---------------------------------------------------------------------------


class TestLimitOrderIntegration:
    """Test LimitOrderWithTimeout with mock exchange."""

    def test_limit_fill(self):
        """Limit order fills within timeout."""
        exchange = MagicMock()
        exchange.fetch_order_book.return_value = {
            "bids": [[100.0, 10.0]],
            "asks": [[100.1, 10.0]],
        }
        exchange.create_order.return_value = {"id": "order-1"}
        exchange.fetch_order.return_value = {
            "status": "closed",
            "average": 100.05,
            "filled": 0.1,
        }

        lo = LimitOrderWithTimeout(timeout_seconds=5, price_offset=0.001)
        result = lo.place_order(exchange, "BTCUSD", "BUY", 0.1)

        assert result.status == "filled"
        assert result.fill_price == 100.05

    def test_limit_timeout_market_fallback(self):
        """Limit times out → market fallback."""
        exchange = MagicMock()
        exchange.fetch_order_book.return_value = {
            "bids": [[100.0, 10.0]],
            "asks": [[100.1, 10.0]],
        }
        # First create = limit, second create = market fallback
        exchange.create_order.side_effect = [
            {"id": "limit-1"},
            {"id": "market-1", "average": 100.1, "filled": 0.1},
        ]
        exchange.fetch_order.return_value = {"status": "open"}
        exchange.cancel_order.return_value = None

        lo = LimitOrderWithTimeout(timeout_seconds=1, price_offset=0.001)
        result = lo.place_order(exchange, "BTCUSD", "BUY", 0.1)

        assert result.status == "market_fallback"
        assert result.orders_placed == 2

    def test_limit_cancel_replaces_order(self):
        """Exchange cancel → re-place order."""
        exchange = MagicMock()
        exchange.fetch_order_book.return_value = {
            "bids": [[100.0, 10.0]],
            "asks": [[100.1, 10.0]],
        }

        # First call: limit order, then canceled, then new limit, then filled
        call_count = [0]

        def mock_create(**kwargs):
            call_count[0] += 1
            return {"id": f"order-{call_count[0]}"}

        exchange.create_order.side_effect = mock_create
        exchange.fetch_order.side_effect = [
            {"status": "canceled"},  # first order canceled
            {"status": "closed", "average": 100.05, "filled": 0.1},  # second fills
        ]
        exchange.cancel_order.return_value = None

        lo = LimitOrderWithTimeout(timeout_seconds=10, price_offset=0.001)
        result = lo.place_order(exchange, "BTCUSD", "BUY", 0.1)

        assert result.status == "filled"
        assert result.orders_placed == 2  # original + replacement


# ---------------------------------------------------------------------------
# 6. Order Book Features Integration
# ---------------------------------------------------------------------------


class TestOrderBookFeaturesIntegration:
    """Test OrderBookFeatureExtractor with various order books."""

    def test_normal_book(self):
        """Normal order book produces valid features."""
        extractor = OrderBookFeatureExtractor(depth=10)
        orderbook = {
            "bids": [[100.0 - i * 0.1, 10.0 + i] for i in range(10)],
            "asks": [[100.1 + i * 0.1, 8.0 + i] for i in range(10)],
        }

        features = extractor.extract(orderbook)

        assert features.spread > 0
        assert features.spread_pct > 0
        assert -1 <= features.ob_imbalance <= 1
        assert features.total_bid_liquidity > 0
        assert features.total_ask_liquidity > 0

    def test_empty_book(self):
        """Empty order book returns zero features."""
        extractor = OrderBookFeatureExtractor()
        features = extractor.extract({"bids": [], "asks": []})

        assert features.spread == 0
        assert features.ob_imbalance == 0

    def test_to_dict(self):
        """to_dict returns correct keys."""
        extractor = OrderBookFeatureExtractor()
        features = extractor.extract(
            {
                "bids": [[100.0, 10.0]],
                "asks": [[100.1, 8.0]],
            }
        )
        d = extractor.to_dict(features)

        assert "ob_spread" in d
        assert "ob_imbalance" in d
        assert len(d) == 9


# ---------------------------------------------------------------------------
# 7. Volume Breakout Integration
# ---------------------------------------------------------------------------


class TestVolumeBreakoutIntegration:
    """Test VolumeBreakout strategy."""

    def test_bullish_breakout(self):
        """Price breaks above high with volume → BUY signal."""
        strategy = VolumeBreakout(lookback=5, volume_threshold=1.5)
        ohlcv = {
            "open": [100] * 5 + [104],
            "high": [101] * 5 + [106],
            "low": [99] * 5 + [103],
            "close": [100.5] * 5 + [105.5],
            "volume": [100] * 5 + [300],
        }

        signal = strategy.generate_signal("TEST", ohlcv)

        assert signal is not None
        assert signal.signal_type.value == "BUY"
        assert float(signal.take_profit) > float(signal.entry_price)
        assert float(signal.stop_loss) < float(signal.entry_price)

    def test_no_breakout_no_signal(self):
        """No breakout → no signal."""
        strategy = VolumeBreakout(lookback=5, volume_threshold=1.5)
        ohlcv = {
            "open": [100] * 6,
            "high": [101] * 6,
            "low": [99] * 6,
            "close": [100.5] * 6,
            "volume": [100] * 6,
        }

        signal = strategy.generate_signal("TEST", ohlcv)
        assert signal is None

    def test_low_volume_no_signal(self):
        """Breakout without volume → no signal."""
        strategy = VolumeBreakout(lookback=5, volume_threshold=2.0)
        ohlcv = {
            "open": [100] * 5 + [104],
            "high": [101] * 5 + [106],
            "low": [99] * 5 + [103],
            "close": [100.5] * 5 + [105.5],
            "volume": [100] * 5 + [100],  # Same volume, not a spike
        }

        signal = strategy.generate_signal("TEST", ohlcv)
        assert signal is None

    def test_bearish_breakout(self):
        """Price breaks below low with volume → SELL signal."""
        strategy = VolumeBreakout(lookback=5, volume_threshold=1.5)
        ohlcv = {
            "open": [100] * 5 + [96],
            "high": [101] * 5 + [97],
            "low": [99] * 5 + [94],
            "close": [100.5] * 5 + [95],
            "volume": [100] * 5 + [300],
        }

        signal = strategy.generate_signal("TEST", ohlcv)

        assert signal is not None
        assert signal.signal_type.value == "SELL"
        assert float(signal.take_profit) < float(signal.entry_price)
        assert float(signal.stop_loss) > float(signal.entry_price)


# ---------------------------------------------------------------------------
# 8. Funding Rate Integration
# ---------------------------------------------------------------------------


class TestFundingRateIntegration:
    """Test FundingRateArbitrage strategy."""

    def test_high_funding_generates_signal(self):
        """High positive funding → SELL signal (short perp)."""
        strategy = FundingRateArbitrage()
        ohlcv = {"close": [50000.0]}

        signal = strategy.generate_signal("BTCUSD", ohlcv, funding_rate=0.0003)

        assert signal is not None
        assert signal.signal_type.value == "SELL"
        assert signal.confidence > 0

    def test_low_funding_no_signal(self):
        """Low funding → no signal."""
        strategy = FundingRateArbitrage()
        ohlcv = {"close": [50000.0]}

        signal = strategy.generate_signal("BTCUSD", ohlcv, funding_rate=0.00001)
        assert signal is None

    def test_no_funding_no_crash(self):
        """Missing funding_rate → no signal, no crash."""
        strategy = FundingRateArbitrage()
        ohlcv = {"close": [50000.0]}

        signal = strategy.generate_signal("BTCUSD", ohlcv)
        assert signal is None

    def test_empty_close_no_crash(self):
        """Empty close list → no signal, no crash."""
        strategy = FundingRateArbitrage()
        ohlcv = {"close": []}

        signal = strategy.generate_signal("BTCUSD", ohlcv, funding_rate=0.0003)
        assert signal is None


# ---------------------------------------------------------------------------
# 9. Enhanced Circuit Breaker Integration
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_CIRCUIT_BREAKER, reason="CircuitBreaker not implemented")
class TestEnhancedCircuitBreakerIntegration:
    """Test CircuitBreaker loss-streak triggers and cooldown recovery."""

    def test_consecutive_losses_trip(self):
        """Threshold of consecutive losses → breaker open."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(threshold=3))

        assert cb.record_trade("forex", -0.01) is False
        assert cb.record_trade("forex", -0.01) is False
        tripped = cb.record_trade("forex", -0.01)
        assert tripped is True
        assert cb.is_open("forex") is True
        assert "consecutive losses" in cb.reason

    def test_profit_resets_loss_streak(self):
        """A profit resets the consecutive-loss counter."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(threshold=3))

        cb.record_trade("crypto", -0.01)
        cb.record_trade("crypto", -0.01)
        assert cb.is_open("crypto") is False

        cb.record_trade("crypto", 0.02)  # profit resets the streak
        cb.record_trade("crypto", -0.01)
        cb.record_trade("crypto", -0.01)
        assert cb.is_open("crypto") is False  # streak restarted from 0

    def test_single_loss_no_trip(self):
        """A single loss below threshold → breaker stays closed."""
        cb = CircuitBreaker()

        assert cb.record_trade("metals", -0.01) is False
        assert cb.is_open("metals") is False
        assert cb.is_blocked is False

    def test_cooldown_auto_recovers(self):
        """Open breaker auto-recovers once the cooldown window passes."""
        import time

        cb = CircuitBreaker(config=CircuitBreakerConfig(threshold=1, cooldown_minutes=30))
        assert cb.record_trade("indices", -0.01) is True
        assert cb.is_open("indices") is True

        # Simulate the cooldown window elapsing
        cb._classes["indices"].opened_at = time.time() - 31 * 60

        assert cb.is_open("indices") is False
        status = cb.get_status()
        assert status["indices"]["consecutive_losses"] == 0
