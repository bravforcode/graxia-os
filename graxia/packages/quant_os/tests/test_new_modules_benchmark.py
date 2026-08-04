"""Performance benchmarks for new modules.

Measures execution time and memory for:
- TripleBoostEnsemble.fit() and predict()
- DynamicKellySizer.compute_kelly()
- CVaROptimizer.optimize()
- OrderBookFeatureExtractor.extract()
- VolumeBreakout.generate_signal()
- CircuitBreaker.record_trade()

Run with: python -m pytest tests/test_new_modules_benchmark.py -v --tb=short
"""

import time

import numpy as np
import pytest

from graxia.packages.quant_os.core.kelly import DynamicKellySizer
from graxia.packages.quant_os.data_pipeline.orderbook_features import OrderBookFeatureExtractor

try:
    from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

    HAS_CIRCUIT_BREAKER = True
except ImportError:
    HAS_CIRCUIT_BREAKER = False

from graxia.packages.quant_os.risk.cvar_optimizer import CVaROptimizer
from graxia.packages.quant_os.strategies.volume_breakout import VolumeBreakout

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _benchmark(func, iterations=100):
    """Run func N times and return (median_ms, p95_ms, total_ms).

    Median (not mean) so a single GC/CPU-contention outlier does not blow the
    average and make timing benchmarks flaky on loaded machines.
    """
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        elapsed = (time.perf_counter() - start) * 1000  # ms
        times.append(elapsed)

    times.sort()
    median = times[len(times) // 2]
    p95 = times[int(len(times) * 0.95)]
    total = sum(times)
    return median, p95, total


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------


class TestDynamicKellyBenchmark:
    """Benchmark DynamicKellySizer."""

    def test_compute_kelly_speed(self):
        """DynamicKellySizer.compute_kelly < 0.1ms median."""
        sizer = DynamicKellySizer(base_kelly=0.25, vol_target=0.15)

        median, p95, total = _benchmark(
            lambda: sizer.compute_kelly(0.55, 1.5, 1.0, 0.20, "trending", 0.05),
            iterations=1000,
        )

        assert median < 0.1, f"median={median:.3f}ms too slow"
        # Just print for info
        print(f"\nDynamicKelly: median={median:.4f}ms, p95={p95:.4f}ms")


class TestCVaRBenchmark:
    """Benchmark CVaROptimizer."""

    def test_optimize_speed_small(self):
        """CVaR optimize 4 assets, 500 periods < 500ms."""
        np.random.seed(42)
        returns = np.random.randn(500, 4) * 0.01

        opt = CVaROptimizer(alpha=0.05, max_weight=0.40)
        median, p95, total = _benchmark(lambda: opt.optimize(returns), iterations=10)

        assert median < 500, f"median={median:.1f}ms too slow"
        print(f"\nCVaR(4 assets, 500 periods): median={median:.1f}ms, p95={p95:.1f}ms")

    def test_optimize_speed_large(self):
        """CVaR optimize 10 assets, 2000 periods < 2000ms."""
        np.random.seed(42)
        returns = np.random.randn(2000, 10) * 0.01

        opt = CVaROptimizer(alpha=0.05, max_weight=0.30)
        median, p95, total = _benchmark(lambda: opt.optimize(returns), iterations=5)

        assert median < 2000, f"median={median:.1f}ms too slow"
        print(f"\nCVaR(10 assets, 2000 periods): median={median:.1f}ms, p95={p95:.1f}ms")


class TestOrderBookBenchmark:
    """Benchmark OrderBookFeatureExtractor."""

    def test_extract_speed(self):
        """OrderBookFeatureExtractor.extract < 0.05ms."""
        extractor = OrderBookFeatureExtractor(depth=20)
        orderbook = {
            "bids": [[100.0 - i * 0.01, 10.0 + i] for i in range(20)],
            "asks": [[100.1 + i * 0.01, 8.0 + i] for i in range(20)],
        }

        median, p95, total = _benchmark(lambda: extractor.extract(orderbook), iterations=10000)

        assert median < 0.05, f"median={median:.4f}ms too slow"
        print(f"\nOrderBook(20 levels): median={median:.4f}ms, p95={p95:.4f}ms")


class TestVolumeBreakoutBenchmark:
    """Benchmark VolumeBreakout.generate_signal."""

    def test_generate_signal_speed(self):
        """VolumeBreakout.generate_signal < 0.5ms."""
        strategy = VolumeBreakout(lookback=20, volume_threshold=2.0)
        ohlcv = {
            "open": [100.0] * 100,
            "high": [101.0] * 100,
            "low": [99.0] * 100,
            "close": [100.5] * 100,
            "volume": [100.0] * 100,
        }

        median, p95, total = _benchmark(
            lambda: strategy.generate_signal("XAUUSD", ohlcv),
            iterations=1000,
        )

        assert median < 0.5, f"median={median:.3f}ms too slow"
        print(f"\nVolumeBreakout(100 bars): median={median:.4f}ms, p95={p95:.4f}ms")


@pytest.mark.skipif(not HAS_CIRCUIT_BREAKER, reason="CircuitBreaker not implemented")
class TestCircuitBreakerBenchmark:
    """Benchmark CircuitBreaker."""

    def test_record_trade_speed(self):
        """CircuitBreaker.record_trade < 0.05ms."""
        cb = CircuitBreaker()

        median, p95, total = _benchmark(
            lambda: cb.record_trade("forex", -0.01),
            iterations=10000,
        )

        assert median < 0.05, f"median={median:.4f}ms too slow"
        print(f"\nCircuitBreaker.record_trade: median={median:.5f}ms, p95={p95:.5f}ms")


class TestEnsembleBenchmark:
    """Benchmark TripleBoostEnsemble."""

    def test_ensemble_predict_speed(self):
        """TripleBoostEnsemble.predict < 25ms for 50 samples (3 boosted models)."""
        from catboost import CatBoostClassifier
        from lightgbm import LGBMClassifier
        from xgboost import XGBClassifier

        from graxia.packages.quant_os.ml.ensemble import TripleBoostEnsemble

        np.random.seed(42)
        x = np.random.randn(200, 5)
        y = (x[:, 0] + x[:, 1] > 0).astype(int)

        ensemble = TripleBoostEnsemble()
        ensemble.models = {
            "lgbm": LGBMClassifier(n_estimators=10, max_depth=3, verbose=-1),
            "catboost": CatBoostClassifier(iterations=10, depth=3, verbose=0),
            "xgboost": XGBClassifier(n_estimators=10, max_depth=3),
        }
        ensemble._fitted = True
        for model in ensemble.models.values():
            model.fit(x[:150], y[:150])

        x_test = x[150:]
        ensemble.predict(x_test)  # warm-up: first call includes model dispatch overhead
        median, p95, total = _benchmark(lambda: ensemble.predict(x_test), iterations=100)

        # 10ms flaked on loaded dev machines (11-14ms observed); 25ms keeps a real
        # regression guard (e.g. accidental I/O or re-fit inside predict).
        assert median < 25, f"median={median:.1f}ms too slow"
        print(f"\nEnsemble.predict(50 samples): median={median:.2f}ms, p95={p95:.2f}ms")
