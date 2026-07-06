"""Load tests for the autonomous trading loop.

Tests performance under burst and sustained load for rate limiter,
persistence layer, and orchestrator.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from datetime import UTC, datetime
from typing import Any

from graxia.packages.quant_os.autonomous.decision_engine import TradeDecision
from graxia.packages.quant_os.autonomous.persistence import TradeStore
from graxia.packages.quant_os.autonomous.rate_limiter import RateLimiter
from graxia.packages.quant_os.core.enums import SignalType

# ── Rate Limiter Load ────────────────────────────────────────────────────────


class TestRateLimiterLoad:
    """Load tests for rate limiter."""

    def test_rate_limiter_under_burst(self) -> None:
        limiter = RateLimiter(limits={"groq": 50})

        start = time.monotonic()
        for _ in range(50):
            assert limiter.can_proceed("groq") is True
            limiter.record_request("groq")
        elapsed = time.monotonic() - start

        assert limiter.can_proceed("groq") is False
        assert elapsed < 1.0

    def test_rate_limiter_sustained_load(self) -> None:
        limiter = RateLimiter(limits={"groq": 100})

        accepted = 0
        rejected = 0
        start = time.monotonic()

        for _ in range(120):
            if limiter.can_proceed("groq"):
                limiter.record_request("groq")
                accepted += 1
            else:
                rejected += 1

        elapsed = time.monotonic() - start

        assert accepted == 100
        assert rejected == 20
        assert elapsed < 2.0

    def test_rate_limiter_multi_provider_burst(self) -> None:
        limiter = RateLimiter(limits={"groq": 30, "cerebras": 30, "openrouter": 30})

        start = time.monotonic()
        for _ in range(30):
            limiter.record_request("groq")
            limiter.record_request("cerebras")
            limiter.record_request("openrouter")
        elapsed = time.monotonic() - start

        assert limiter.can_proceed("groq") is False
        assert limiter.can_proceed("cerebras") is False
        assert limiter.can_proceed("openrouter") is False
        assert elapsed < 2.0

    def test_rate_limiter_refill_after_burst(self) -> None:
        limiter = RateLimiter(limits={"groq": 5})

        for _ in range(5):
            limiter.record_request("groq")

        assert limiter.can_proceed("groq") is False

        bucket = limiter._buckets["groq"]
        bucket.tokens = 3.0
        bucket.last_refill = time.monotonic() - 1.0

        assert limiter.can_proceed("groq") is True


# ── Persistence Load ─────────────────────────────────────────────────────────


def _close_store(store: TradeStore) -> None:
    """Close all thread-local SQLite connections in a TradeStore."""

    conn = getattr(store._local, "conn", None)
    if conn is not None:
        conn.close()
        store._local.conn = None


def _make_decision_dict(i: int) -> dict[str, Any]:
    return {
        "symbol": "XAUUSD",
        "direction": "BUY",
        "confidence": 0.82,
        "entry": 2350.0,
        "sl": 2340.0,
        "tp": 2370.0,
        "reasoning": f"Load test decision {i}",
        "red_flags": "",
        "timestamp": datetime.now(UTC).isoformat(),
        "timeframe": "1h",
        "snapshot_ts": "",
        "latency_ms": 150.0,
        "llm_provider": "groq",
    }


def _make_execution_dict(i: int) -> dict[str, Any]:
    return {
        "symbol": "XAUUSD",
        "direction": "BUY",
        "confidence": 0.82,
        "entry": 2350.0,
        "stop_loss": 2340.0,
        "take_profit": 2370.0,
        "success": True,
        "order_id": f"auto-{i:04d}",
        "broker_order_id": f"MT5-{i:04d}",
        "error": "",
        "approval_required": False,
        "mode": "paper",
        "timestamp": datetime.now(UTC).isoformat(),
    }


class TestPersistenceLoad:
    """Load tests for persistence layer."""

    def test_store_many_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "load_test.db")
            store = TradeStore(db_path=db_path)

            start = time.monotonic()
            for i in range(500):
                store.save_decision(_make_decision_dict(i))
            elapsed = time.monotonic() - start

            _close_store(store)
            assert elapsed < 15.0
            store2 = TradeStore(db_path=db_path)
            recent = store2.get_recent_decisions("XAUUSD", limit=500)
            _close_store(store2)
            assert len(recent) == 500

    def test_store_concurrent_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "concurrent_test.db")
            store = TradeStore(db_path=db_path)

            def write_decision(idx: int) -> None:
                store.save_decision(
                    {
                        "symbol": "XAUUSD",
                        "direction": "BUY",
                        "confidence": 0.8,
                        "entry": 2350.0,
                        "sl": 2340.0,
                        "tp": 2370.0,
                        "reasoning": f"Concurrent {idx}",
                        "red_flags": "",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "timeframe": "1h",
                        "snapshot_ts": "",
                        "latency_ms": 100.0,
                        "llm_provider": "groq",
                    }
                )
                conn = getattr(store._local, "conn", None)
                if conn is not None:
                    conn.close()
                    store._local.conn = None

            threads = []
            import threading

            for i in range(20):
                t = threading.Thread(target=write_decision, args=(i,))
                threads.append(t)
                t.start()

            for t in threads:
                t.join(timeout=10)

            _close_store(store)
            store2 = TradeStore(db_path=db_path)
            recent = store2.get_recent_decisions("XAUUSD", limit=100)
            _close_store(store2)
            assert len(recent) == 20

    def test_store_many_executions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "exec_test.db")
            store = TradeStore(db_path=db_path)

            start = time.monotonic()
            for i in range(200):
                store.save_execution(_make_execution_dict(i))
            elapsed = time.monotonic() - start

            _close_store(store)
            assert elapsed < 15.0
            store2 = TradeStore(db_path=db_path)
            log = store2.get_execution_log(limit=200)
            _close_store(store2)
            assert len(log) == 200

    def test_store_health_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "health_test.db")
            store = TradeStore(db_path=db_path)

            start = time.monotonic()
            for i in range(100):
                store.save_health(
                    {
                        "uptime_seconds": float(i * 60),
                        "total_decisions": i * 10,
                        "total_trades": i * 2,
                        "errors": i,
                        "kill_switch_active": False,
                    }
                )
            elapsed = time.monotonic() - start

            _close_store(store)
            assert elapsed < 2.0

    def test_store_get_daily_stats_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "daily_test.db")
            store = TradeStore(db_path=db_path)

            stats = store.get_daily_stats("2099-01-01")
            _close_store(store)
            assert stats["trades_today"] == 0
            assert stats["realized_pnl"] == 0.0


# ── Orchestrator Performance ─────────────────────────────────────────────────


class TestOrchestratorPerformance:
    """Performance tests for orchestrator."""

    def test_loop_iteration_time(self) -> None:
        from unittest.mock import MagicMock, patch

        from graxia.packages.quant_os.autonomous.chart_monitor import ChartSnapshot
        from graxia.packages.quant_os.autonomous.decision_engine import DecisionEngine

        engine = DecisionEngine(min_confidence=0.65, cooldown_seconds=0)

        mock_provider = MagicMock(name="groq")
        mock_router = MagicMock()
        mock_router._call_llm_chain = MagicMock(
            return_value=(
                '{"direction": "BUY", "confidence": 0.85, "entry": 2350.0, "sl": 2340.0, "tp": 2370.0, "reasoning": "Perf test", "red_flags": []}',
                50.0,
                mock_provider,
            )
        )

        snapshot = ChartSnapshot(
            symbol="XAUUSD",
            timeframe="1h",
            ohlcv=[],
            indicators={},
            screenshot_path=None,
            timestamp=datetime.now(UTC),
        )

        with patch("graxia.packages.quant_os.autonomous.decision_engine.get_router", return_value=mock_router):
            start = time.monotonic()
            for _ in range(10):
                engine._last_analysis.clear()
                asyncio.get_event_loop().run_until_complete(engine.analyze(snapshot))
            elapsed = time.monotonic() - start

        avg_per_iter = elapsed / 10.0
        assert avg_per_iter < 1.0

    def test_memory_usage_bounded(self) -> None:
        from graxia.packages.quant_os.autonomous.chart_monitor import ChartSnapshot
        from graxia.packages.quant_os.autonomous.decision_engine import MAX_HISTORY, DecisionEngine

        engine = DecisionEngine(min_confidence=0.65, cooldown_seconds=0)
        snapshot = ChartSnapshot(
            symbol="XAUUSD",
            timeframe="1h",
            ohlcv=[],
            indicators={},
            screenshot_path=None,
            timestamp=datetime.now(UTC),
        )

        for _ in range(MAX_HISTORY + 50):
            decision = TradeDecision(
                symbol="XAUUSD",
                direction=SignalType.NO_TRADE,
                confidence=0.0,
                entry=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                reasoning="Memory test",
                red_flags=(),
                timestamp=datetime.now(UTC),
            )
            engine._record(decision)

        assert len(engine._history["XAUUSD"]) == MAX_HISTORY

    def test_rate_limiter_throughput(self) -> None:
        limiter = RateLimiter(limits={"groq": 1000})

        start = time.monotonic()
        for _ in range(1000):
            limiter.record_request("groq")
        elapsed = time.monotonic() - start

        assert elapsed < 1.0

    def test_persistence_throughput(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "throughput_test.db")
            store = TradeStore(db_path=db_path)

            start = time.monotonic()
            for i in range(1000):
                store.save_decision(_make_decision_dict(i))
            elapsed = time.monotonic() - start

            _close_store(store)
            writes_per_sec = 1000 / elapsed
            assert writes_per_sec > 100

    def test_decision_engine_cooldown_performance(self) -> None:
        from graxia.packages.quant_os.autonomous.chart_monitor import ChartSnapshot
        from graxia.packages.quant_os.autonomous.decision_engine import DecisionEngine

        engine = DecisionEngine(min_confidence=0.65, cooldown_seconds=300)

        snapshot = ChartSnapshot(
            symbol="XAUUSD",
            timeframe="1h",
            ohlcv=[],
            indicators={},
            screenshot_path=None,
            timestamp=datetime.now(UTC),
        )

        start = time.monotonic()
        for _ in range(100):
            asyncio.get_event_loop().run_until_complete(engine.analyze(snapshot))
        elapsed = time.monotonic() - start

        assert elapsed < 1.0

        history = engine.get_decision_history("XAUUSD")
        assert len(history) == 1
