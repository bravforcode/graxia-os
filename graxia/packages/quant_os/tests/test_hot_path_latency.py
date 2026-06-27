"""
Load Test — Hot Path Latency (< 10ms guarantee).

Tests the critical trading loop components under concurrent load:
  - MacroRegimeCache.get() — O(1) atomic read
  - RiskAuditor._check_macro_lockdown() — reads from cache
  - PortfolioManager.act() — hierarchical veto computation
  - Full signal flow: observe → act → result

RULE: No HTTP calls in hot path. All LLM calls are WARM PATH only.
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

# Target: 10ms = 0.01s
HOT_PATH_BUDGET_MS = 10.0
ITERATIONS = 10000
CONCURRENT_THREADS = 8


class TestMacroRegimeCacheLatency:
    """Test MacroRegimeCache read latency under load."""

    def test_single_read_latency(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.NEUTRAL, 0.5, 1.0, "NORMAL")

        latencies = []
        for _ in range(ITERATIONS):
            start = time.perf_counter_ns()
            _ = cache.get()
            _ = get_position_multiplier()
            _ = get_macro_regime()
            end = time.perf_counter_ns()
            latencies.append((end - start) / 1_000_000)  # ns → ms

        p50 = statistics.median(latencies)
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]
        max_lat = max(latencies)

        assert p50 < HOT_PATH_BUDGET_MS, f"p50={p50:.3f}ms exceeds {HOT_PATH_BUDGET_MS}ms"
        assert p99 < HOT_PATH_BUDGET_MS, f"p99={p99:.3f}ms exceeds {HOT_PATH_BUDGET_MS}ms"
        assert max_lat < HOT_PATH_BUDGET_MS * 2, f"max={max_lat:.3f}ms exceeds 2x budget"

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
                ms = (end - start) / 1_000_000
                with lock:
                    latencies.append(ms)

        threads = [threading.Thread(target=read_cache) for _ in range(CONCURRENT_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        p50 = statistics.median(latencies)
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]
        max_lat = max(latencies)

        assert p50 < HOT_PATH_BUDGET_MS, f"concurrent p50={p50:.3f}ms"
        assert p99 < HOT_PATH_BUDGET_MS, f"concurrent p99={p99:.3f}ms"

    def test_read_under_concurrent_write(self):
        cache = MacroRegimeCache()
        cache.reset()

        read_latencies = []
        write_latencies = []
        read_lock = threading.Lock()
        write_lock = threading.Lock()
        stop_flag = threading.Event()

        def reader():
            while not stop_flag.is_set():
                start = time.perf_counter_ns()
                _ = cache.get()
                end = time.perf_counter_ns()
                ms = (end - start) / 1_000_000
                with read_lock:
                    read_latencies.append(ms)

        def writer():
            biases = [RegimeBias.BULLISH, RegimeBias.BEARISH, RegimeBias.PANIC, RegimeBias.NEUTRAL]
            i = 0
            while not stop_flag.is_set():
                cache.update_from_sentiment(biases[i % len(biases)], 0.5, 1.0, "NORMAL")
                i += 1
                time.sleep(0.0001)  # 100μs between writes

        reader_threads = [threading.Thread(target=reader) for _ in range(4)]
        writer_thread = threading.Thread(target=writer)

        for t in reader_threads:
            t.start()
        writer_thread.start()

        time.sleep(0.5)  # Run for 500ms
        stop_flag.set()

        for t in reader_threads:
            t.join()
        writer_thread.join()

        if read_latencies:
            p99 = sorted(read_latencies)[int(len(read_latencies) * 0.99)]
            assert p99 < HOT_PATH_BUDGET_MS, f"read-under-write p99={p99:.3f}ms"


class TestRiskAuditorLatency:
    """Test RiskAuditor hot path latency."""

    def test_check_macro_lockdown_latency(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.NEUTRAL, 0.5, 1.0, "NORMAL")
        ra = RiskAuditorAgent()

        latencies = []
        for _ in range(ITERATIONS):
            start = time.perf_counter_ns()
            _ = ra._check_macro_lockdown()
            end = time.perf_counter_ns()
            latencies.append((end - start) / 1_000_000)

        p50 = statistics.median(latencies)
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]

        assert p50 < HOT_PATH_BUDGET_MS, f"macro_lockdown p50={p50:.3f}ms"
        assert p99 < HOT_PATH_BUDGET_MS, f"macro_lockdown p99={p99:.3f}ms"

    def test_full_audit_latency(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.NEUTRAL, 0.5, 1.0, "NORMAL")
        ra = RiskAuditorAgent()

        latencies = []
        for _ in range(1000):
            sig = SignalEvent(
                symbol="XAUUSD",
                signal_type=SignalType.BUY,
                confidence=0.8,
                entry_price=2400.0,
                stop_loss=2390.0,
                take_profit=2430.0,
                source="technical_analyst",
            )
            ra.observe(sig)
            start = time.perf_counter_ns()
            _ = ra.act()
            end = time.perf_counter_ns()
            latencies.append((end - start) / 1_000_000)

        p50 = statistics.median(latencies)
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]

        assert p50 < HOT_PATH_BUDGET_MS, f"full_audit p50={p50:.3f}ms"
        assert p99 < HOT_PATH_BUDGET_MS, f"full_audit p99={p99:.3f}ms"


class TestPortfolioManagerLatency:
    """Test PortfolioManager hot path latency."""

    def test_act_latency(self):
        pm = PortfolioManagerAgent()

        latencies = []
        for _ in range(1000):
            sig = SignalEvent(
                symbol="XAUUSD",
                signal_type=SignalType.BUY,
                confidence=0.8,
                entry_price=2400.0,
                stop_loss=2390.0,
                take_profit=2430.0,
                source="technical_analyst",
            )
            pm.observe(sig)
            start = time.perf_counter_ns()
            _ = pm.act()
            end = time.perf_counter_ns()
            latencies.append((end - start) / 1_000_000)

        p50 = statistics.median(latencies)
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]

        assert p50 < HOT_PATH_BUDGET_MS, f"pm_act p50={p50:.3f}ms"
        assert p99 < HOT_PATH_BUDGET_MS, f"pm_act p99={p99:.3f}ms"


class TestFullSignalFlowLatency:
    """Test end-to-end signal flow latency (no LLM calls)."""

    def test_signal_to_final_latency(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.NEUTRAL, 0.5, 1.0, "NORMAL")

        ra = RiskAuditorAgent()
        pm = PortfolioManagerAgent()

        latencies = []
        for _ in range(1000):
            sig = SignalEvent(
                symbol="XAUUSD",
                signal_type=SignalType.BUY,
                confidence=0.8,
                entry_price=2400.0,
                stop_loss=2390.0,
                take_profit=2430.0,
                source="technical_analyst",
            )

            start = time.perf_counter_ns()

            # Step 1: Risk audit
            ra.observe(sig)
            risk = ra.act()

            # Step 2: Portfolio manager
            pm.observe(sig)
            pm.observe(risk)
            final = pm.act()

            end = time.perf_counter_ns()
            latencies.append((end - start) / 1_000_000)

        p50 = statistics.median(latencies)
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]
        max_lat = max(latencies)

        assert p50 < HOT_PATH_BUDGET_MS, f"full_flow p50={p50:.3f}ms"
        assert p99 < HOT_PATH_BUDGET_MS, f"full_flow p99={p99:.3f}ms"
        assert max_lat < HOT_PATH_BUDGET_MS * 3, f"full_flow max={max_lat:.3f}ms"

    def test_concurrent_signal_flow(self):
        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.NEUTRAL, 0.5, 1.0, "NORMAL")

        latencies = []
        lock = threading.Lock()

        def process_signal():
            ra = RiskAuditorAgent()
            pm = PortfolioManagerAgent()
            for _ in range(100):
                sig = SignalEvent(
                    symbol="XAUUSD",
                    signal_type=SignalType.BUY,
                    confidence=0.8,
                    entry_price=2400.0,
                    stop_loss=2390.0,
                    take_profit=2430.0,
                    source="technical_analyst",
                )
                start = time.perf_counter_ns()
                ra.observe(sig)
                risk = ra.act()
                pm.observe(sig)
                pm.observe(risk)
                final = pm.act()
                end = time.perf_counter_ns()
                ms = (end - start) / 1_000_000
                with lock:
                    latencies.append(ms)

        with ThreadPoolExecutor(max_workers=CONCURRENT_THREADS) as executor:
            futures = [executor.submit(process_signal) for _ in range(CONCURRENT_THREADS)]
            for f in as_completed(futures):
                f.result()

        p50 = statistics.median(latencies)
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]

        assert p50 < HOT_PATH_BUDGET_MS, f"concurrent_flow p50={p50:.3f}ms"
        assert p99 < HOT_PATH_BUDGET_MS, f"concurrent_flow p99={p99:.3f}ms"


class TestNoHTTPInHotPath:
    """Verify no HTTP calls happen in hot path components."""

    def test_macro_regime_cache_no_http(self):
        import unittest.mock as mock

        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.NEUTRAL, 0.5, 1.0, "NORMAL")

        with mock.patch("httpx.AsyncClient.post", side_effect=AssertionError("HTTP in hot path!")):
            for _ in range(100):
                _ = cache.get()
                _ = get_position_multiplier()

    def test_risk_auditor_no_http(self):
        import unittest.mock as mock

        cache = MacroRegimeCache()
        cache.update_from_sentiment(RegimeBias.NEUTRAL, 0.5, 1.0, "NORMAL")
        ra = RiskAuditorAgent()

        with mock.patch("httpx.AsyncClient.post", side_effect=AssertionError("HTTP in hot path!")):
            for _ in range(100):
                sig = SignalEvent(
                    symbol="XAUUSD",
                    signal_type=SignalType.BUY,
                    confidence=0.8,
                    entry_price=2400.0,
                    stop_loss=2390.0,
                    take_profit=2430.0,
                    source="technical_analyst",
                )
                ra.observe(sig)
                _ = ra.act()

    def test_portfolio_manager_no_http(self):
        import unittest.mock as mock

        pm = PortfolioManagerAgent()

        with mock.patch("httpx.AsyncClient.post", side_effect=AssertionError("HTTP in hot path!")):
            for _ in range(100):
                sig = SignalEvent(
                    symbol="XAUUSD",
                    signal_type=SignalType.BUY,
                    confidence=0.8,
                    entry_price=2400.0,
                    stop_loss=2390.0,
                    take_profit=2430.0,
                    source="technical_analyst",
                )
                pm.observe(sig)
                _ = pm.act()
