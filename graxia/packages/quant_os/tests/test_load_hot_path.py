"""
Load Test — Hot Path Latency Verification.

Tests the critical trading loop components under concurrent load:
  - MacroRegimeCache.get() — O(1) atomic read
  - RiskAuditor._check_macro_lockdown() — reads from cache
  - PortfolioManager.act() — hierarchical veto computation
  - Full signal flow: observe → act → result

Target: < 10ms p99 latency for all hot path operations.
"""

import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from graxia.packages.quant_os.core.canonical.macro_regime import (
    MacroRegimeCache,
    RegimeBias,
    get_macro_regime,
    get_position_multiplier,
)
from graxia.packages.quant_os.core.agents.risk_auditor import RiskAuditorAgent
from graxia.packages.quant_os.core.agents.portfolio_manager import PortfolioManagerAgent
from graxia.packages.quant_os.core.events import SignalEvent, RiskEvent
from graxia.packages.quant_os.core.enums import SignalType

HOT_PATH_BUDGET_MS = 10.0
ITERATIONS = 10000
CONCURRENT_THREADS = 8


class TestHotPath_Latency:
    """Test hot path latency under load."""

    def test_macro_regime_cache_read_latency(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.NEUTRAL, 0.5, 1.0, "NORMAL")

        latencies = []
        for _ in range(ITERATIONS):
            start = time.perf_counter_ns()
            _ = cache.get()
            _ = get_position_multiplier()
            _ = get_macro_regime()
            end = time.perf_counter_ns()
            latencies.append((end - start) / 1_000_000)

        p50 = statistics.median(latencies)
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]

        assert p50 < HOT_PATH_BUDGET_MS, f"p50={p50:.3f}ms exceeds {HOT_PATH_BUDGET_MS}ms"
        assert p99 < HOT_PATH_BUDGET_MS, f"p99={p99:.3f}ms exceeds {HOT_PATH_BUDGET_MS}ms"

    def test_concurrent_read_latency(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.BEARISH, 0.8, 0.5, "HIGH_UNCERTAINTY")

        latencies = []
        lock = threading.Lock()

        def read_cache():
            for _ in range(ITERATIONS // CONCURRENT_THREADS):
                start = time.perf_counter_ns()
                _ = cache.get()
                _ = get_position_multiplier()
                end = time.perf_counter_ns()
                with lock:
                    latencies.append((end - start) / 1_000_000)

        threads = [threading.Thread(target=read_cache) for _ in range(CONCURRENT_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        p50 = statistics.median(latencies)
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]

        assert p50 < HOT_PATH_BUDGET_MS, f"concurrent p50={p50:.3f}ms"
        assert p99 < HOT_PATH_BUDGET_MS, f"concurrent p99={p99:.3f}ms"

    def test_risk_auditor_latency(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.NEUTRAL, 0.5, 1.0, "NORMAL")
        ra = RiskAuditorAgent()

        latencies = []
        for _ in range(1000):
            sig = SignalEvent(
                symbol="XAUUSD", signal_type=SignalType.BUY, confidence=0.8,
                entry_price=2400.0, stop_loss=2390.0, take_profit=2430.0,
                source="technical_analyst",
            )
            ra.observe(sig)
            start = time.perf_counter_ns()
            _ = ra.act()
            end = time.perf_counter_ns()
            latencies.append((end - start) / 1_000_000)

        p99 = sorted(latencies)[int(len(latencies) * 0.99)]
        assert p99 < HOT_PATH_BUDGET_MS, f"risk_auditor p99={p99:.3f}ms"

    def test_portfolio_manager_latency(self):
        pm = PortfolioManagerAgent()

        latencies = []
        for _ in range(1000):
            sig = SignalEvent(
                symbol="XAUUSD", signal_type=SignalType.BUY, confidence=0.8,
                entry_price=2400.0, stop_loss=2390.0, take_profit=2430.0,
                source="technical_analyst",
            )
            risk = RiskEvent(check_name="audit", passed=True, source="risk_auditor")
            pm.observe(sig)
            pm.observe(risk)
            start = time.perf_counter_ns()
            _ = pm.act()
            end = time.perf_counter_ns()
            latencies.append((end - start) / 1_000_000)

        p99 = sorted(latencies)[int(len(latencies) * 0.99)]
        assert p99 < HOT_PATH_BUDGET_MS, f"portfolio_manager p99={p99:.3f}ms"

    def test_full_signal_flow_latency(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.NEUTRAL, 0.5, 1.0, "NORMAL")

        ra = RiskAuditorAgent()
        pm = PortfolioManagerAgent()

        latencies = []
        for _ in range(1000):
            sig = SignalEvent(
                symbol="XAUUSD", signal_type=SignalType.BUY, confidence=0.8,
                entry_price=2400.0, stop_loss=2390.0, take_profit=2430.0,
                source="technical_analyst",
            )

            start = time.perf_counter_ns()

            ra.observe(sig)
            risk = ra.act()
            pm.observe(sig)
            pm.observe(risk)
            final = pm.act()

            end = time.perf_counter_ns()
            latencies.append((end - start) / 1_000_000)

        p99 = sorted(latencies)[int(len(latencies) * 0.99)]
        assert p99 < HOT_PATH_BUDGET_MS, f"full_flow p99={p99:.3f}ms"

    def test_concurrent_signal_flow(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.NEUTRAL, 0.5, 1.0, "NORMAL")

        latencies = []
        lock = threading.Lock()

        def process():
            ra = RiskAuditorAgent()
            pm = PortfolioManagerAgent()
            for _ in range(100):
                sig = SignalEvent(
                    symbol="XAUUSD", signal_type=SignalType.BUY, confidence=0.8,
                    entry_price=2400.0, stop_loss=2390.0, take_profit=2430.0,
                    source="technical_analyst",
                )
                risk = RiskEvent(check_name="audit", passed=True, source="risk_auditor")
                start = time.perf_counter_ns()
                ra.observe(sig)
                risk_event = ra.act()
                pm.observe(sig)
                pm.observe(risk_event)
                pm.act()
                end = time.perf_counter_ns()
                with lock:
                    latencies.append((end - start) / 1_000_000)

        with ThreadPoolExecutor(max_workers=CONCURRENT_THREADS) as ex:
            futures = [ex.submit(process) for _ in range(CONCURRENT_THREADS)]
            for f in as_completed(futures):
                f.result()

        p99 = sorted(latencies)[int(len(latencies) * 0.99)]
        assert p99 < HOT_PATH_BUDGET_MS, f"concurrent_flow p99={p99:.3f}ms"

    def test_no_http_in_hot_path(self):
        import unittest.mock as mock

        with mock.patch("httpx.AsyncClient.post", side_effect=AssertionError("HTTP in hot path!")):
            cache = MacroRegimeCache()
            cache.update_from_sentiment(RegimeBias.NEUTRAL, 0.5, 1.0, "NORMAL")
            ra = RiskAuditorAgent()
            pm = PortfolioManagerAgent()
            for _ in range(100):
                sig = SignalEvent(
                    symbol="XAUUSD", signal_type=SignalType.BUY, confidence=0.8,
                    entry_price=2400.0, stop_loss=2390.0, take_profit=2430.0,
                    source="technical_analyst",
                )
                risk = RiskEvent(check_name="audit", passed=True, source="risk_auditor")
                ra.observe(sig)
                risk_event = ra.act()
                pm.observe(sig)
                pm.observe(risk_event)
                pm.act()
