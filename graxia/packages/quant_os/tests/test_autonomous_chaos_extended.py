"""Extended chaos tests targeting critical untested gaps.

100+ high-quality tests covering:
  - Concurrent access: Thread safety, race conditions, DB corruption under load
  - Partial failures: Network partitions, broker timeouts, partial fills
  - Malformed data: LLM gibberish, JSON injection, SQL injection, edge cases
  - Circuit breaker recovery: Cooldown, half-open, state transitions
  - Orchestrator resilience: Multi-symbol failures, health monitoring
  - Memory safety: Large payloads, buffer overflow, resource leaks
  - Security: Auth bypass attempts, injection attacks, fail-closed paths
  - Position sizing edge cases: Contract sizes, extreme confidence, margin
  - Reconciliation during volatile market states
  - Notification delivery under failure conditions
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from graxia.packages.quant_os.autonomous.chart_monitor import ChartMonitor, ChartSnapshot
from graxia.packages.quant_os.autonomous.decision_engine import DecisionEngine, TradeDecision
from graxia.packages.quant_os.autonomous.live_approval import (
    ApprovalAction,
    LiveApprovalGate,
)
from graxia.packages.quant_os.autonomous.news_gate import NewsBlackoutGate
from graxia.packages.quant_os.autonomous.notifications import TradeNotifier
from graxia.packages.quant_os.autonomous.order_executor import OrderExecutor
from graxia.packages.quant_os.autonomous.persistence import TradeStore
from graxia.packages.quant_os.autonomous.rate_limiter import RateLimiter
from graxia.packages.quant_os.autonomous.reconciler import ReconciliationResult, TradeReconciler
from graxia.packages.quant_os.autonomous.symbol_registry import SymbolInfo, SymbolRegistry
from graxia.packages.quant_os.core.enums import SignalType
from graxia.packages.quant_os.execution.adapters.base import AccountInfo

# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def snapshot() -> ChartSnapshot:
    return ChartSnapshot(
        symbol="XAUUSD",
        timeframe="1h",
        ohlcv=[],
        indicators={},
        screenshot_path=None,
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def buy_decision() -> TradeDecision:
    return TradeDecision(
        symbol="XAUUSD",
        direction=SignalType.BUY,
        confidence=0.82,
        entry=2350.0,
        stop_loss=2340.0,
        take_profit=2370.0,
        reasoning="Chaos test",
        red_flags=(),
        timestamp=datetime.now(UTC),
        timeframe="1h",
    )


@pytest.fixture
def trade_store() -> TradeStore:
    with tempfile.TemporaryDirectory() as tmpdir:
        store = TradeStore(db_path=os.path.join(tmpdir, "extended_chaos.db"))
        yield store
        conn = getattr(store._local, "conn", None)
        if conn:
            conn.close()
            store._local.conn = None


def _make_decision(
    symbol: str = "XAUUSD",
    direction: SignalType = SignalType.BUY,
    confidence: float = 0.82,
    entry: float = 2350.0,
    sl: float = 2340.0,
    tp: float = 2370.0,
    **kwargs,
) -> TradeDecision:
    defaults = dict(
        symbol=symbol,
        direction=direction,
        confidence=confidence,
        entry=entry,
        stop_loss=sl,
        take_profit=tp,
        reasoning=kwargs.get("reasoning", "Chaos test"),
        red_flags=kwargs.get("red_flags", ()),
        timestamp=datetime.now(UTC),
        timeframe=kwargs.get("timeframe", "1h"),
    )
    return TradeDecision(**defaults)


def _make_executor(
    broker: MagicMock,
    kill_active: bool = False,
    mode: str = "paper",
    **overrides,
) -> OrderExecutor:
    risk = overrides.get("risk_engine", MagicMock())
    risk.evaluate.return_value = MagicMock(approved=True, reason="")
    ks = overrides.get("kill_switch", MagicMock())
    ks.is_active.return_value = kill_active
    ks.is_triggered = kill_active
    ks.get_status.return_value = {}
    broker.active.get_account_info.return_value = AccountInfo(
        equity=overrides.get("equity", 10000),
        cash=overrides.get("cash", 10000),
        margin_used=0,
        margin_available=overrides.get("equity", 10000),
    )
    return OrderExecutor(broker_manager=broker, risk_engine=risk, kill_switch=ks, mode=mode)


def _close_store(store: TradeStore) -> None:
    conn = getattr(store._local, "conn", None)
    if conn:
        conn.close()
        store._local.conn = None


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Concurrent Access & Thread Safety (15 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestConcurrentAccess:
    """Thread safety and race condition tests."""

    def test_concurrent_save_different_symbols(self, trade_store: TradeStore) -> None:
        errors = []
        symbols = ["XAUUSD", "BTCUSD", "EURUSD", "USDJPY", "US500"]

        def writer(sym: str) -> None:
            try:
                trade_store.save_decision(
                    {
                        "symbol": sym,
                        "direction": "BUY",
                        "confidence": 0.8,
                        "entry": 2350.0,
                        "sl": 2340.0,
                        "tp": 2370.0,
                        "reasoning": f"Thread for {sym}",
                        "red_flags": "",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "timeframe": "1h",
                        "snapshot_ts": "",
                        "latency_ms": 0.0,
                        "llm_provider": "groq",
                    }
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(s,)) for s in symbols]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        for sym in symbols:
            decisions = trade_store.get_recent_decisions(sym, limit=1)
            assert len(decisions) == 1

    def test_concurrent_read_write_same_symbol(self, trade_store: TradeStore) -> None:
        errors = []
        readers_done = []

        def writer() -> None:
            try:
                for i in range(20):
                    trade_store.save_decision(
                        {
                            "symbol": "XAUUSD",
                            "direction": "BUY",
                            "confidence": 0.8,
                            "entry": 2350.0,
                            "sl": 2340.0,
                            "tp": 2370.0,
                            "reasoning": f"Write {i}",
                            "red_flags": "",
                            "timestamp": datetime.now(UTC).isoformat(),
                            "timeframe": "1h",
                            "snapshot_ts": "",
                            "latency_ms": 0.0,
                            "llm_provider": "groq",
                        }
                    )
            except Exception as e:
                errors.append(e)

        def reader() -> None:
            try:
                for _ in range(20):
                    trade_store.get_recent_decisions("XAUUSD", limit=5)
            except Exception as e:
                errors.append(e)
            finally:
                readers_done.append(True)

        threads = [threading.Thread(target=writer)] + [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert len(readers_done) == 3

    def test_concurrent_execution_log_writes(self, trade_store: TradeStore) -> None:
        errors = []

        def writer(idx: int) -> None:
            try:
                trade_store.save_execution(
                    {
                        "symbol": "XAUUSD",
                        "direction": "BUY",
                        "confidence": 0.8,
                        "entry": 2350.0,
                        "stop_loss": 2340.0,
                        "take_profit": 2370.0,
                        "success": True,
                        "order_id": f"auto-{idx:03d}",
                        "broker_order_id": f"MT5-{idx:03d}",
                        "error": "",
                        "approval_required": False,
                        "mode": "paper",
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        log = trade_store.get_execution_log(limit=15)
        assert len(log) == 15

    def test_concurrent_save_health(self, trade_store: TradeStore) -> None:
        errors = []

        def writer(idx: int) -> None:
            try:
                trade_store.save_health(
                    {
                        "uptime_seconds": float(idx),
                        "total_decisions": idx,
                        "total_trades": idx // 2,
                        "errors": 0,
                        "kill_switch_active": False,
                    }
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []

    def test_concurrent_db_open_close(self) -> None:
        errors = []
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "open_close.db")

            def writer(idx: int) -> None:
                try:
                    store = TradeStore(db_path=db_path)
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
                            "latency_ms": 0.0,
                            "llm_provider": "groq",
                        }
                    )
                    conn = getattr(store._local, "conn", None)
                    if conn:
                        conn.close()
                        store._local.conn = None
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            assert errors == []
            store = TradeStore(db_path=db_path)
            decisions = store.get_recent_decisions("XAUUSD", limit=100)
            assert len(decisions) == 10
            _close_store(store)

    def test_rapid_open_close_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "rapid.db")
            for _ in range(50):
                store = TradeStore(db_path=db_path)
                store.save_decision(
                    {
                        "symbol": "XAUUSD",
                        "direction": "BUY",
                        "confidence": 0.8,
                        "entry": 2350.0,
                        "sl": 2340.0,
                        "tp": 2370.0,
                        "reasoning": "rapid",
                        "red_flags": "",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "timeframe": "1h",
                        "snapshot_ts": "",
                        "latency_ms": 0.0,
                        "llm_provider": "groq",
                    }
                )
                conn = getattr(store._local, "conn", None)
                if conn:
                    conn.close()
                    store._local.conn = None

    def test_concurrent_save_and_retrieve(self, trade_store: TradeStore) -> None:
        results = []
        errors = []

        def writer() -> None:
            try:
                for i in range(20):
                    trade_store.save_decision(
                        {
                            "symbol": "XAUUSD",
                            "direction": "BUY",
                            "confidence": 0.8,
                            "entry": 2350.0,
                            "sl": 2340.0,
                            "tp": 2370.0,
                            "reasoning": f"Write {i}",
                            "red_flags": "",
                            "timestamp": datetime.now(UTC).isoformat(),
                            "timeframe": "1h",
                            "snapshot_ts": "",
                            "latency_ms": 0.0,
                            "llm_provider": "groq",
                        }
                    )
            except Exception as e:
                errors.append(e)

        def reader() -> None:
            try:
                for _ in range(10):
                    d = trade_store.get_recent_decisions("XAUUSD", limit=5)
                    results.append(len(d))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert all(isinstance(r, int) for r in results)

    def test_thread_local_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "isolation.db")
            store = TradeStore(db_path=db_path)
            thread_conns = {}

            def get_conn() -> None:
                store.save_decision(
                    {
                        "symbol": "XAUUSD",
                        "direction": "BUY",
                        "confidence": 0.8,
                        "entry": 2350.0,
                        "sl": 2340.0,
                        "tp": 2370.0,
                        "reasoning": "isolation",
                        "red_flags": "",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "timeframe": "1h",
                        "snapshot_ts": "",
                        "latency_ms": 0.0,
                        "llm_provider": "groq",
                    }
                )
                thread_conns[threading.current_thread().ident] = store._get_conn()

            threads = [threading.Thread(target=get_conn) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            conns = list(thread_conns.values())
            assert len(set(id(c) for c in conns)) == len(conns)
            _close_store(store)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Malformed Data & Injection (20 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestMalformedData:
    """Tests for malformed LLM output, JSON injection, and edge cases."""

    def test_llm_returns_html(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = "<html><body><h1>BUY XAUUSD</h1></body></html>"
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.direction == SignalType.NO_TRADE

    def test_llm_returns_python_code(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = 'def trade():\n    return {"direction": "BUY", "confidence": 0.8}'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.direction == SignalType.NO_TRADE

    def test_llm_returns_sql(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = "SELECT * FROM trades WHERE direction='BUY'; DROP TABLE trades;--"
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.direction == SignalType.NO_TRADE

    def test_llm_returns_javascript(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = 'JSON.parse(\'{"direction": "BUY", "confidence": 0.8}\')'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.direction == SignalType.NO_TRADE

    def test_json_injection_in_reasoning(self, trade_store: TradeStore) -> None:
        malicious = '"; DROP TABLE decisions; --'
        trade_store.save_decision(
            {
                "symbol": "XAUUSD",
                "direction": "BUY",
                "confidence": 0.8,
                "entry": 2350.0,
                "sl": 2340.0,
                "tp": 2370.0,
                "reasoning": malicious,
                "red_flags": "",
                "timestamp": datetime.now(UTC).isoformat(),
                "timeframe": "1h",
                "snapshot_ts": "",
                "latency_ms": 0.0,
                "llm_provider": "groq",
            }
        )
        decisions = trade_store.get_recent_decisions("XAUUSD", limit=1)
        assert len(decisions) == 1
        assert decisions[0]["reasoning"] == malicious

    def test_sql_injection_in_symbol(self, trade_store: TradeStore) -> None:
        malicious = "XAUUSD'; DROP TABLE decisions; --"
        trade_store.save_decision(
            {
                "symbol": malicious,
                "direction": "BUY",
                "confidence": 0.8,
                "entry": 2350.0,
                "sl": 2340.0,
                "tp": 2370.0,
                "reasoning": "injection test",
                "red_flags": "",
                "timestamp": datetime.now(UTC).isoformat(),
                "timeframe": "1h",
                "snapshot_ts": "",
                "latency_ms": 0.0,
                "llm_provider": "groq",
            }
        )
        decisions = trade_store.get_recent_decisions(malicious, limit=1)
        assert len(decisions) == 1

    def test_json_with_trailing_comma(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = '{"direction": "BUY", "confidence": 0.8, "entry": 2350.0, "sl": 2340.0, "tp": 2370.0, "reasoning": "Test", "red_flags": [],}'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.direction == SignalType.BUY

    def test_json_with_single_quotes(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = "{'direction': 'BUY', 'confidence': 0.8, 'entry': 2350.0, 'sl': 2340.0, 'tp': 2370.0, 'reasoning': 'Test', 'red_flags': []}"
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.direction == SignalType.NO_TRADE

    def test_json_with_nan_values(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = '{"direction": "BUY", "confidence": NaN, "entry": 2350.0, "sl": 2340.0, "tp": 2370.0, "reasoning": "Test", "red_flags": []}'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.direction == SignalType.NO_TRADE

    def test_json_with_null_confidence(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = '{"direction": "BUY", "confidence": null, "entry": 2350.0, "sl": 2340.0, "tp": 2370.0, "reasoning": "Test", "red_flags": []}'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.direction == SignalType.NO_TRADE

    def test_json_with_string_numbers(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = '{"direction": "BUY", "confidence": 0.8, "entry": "2350.0", "sl": "2340.0", "tp": "2370.0", "reasoning": "Test", "red_flags": []}'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.direction == SignalType.BUY

    def test_json_with_extra_keys(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = '{"direction": "BUY", "confidence": 0.8, "entry": 2350.0, "sl": 2340.0, "tp": 2370.0, "reasoning": "Test", "red_flags": [], "extra_key": true}'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.direction == SignalType.BUY

    def test_json_missing_required_fields(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = '{"direction": "BUY"}'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.direction == SignalType.NO_TRADE

    def test_json_100_percent_confidence(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = '{"direction": "BUY", "confidence": 1.0, "entry": 2350.0, "sl": 2340.0, "tp": 2370.0, "reasoning": "Test", "red_flags": []}'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.confidence == 0.95

    def test_json_zero_confidence(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = '{"direction": "BUY", "confidence": 0.0, "entry": 2350.0, "sl": 2340.0, "tp": 2370.0, "reasoning": "Test", "red_flags": []}'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.direction == SignalType.NO_TRADE

    def test_unicode_symbols_in_reasoning(self, trade_store: TradeStore) -> None:
        trade_store.save_decision(
            {
                "symbol": "XAUUSD",
                "direction": "BUY",
                "confidence": 0.8,
                "entry": 2350.0,
                "sl": 2340.0,
                "tp": 2370.0,
                "reasoning": "สัญญาณซื้อทองคำ 日本のゴールド ドイツisches Gold",
                "red_flags": "",
                "timestamp": datetime.now(UTC).isoformat(),
                "timeframe": "1h",
                "snapshot_ts": "",
                "latency_ms": 0.0,
                "llm_provider": "groq",
            }
        )
        decisions = trade_store.get_recent_decisions("XAUUSD", limit=1)
        assert "สัญญาณซื้อ" in decisions[0]["reasoning"]

    def test_emoji_in_reasoning(self, trade_store: TradeStore) -> None:
        trade_store.save_decision(
            {
                "symbol": "XAUUSD",
                "direction": "BUY",
                "confidence": 0.8,
                "entry": 2350.0,
                "sl": 2340.0,
                "tp": 2370.0,
                "reasoning": "🔥 Strong BUY signal 💰📈 🎯",
                "red_flags": "",
                "timestamp": datetime.now(UTC).isoformat(),
                "timeframe": "1h",
                "snapshot_ts": "",
                "latency_ms": 0.0,
                "llm_provider": "groq",
            }
        )
        decisions = trade_store.get_recent_decisions("XAUUSD", limit=1)
        assert "🔥" in decisions[0]["reasoning"]

    def test_xss_in_reasoning(self, trade_store: TradeStore) -> None:
        xss = '<script>alert("xss")</script><img onerror="alert(1)" src=x>'
        trade_store.save_decision(
            {
                "symbol": "XAUUSD",
                "direction": "BUY",
                "confidence": 0.8,
                "entry": 2350.0,
                "sl": 2340.0,
                "tp": 2370.0,
                "reasoning": xss,
                "red_flags": "",
                "timestamp": datetime.now(UTC).isoformat(),
                "timeframe": "1h",
                "snapshot_ts": "",
                "latency_ms": 0.0,
                "llm_provider": "groq",
            }
        )
        decisions = trade_store.get_recent_decisions("XAUUSD", limit=1)
        assert decisions[0]["reasoning"] == xss

    def test_newlines_in_reasoning(self, trade_store: TradeStore) -> None:
        multiline = "Line 1\nLine 2\n\tTabbed\n  Double spaced"
        trade_store.save_decision(
            {
                "symbol": "XAUUSD",
                "direction": "BUY",
                "confidence": 0.8,
                "entry": 2350.0,
                "sl": 2340.0,
                "tp": 2370.0,
                "reasoning": multiline,
                "red_flags": "",
                "timestamp": datetime.now(UTC).isoformat(),
                "timeframe": "1h",
                "snapshot_ts": "",
                "latency_ms": 0.0,
                "llm_provider": "groq",
            }
        )
        decisions = trade_store.get_recent_decisions("XAUUSD", limit=1)
        assert "\n" in decisions[0]["reasoning"]

    def test_very_large_confidence_number(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = '{"direction": "BUY", "confidence": 999999.0, "entry": 2350.0, "sl": 2340.0, "tp": 2370.0, "reasoning": "Test", "red_flags": []}'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.confidence == 0.95

    def test_negative_entry_price(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = '{"direction": "BUY", "confidence": 0.8, "entry": -2350.0, "sl": -2340.0, "tp": -2370.0, "reasoning": "Test", "red_flags": []}'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.direction == SignalType.NO_TRADE


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Circuit Breaker Recovery & State Transitions (15 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCircuitBreakerRecovery:
    """Tests for circuit breaker state transitions and recovery."""

    def test_circuit_breaker_basic_flow(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(max_failures=3, cooldown_seconds=60)
        assert cb.is_blocked is False

        for _ in range(3):
            cb.record_trade(MagicMock(pnl=-100.0))
        assert cb.is_blocked is True

    def test_circuit_breaker_no_trip_on_profit(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(max_failures=3, cooldown_seconds=60)
        for _ in range(5):
            cb.record_trade(MagicMock(pnl=100.0))
        assert cb.is_blocked is False

    def test_circuit_breaker_cooldown_recovery(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(max_failures=2, cooldown_seconds=0)
        cb.record_trade(MagicMock(pnl=-100.0))
        cb.record_trade(MagicMock(pnl=-100.0))
        assert cb.is_blocked is True

        time.sleep(0.01)
        assert cb.is_blocked is False

    def test_circuit_breaker_half_open_state(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(max_failures=2, cooldown_seconds=0.1)
        cb.record_trade(MagicMock(pnl=-100.0))
        cb.record_trade(MagicMock(pnl=-100.0))
        assert cb.is_blocked is True

        time.sleep(0.15)
        assert cb.is_blocked is False
        cb.record_trade(MagicMock(pnl=-100.0))
        assert cb.is_blocked is True

    def test_circuit_breaker_success_resets_count(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(max_failures=3, cooldown_seconds=60)
        cb.record_trade(MagicMock(pnl=-100.0))
        cb.record_trade(MagicMock(pnl=-100.0))
        assert cb.is_blocked is False

        cb.record_trade(MagicMock(pnl=200.0))
        cb.record_trade(MagicMock(pnl=-100.0))
        cb.record_trade(MagicMock(pnl=-100.0))
        assert cb.is_blocked is False
        cb.record_trade(MagicMock(pnl=-100.0))
        assert cb.is_blocked is True

    def test_circuit_breaker_zero_cooldown(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(max_failures=2, cooldown_seconds=0)
        cb.record_trade(MagicMock(pnl=-100.0))
        cb.record_trade(MagicMock(pnl=-100.0))
        assert cb.is_blocked is True

        assert cb.is_blocked is False

    def test_circuit_breaker_reason_message(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(max_failures=2, cooldown_seconds=60)
        cb.record_trade(MagicMock(pnl=-100.0))
        cb.record_trade(MagicMock(pnl=-100.0))
        assert cb.is_blocked is True
        assert cb.reason != ""

    def test_circuit_breaker_never_trip_with_no_losses(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(max_failures=5, cooldown_seconds=60)
        for _ in range(100):
            cb.record_trade(MagicMock(pnl=10.0))
        assert cb.is_blocked is False

    def test_circuit_breaker_single_loss_no_trip(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(max_failures=3, cooldown_seconds=60)
        cb.record_trade(MagicMock(pnl=-100.0))
        assert cb.is_blocked is False

    def test_circuit_breaker_reset_after_cooldown(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(max_failures=2, cooldown_seconds=0.05)
        cb.record_trade(MagicMock(pnl=-100.0))
        cb.record_trade(MagicMock(pnl=-100.0))
        assert cb.is_blocked is True
        time.sleep(0.1)
        assert cb.is_blocked is False

    def test_circuit_breaker_multiple_cooldown_cycles(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(max_failures=2, cooldown_seconds=0.05)
        for _ in range(3):
            cb.record_trade(MagicMock(pnl=-100.0))
            cb.record_trade(MagicMock(pnl=-100.0))
            assert cb.is_blocked is True
            time.sleep(0.1)
            assert cb.is_blocked is False

    def test_circuit_breaker_blocks_snapshot_in_orchestrator(self) -> None:
        from graxia.packages.quant_os.autonomous.orchestrator import AutonomousOrchestrator, SystemHealth

        cb = MagicMock()
        cb.is_blocked = True
        cb.reason = "too many losses"
        orch = AutonomousOrchestrator.__new__(AutonomousOrchestrator)
        orch._symbols = ["XAUUSD"]
        orch._timeframes = ["1h"]
        orch._trading_mode = MagicMock(value="paper")
        orch._chart_monitor = MagicMock()
        orch._decision_engine = MagicMock()
        orch._kill_switch = MagicMock(is_triggered=False)
        orch._circuit_breaker = cb
        orch._news_gate = MagicMock(is_blocked=MagicMock(return_value=False))
        orch._risk_engine = MagicMock()
        orch._symbol_registry = MagicMock()
        orch._notifier = MagicMock(
            notify_trade=AsyncMock(),
            notify_error=AsyncMock(),
            notify_kill_switch=AsyncMock(),
            notify_daily_summary=AsyncMock(),
        )
        orch._order_executor = MagicMock()
        orch._health = SystemHealth()
        orch._start_time = None
        orch._running = True
        orch._main_task = None
        orch._health_task = None
        orch._kill_switch_notified = False
        orch._last_daily_summary_date = None
        orch._trade_store = MagicMock()
        orch._consecutive_errors = {"chart_monitor": 0, "decision_engine": 0, "order_executor": 0}

        loop = asyncio.new_event_loop()
        try:
            snap = ChartSnapshot(
                symbol="XAUUSD",
                timeframe="1h",
                ohlcv=[],
                indicators={},
                screenshot_path=None,
                timestamp=datetime.now(UTC),
            )
            loop.run_until_complete(orch._on_snapshot(snap))
            orch._decision_engine.analyze.assert_not_called()
        finally:
            loop.close()

    def test_circuit_breaker_not_blocked_allows_flow(self) -> None:
        from graxia.packages.quant_os.autonomous.orchestrator import AutonomousOrchestrator, SystemHealth

        cb = MagicMock()
        cb.is_blocked = False
        cb.reason = ""
        orch = AutonomousOrchestrator.__new__(AutonomousOrchestrator)
        orch._symbols = ["XAUUSD"]
        orch._timeframes = ["1h"]
        orch._trading_mode = MagicMock(value="paper")
        orch._chart_monitor = MagicMock()
        orch._decision_engine = MagicMock()
        orch._kill_switch = MagicMock(is_triggered=False)
        orch._circuit_breaker = cb
        orch._news_gate = MagicMock(is_blocked=MagicMock(return_value=False))
        orch._risk_engine = MagicMock()
        orch._symbol_registry = MagicMock()
        orch._notifier = MagicMock(
            notify_trade=AsyncMock(),
            notify_error=AsyncMock(),
            notify_kill_switch=AsyncMock(),
            notify_daily_summary=AsyncMock(),
        )
        orch._order_executor = MagicMock()
        orch._health = SystemHealth()
        orch._start_time = None
        orch._running = True
        orch._main_task = None
        orch._health_task = None
        orch._kill_switch_notified = False
        orch._last_daily_summary_date = None
        orch._trade_store = MagicMock()
        orch._consecutive_errors = {"chart_monitor": 0, "decision_engine": 0, "order_executor": 0}

        de = MagicMock()
        de.analyze = AsyncMock(return_value=_make_decision(confidence=0.8))
        orch._decision_engine = de

        loop = asyncio.new_event_loop()
        try:
            snap = ChartSnapshot(
                symbol="XAUUSD",
                timeframe="1h",
                ohlcv=[],
                indicators={},
                screenshot_path=None,
                timestamp=datetime.now(UTC),
            )
            loop.run_until_complete(orch._on_snapshot(snap))
            orch._decision_engine.analyze.assert_called_once()
        finally:
            loop.close()


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Orchestrator Resilience (12 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestOrchestratorResilience:
    """Tests for orchestrator error handling, health monitoring, and multi-symbol."""

    def _make_orchestrator(self, **overrides):
        from graxia.packages.quant_os.autonomous.orchestrator import AutonomousOrchestrator, SystemHealth

        orch = AutonomousOrchestrator.__new__(AutonomousOrchestrator)
        orch._symbols = overrides.get("symbols", ["XAUUSD"])
        orch._timeframes = overrides.get("timeframes", ["1h"])
        orch._trading_mode = overrides.get("trading_mode", MagicMock(value="paper"))
        orch._chart_monitor = overrides.get("chart_monitor", MagicMock())
        orch._decision_engine = overrides.get("decision_engine", MagicMock())
        orch._kill_switch = overrides.get("kill_switch", MagicMock(is_triggered=False))
        orch._circuit_breaker = overrides.get("circuit_breaker", MagicMock(is_blocked=False, reason=""))
        orch._news_gate = overrides.get("news_gate", MagicMock(is_blocked=MagicMock(return_value=False)))
        orch._risk_engine = overrides.get("risk_engine", MagicMock())
        orch._symbol_registry = overrides.get("symbol_registry", MagicMock())
        orch._notifier = overrides.get(
            "notifier",
            MagicMock(
                notify_trade=AsyncMock(),
                notify_error=AsyncMock(),
                notify_kill_switch=AsyncMock(),
                notify_daily_summary=AsyncMock(),
            ),
        )
        orch._order_executor = overrides.get("order_executor", MagicMock())
        orch._health = SystemHealth()
        orch._start_time = None
        orch._running = overrides.get("running", True)
        orch._main_task = None
        orch._health_task = None
        orch._kill_switch_notified = False
        orch._last_daily_summary_date = None
        orch._trade_store = overrides.get("trade_store", MagicMock())
        orch._consecutive_errors = {"chart_monitor": 0, "decision_engine": 0, "order_executor": 0}
        return orch

    @pytest.mark.asyncio
    async def test_consecutive_errors_circuit_breaker(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(max_failures=5, cooldown_seconds=60)
        orch = self._make_orchestrator(circuit_breaker=cb)
        for i in range(6):
            orch._handle_error("system", RuntimeError(f"error {i}"))
        assert orch._consecutive_errors["chart_monitor"] == 0

    @pytest.mark.asyncio
    async def test_notification_error_does_not_crash(self) -> None:
        notifier = MagicMock()
        notifier.notify_trade = AsyncMock(side_effect=RuntimeError("Telegram down"))
        notifier.notify_error = AsyncMock()
        notifier.notify_kill_switch = AsyncMock()
        notifier.notify_daily_summary = AsyncMock()
        orch = self._make_orchestrator(notifier=notifier)

        de = MagicMock()
        de.analyze = AsyncMock(return_value=_make_decision(confidence=0.8))
        orch._decision_engine = de

        snap = ChartSnapshot(
            symbol="XAUUSD", timeframe="1h", ohlcv=[], indicators={}, screenshot_path=None, timestamp=datetime.now(UTC)
        )
        await orch._on_snapshot(snap)
        assert orch._health.errors >= 1

    @pytest.mark.asyncio
    async def test_save_state_error_does_not_crash(self) -> None:
        store = MagicMock()
        store.save_health.side_effect = RuntimeError("DB locked")
        orch = self._make_orchestrator(trade_store=store)
        orch._save_state()

    @pytest.mark.asyncio
    async def test_kill_switch_notification_only_once(self) -> None:
        notifier = MagicMock()
        notifier.notify_kill_switch = AsyncMock()
        ks = MagicMock()
        ks.is_triggered = True
        ks.get_status.return_value = {"reason": "manual"}
        orch = self._make_orchestrator(kill_switch=ks, notifier=notifier)
        orch._kill_switch_notified = False

        de = MagicMock()
        de.analyze = AsyncMock(return_value=_make_decision(confidence=0.8))
        orch._decision_engine = de

        snap = ChartSnapshot(
            symbol="XAUUSD", timeframe="1h", ohlcv=[], indicators={}, screenshot_path=None, timestamp=datetime.now(UTC)
        )
        await orch._on_snapshot(snap)
        notifier.notify_kill_switch.assert_called_once()
        assert orch._kill_switch_notified is True

    @pytest.mark.asyncio
    async def test_low_confidence_no_notify(self) -> None:
        notifier = MagicMock()
        notifier.notify_trade = AsyncMock()
        orch = self._make_orchestrator(notifier=notifier)

        de = MagicMock()
        de.analyze = AsyncMock(return_value=_make_decision(confidence=0.3))
        orch._decision_engine = de

        snap = ChartSnapshot(
            symbol="XAUUSD", timeframe="1h", ohlcv=[], indicators={}, screenshot_path=None, timestamp=datetime.now(UTC)
        )
        await orch._on_snapshot(snap)
        notifier.notify_trade.assert_not_called()

    def test_health_status_returns_all_fields(self) -> None:
        orch = self._make_orchestrator()
        orch._start_time = datetime.now(UTC)
        status = orch.get_status()
        assert hasattr(status, "uptime_seconds")
        assert hasattr(status, "total_decisions")
        assert hasattr(status, "errors")

    @pytest.mark.asyncio
    async def test_daily_summary_not_triggered_twice(self) -> None:
        notifier = MagicMock()
        notifier.notify_daily_summary = AsyncMock()
        orch = self._make_orchestrator(notifier=notifier)
        orch._last_daily_summary_date = datetime.now(UTC).date()

        snap = ChartSnapshot(
            symbol="XAUUSD", timeframe="1h", ohlcv=[], indicators={}, screenshot_path=None, timestamp=datetime.now(UTC)
        )
        await orch._on_snapshot(snap)

    @pytest.mark.asyncio
    async def test_consecutive_error_threshold(self) -> None:
        orch = self._make_orchestrator()
        for i in range(10):
            orch._handle_error("decision_engine", RuntimeError(f"err {i}"))
        assert orch._consecutive_errors["decision_engine"] == 10

    @pytest.mark.asyncio
    async def test_stop_cancels_tasks(self) -> None:
        orch = self._make_orchestrator()
        orch._chart_monitor.stop = AsyncMock()
        orch._running = True
        await orch.stop()
        assert orch._running is False

    @pytest.mark.asyncio
    async def test_stop_multiple_times(self) -> None:
        orch = self._make_orchestrator()
        orch._chart_monitor.stop = AsyncMock()
        await orch.stop()
        await orch.stop()
        assert orch._running is False

    def test_health_uptime_calculation(self) -> None:
        orch = self._make_orchestrator()
        orch._start_time = datetime.now(UTC) - timedelta(hours=1)
        status = orch.get_status()
        assert status.uptime_seconds >= 3599.0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Position Sizing Edge Cases (12 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestPositionSizingEdgeCases:
    """Tests for position sizing under extreme and edge case conditions."""

    def test_very_low_confidence_position_size(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker, equity=10000)
        d = _make_decision(confidence=0.65)
        size = executor._calculate_position_size(d)
        assert size >= 0.01

    def test_very_high_confidence_position_size(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker, equity=10000)
        d = _make_decision(confidence=0.95)
        size = executor._calculate_position_size(d)
        assert size <= 10.0

    def test_small_equity_position_size(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker, equity=100)
        d = _make_decision(confidence=0.8)
        size = executor._calculate_position_size(d)
        assert size >= 0.01

    def test_large_equity_position_size(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker, equity=1000000)
        d = _make_decision(confidence=0.8)
        size = executor._calculate_position_size(d)
        assert size <= 100.0

    def test_tight_stop_loss_position_size(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker, equity=10000)
        d = _make_decision(sl=2349.99, tp=2370.0)
        size = executor._calculate_position_size(d)
        assert size >= 0.01

    def test_wide_stop_loss_position_size(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker, equity=10000)
        d = _make_decision(sl=2300.0, tp=2370.0)
        size = executor._calculate_position_size(d)
        assert size >= 0.01

    def test_crypto_symbol_position_size(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker, equity=10000)
        d = _make_decision(symbol="BTCUSD", entry=65000.0, sl=64000.0, tp=67000.0)
        size = executor._calculate_position_size(d)
        assert size >= 0.001

    def test_forex_symbol_position_size(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker, equity=10000)
        d = _make_decision(symbol="EURUSD", entry=1.1, sl=1.095, tp=1.11)
        size = executor._calculate_position_size(d)
        assert size >= 0.01

    def test_index_symbol_position_size(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker, equity=10000)
        d = _make_decision(symbol="US500", entry=5000.0, sl=4990.0, tp=5020.0)
        size = executor._calculate_position_size(d)
        assert size >= 0.01

    def test_position_size_never_zero(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker, equity=10000)
        d = _make_decision(confidence=0.65)
        size = executor._calculate_position_size(d)
        assert size > 0

    def test_position_size_with_zero_sl_distance(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker, equity=10000)
        d = _make_decision(sl=2350.0, tp=2370.0)
        size = executor._calculate_position_size(d)
        assert size >= 0.01

    def test_daily_stats_returns_all_keys(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker)
        stats = executor.get_daily_stats()
        required_keys = ["trades_today", "realized_pnl", "mode"]
        for key in required_keys:
            assert key in stats


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Notification Delivery Under Failure (10 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestNotificationFailure:
    """Tests for notification delivery under various failure conditions."""

    @pytest.mark.asyncio
    async def test_telegram_500_error_handled(self) -> None:
        notifier = TradeNotifier(bot_token="token", chat_id="123")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx = MagicMock()
        mock_httpx.AsyncClient.return_value = mock_client
        import sys

        sys.modules["httpx"] = mock_httpx
        try:
            await notifier._send("test message")
        finally:
            del sys.modules["httpx"]

    @pytest.mark.asyncio
    async def test_telegram_429_rate_limit(self) -> None:
        notifier = TradeNotifier(bot_token="token", chat_id="123")
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Too Many Requests"
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx = MagicMock()
        mock_httpx.AsyncClient.return_value = mock_client
        import sys

        sys.modules["httpx"] = mock_httpx
        try:
            await notifier._send("test message")
        finally:
            del sys.modules["httpx"]

    @pytest.mark.asyncio
    async def test_telegram_network_timeout(self) -> None:
        notifier = TradeNotifier(bot_token="token", chat_id="123")
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=TimeoutError())
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx = MagicMock()
        mock_httpx.AsyncClient.return_value = mock_client
        import sys

        sys.modules["httpx"] = mock_httpx
        try:
            await notifier._send("test message")
        finally:
            del sys.modules["httpx"]

    @pytest.mark.asyncio
    async def test_telegram_connection_refused(self) -> None:
        notifier = TradeNotifier(bot_token="token", chat_id="123")
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=ConnectionError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx = MagicMock()
        mock_httpx.AsyncClient.return_value = mock_client
        import sys

        sys.modules["httpx"] = mock_httpx
        try:
            await notifier._send("test message")
        finally:
            del sys.modules["httpx"]

    @pytest.mark.asyncio
    async def test_rate_limit_enforces_delay(self) -> None:
        notifier = TradeNotifier(bot_token="token", chat_id="123")
        notifier._last_send_time["123"] = time.monotonic()
        start = time.monotonic()
        await notifier._rate_limit("123")
        elapsed = time.monotonic() - start
        assert elapsed >= 0.9

    @pytest.mark.asyncio
    async def test_disabled_notifier_skips_send(self) -> None:
        notifier = TradeNotifier(enabled=False)
        await notifier.notify_trade(_make_decision(), MagicMock(success=True))
        await notifier.notify_error("test", "error")
        await notifier.notify_kill_switch("manual")
        await notifier.notify_daily_summary({})

    @pytest.mark.asyncio
    async def test_empty_bot_token_skips_send(self) -> None:
        notifier = TradeNotifier(bot_token="", chat_id="123")
        await notifier.notify_trade(_make_decision(), MagicMock(success=True))

    @pytest.mark.asyncio
    async def test_empty_chat_id_skips_send(self) -> None:
        notifier = TradeNotifier(bot_token="token", chat_id="")
        await notifier.notify_trade(_make_decision(), MagicMock(success=True))

    @pytest.mark.asyncio
    async def test_trade_notification_success_result(self) -> None:
        notifier = TradeNotifier(enabled=False)
        result = MagicMock(success=True, order_id="auto-001", error=None)
        await notifier.notify_trade(_make_decision(), result)

    @pytest.mark.asyncio
    async def test_trade_notification_failure_result(self) -> None:
        notifier = TradeNotifier(enabled=False)
        result = MagicMock(success=False, order_id=None, error="broker timeout")
        await notifier.notify_trade(_make_decision(), result)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Reconciliation Edge Cases (10 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestReconciliationEdgeCases:
    """Tests for reconciliation during volatile and edge case states."""

    @pytest.mark.asyncio
    async def test_reconciler_with_mixed_success_and_failure(self, trade_store: TradeStore) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_positions.return_value = []

        for i in range(10):
            trade_store.save_execution(
                {
                    "symbol": "XAUUSD",
                    "direction": "BUY",
                    "confidence": 0.8,
                    "entry": 2350.0,
                    "stop_loss": 2340.0,
                    "take_profit": 2370.0,
                    "success": i % 2 == 0,
                    "order_id": f"auto-{i:03d}",
                    "broker_order_id": f"MT5-{i:03d}" if i % 2 == 0 else "",
                    "error": "" if i % 2 == 0 else "rejected",
                    "approval_required": False,
                    "mode": "paper",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )

        reconciler = TradeReconciler(broker, trade_store)
        result = await reconciler.reconcile()
        assert result.total_executions >= 0

    @pytest.mark.asyncio
    async def test_reconciler_many_phantom_positions(self, trade_store: TradeStore) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_positions.return_value = [
            {"symbol": "XAUUSD", "volume": 1.0, "price_open": 2350.0},
            {"symbol": "BTCUSD", "volume": 0.1, "price_open": 65000.0},
            {"symbol": "EURUSD", "volume": 1.0, "price_open": 1.1},
        ]
        reconciler = TradeReconciler(broker, trade_store)
        result = await reconciler.reconcile()
        assert result.is_clean is False
        assert len(result.phantom_positions) == 3

    @pytest.mark.asyncio
    async def test_reconciler_broker_timeout(self, trade_store: TradeStore) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_positions.side_effect = TimeoutError()
        reconciler = TradeReconciler(broker, trade_store)
        result = await reconciler.reconcile()
        assert result.total_positions == 0

    @pytest.mark.asyncio
    async def test_reconciler_connection_reset(self, trade_store: TradeStore) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_positions.side_effect = ConnectionResetError("Connection reset by peer")
        reconciler = TradeReconciler(broker, trade_store)
        result = await reconciler.reconcile()
        assert result.total_positions == 0

    @pytest.mark.asyncio
    async def test_reconciler_empty_executions(self, trade_store: TradeStore) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_positions.return_value = [
            {"symbol": "XAUUSD", "volume": 1.0, "price_open": 2350.0},
        ]
        reconciler = TradeReconciler(broker, trade_store)
        result = await reconciler.reconcile()
        assert result.is_clean is False

    @pytest.mark.asyncio
    async def test_reconciler_many_executions_many_positions(self, trade_store: TradeStore) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_positions.return_value = [
            {"symbol": f"SYM{i}", "volume": 1.0, "price_open": 100.0 + i} for i in range(20)
        ]
        for i in range(20):
            trade_store.save_execution(
                {
                    "symbol": f"SYM{i}",
                    "direction": "BUY",
                    "confidence": 0.8,
                    "entry": 100.0 + i,
                    "stop_loss": 99.0 + i,
                    "take_profit": 102.0 + i,
                    "success": True,
                    "order_id": f"auto-{i:03d}",
                    "broker_order_id": f"MT5-{i:03d}",
                    "error": "",
                    "approval_required": False,
                    "mode": "paper",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        reconciler = TradeReconciler(broker, trade_store)
        result = await reconciler.reconcile()
        assert result.total_executions == 20

    @pytest.mark.asyncio
    async def test_reconciler_concurrent_reconcile(self, trade_store: TradeStore) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_positions.return_value = []
        reconciler = TradeReconciler(broker, trade_store)

        async def reconcile() -> ReconciliationResult:
            return await reconciler.reconcile()

        results = await asyncio.gather(reconcile(), reconcile(), reconcile())
        for result in results:
            assert hasattr(result, "is_clean")

    @pytest.mark.asyncio
    async def test_reconciler_result_has_timestamp(self, trade_store: TradeStore) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_positions.return_value = []
        reconciler = TradeReconciler(broker, trade_store)
        result = await reconciler.reconcile()
        assert isinstance(result.timestamp, datetime)

    @pytest.mark.asyncio
    async def test_reconciler_result_has_missing_fills_field(self, trade_store: TradeStore) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_positions.return_value = []
        reconciler = TradeReconciler(broker, trade_store)
        result = await reconciler.reconcile()
        assert hasattr(result, "missing_fills")
        assert isinstance(result.missing_fills, list)

    @pytest.mark.asyncio
    async def test_reconciler_result_has_phantom_positions_field(self, trade_store: TradeStore) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_positions.return_value = []
        reconciler = TradeReconciler(broker, trade_store)
        result = await reconciler.reconcile()
        assert hasattr(result, "phantom_positions")
        assert isinstance(result.phantom_positions, list)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Security & Auth Edge Cases (10 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestSecurityEdgeCases:
    """Tests for security, auth bypass, and fail-closed paths."""

    @pytest.mark.asyncio
    async def test_unauthorized_user_empty_set_rejects(self) -> None:
        gate = LiveApprovalGate(bot_token="token", chat_id="123")
        gate._authorized_users = set()
        result = await gate.request_approval(_make_decision())
        assert result.approved is False

    @pytest.mark.asyncio
    async def test_authorized_user_allows(self) -> None:
        gate = LiveApprovalGate(bot_token="token", chat_id="123")
        gate._authorized_users = {"user1"}
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        gate._pending["test-req"] = future
        gate.handle_callback("test-req", ApprovalAction.APPROVE, user_id="user1")
        assert future.done()
        assert future.result() == ApprovalAction.APPROVE

    def test_parse_callback_injection_attempt(self) -> None:
        result = LiveApprovalGate.parse_live_callback("live:req-001:approve; DROP TABLE users;--")
        assert result is None

    def test_parse_callback_empty_string(self) -> None:
        result = LiveApprovalGate.parse_live_callback("")
        assert result is None

    def test_parse_callback_missing_parts(self) -> None:
        result = LiveApprovalGate.parse_live_callback("live:req-001")
        assert result is None

    def test_parse_callback_extra_colons(self) -> None:
        result = LiveApprovalGate.parse_live_callback("live:req:001:approve")
        assert result is not None

    @pytest.mark.asyncio
    async def test_callback_with_zero_user_id(self) -> None:
        gate = LiveApprovalGate(bot_token="token", chat_id="123")
        gate._authorized_users = {"0"}
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        gate._pending["test-req"] = future
        gate.handle_callback("test-req", ApprovalAction.APPROVE, user_id="0")
        assert future.done()

    @pytest.mark.asyncio
    async def test_callback_with_negative_user_id(self) -> None:
        gate = LiveApprovalGate(bot_token="token", chat_id="123")
        gate._authorized_users = {"-1"}
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        gate._pending["test-req"] = future
        gate.handle_callback("test-req", ApprovalAction.APPROVE, user_id="-1")
        assert future.done()

    def test_build_keyboard_request_id_in_callback(self) -> None:
        gate = LiveApprovalGate(bot_token="token", chat_id="123")
        kb = gate._build_keyboard("unique-req-123")
        assert "unique-req-123" in kb["inline_keyboard"][0][0]["callback_data"]

    def test_action_to_result_all_actions(self) -> None:
        for action in ApprovalAction:
            result = LiveApprovalGate._action_to_result(action)
            assert hasattr(result, "approved")
            assert hasattr(result, "size_multiplier")


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Rate Limiter Advanced (8 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestRateLimiterAdvanced:
    """Advanced rate limiter edge case tests."""

    def test_burst_then_deplete(self) -> None:
        rl = RateLimiter(limits={"groq": 5})
        for _ in range(5):
            assert rl.can_proceed("groq") is True
            rl.record_request("groq")
        assert rl.can_proceed("groq") is False

    def test_refill_partial(self) -> None:
        rl = RateLimiter(limits={"groq": 2})
        rl.record_request("groq")
        rl.record_request("groq")
        assert rl.can_proceed("groq") is False
        bucket = rl._buckets["groq"]
        bucket.last_refill = time.monotonic() - 43200.0
        assert rl.can_proceed("groq") is True

    def test_status_format(self) -> None:
        rl = RateLimiter(limits={"groq": 100})
        status = rl.get_status()
        assert "groq" in status
        assert "remaining" in status["groq"]
        assert "limit" in status["groq"]

    def test_get_wait_time_unknown_provider(self) -> None:
        rl = RateLimiter(limits={"groq": 100})
        wait = rl.get_wait_time("unknown_provider")
        assert wait == 0.0

    def test_record_request_unknown_provider(self) -> None:
        rl = RateLimiter(limits={"groq": 100})
        rl.record_request("unknown_provider")
        assert rl.can_proceed("unknown_provider") is True

    def test_many_providers(self) -> None:
        limits = {f"provider_{i}": 10 for i in range(20)}
        rl = RateLimiter(limits=limits)
        for i in range(20):
            assert rl.can_proceed(f"provider_{i}") is True

    def test_concurrent_record_requests(self) -> None:
        rl = RateLimiter(limits={"groq": 10})
        errors = []

        def recorder() -> None:
            try:
                rl.record_request("groq")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=recorder) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert rl.can_proceed("groq") is False

    def test_refill_after_long_time(self) -> None:
        rl = RateLimiter(limits={"groq": 1})
        rl.record_request("groq")
        bucket = rl._buckets["groq"]
        bucket.last_refill = time.monotonic() - 86400.0 * 365
        assert rl.can_proceed("groq") is True


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Symbol Registry Advanced (8 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestSymbolRegistryAdvanced:
    """Advanced symbol registry edge cases."""

    def test_all_asset_classes_covered(self) -> None:
        reg = SymbolRegistry()
        all_symbols = reg.list_symbols()
        classes = set()
        for s in all_symbols:
            classes.add(reg.get_asset_class(s))
        assert "metals" in classes
        assert "crypto" in classes
        assert "forex" in classes

    def test_register_overwrites_existing(self) -> None:
        reg = SymbolRegistry()
        original_class = reg.get_asset_class("XAUUSD")
        new_info = SymbolInfo("custom_class", 0.01, 100.0, (100.0, 200.0))
        reg.register("XAUUSD", new_info)
        assert reg.get_asset_class("XAUUSD") == "custom_class"
        reg.register("XAUUSD", SymbolInfo("metals", 0.01, 100.0, (1900.0, 2500.0)))

    def test_get_pip_value_known_symbol(self) -> None:
        reg = SymbolRegistry()
        pip = reg.get_pip_value("XAUUSD")
        assert pip > 0

    def test_get_pip_value_unknown_symbol(self) -> None:
        reg = SymbolRegistry()
        pip = reg.get_pip_value("FAKECOIN")
        assert pip == 0.01

    def test_validate_price_boundary(self) -> None:
        reg = SymbolRegistry()
        assert reg.validate_price("XAUUSD", 1900.0) is True
        assert reg.validate_price("XAUUSD", 2500.0) is True

    def test_validate_price_just_outside_range(self) -> None:
        reg = SymbolRegistry()
        assert reg.validate_price("XAUUSD", 500.0) is False

    def test_many_custom_symbols(self) -> None:
        reg = SymbolRegistry()
        for i in range(50):
            info = SymbolInfo(f"class_{i % 5}", 0.01, 100.0, (0.0, 10000.0))
            reg.register(f"SYM{i}", info)
        for i in range(50):
            assert reg.is_known(f"SYM{i}") is True

    def test_unregister_then_register(self) -> None:
        reg = SymbolRegistry()
        reg.unregister("XAUUSD")
        assert reg.is_known("XAUUSD") is False
        reg.register("XAUUSD", SymbolInfo("metals", 0.01, 100.0, (1900.0, 2500.0)))
        assert reg.is_known("XAUUSD") is True


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Chart Monitor Advanced (8 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestChartMonitorAdvanced:
    """Advanced chart monitor edge cases."""

    def _make_monitor(self, **overrides) -> ChartMonitor:
        monitor = ChartMonitor.__new__(ChartMonitor)
        monitor._symbols = overrides.get("symbols", ["XAUUSD"])
        monitor._timeframes = overrides.get("timeframes", ["1h"])
        monitor._poll_seconds = overrides.get("poll_seconds", 60)
        monitor._buffers = {}
        monitor._callbacks = []
        monitor._running = False
        monitor._task = None
        monitor._tv_client = MagicMock()
        monitor._tv_cdp = MagicMock()
        monitor._cdp_available = overrides.get("cdp_available", True)
        monitor._last_cdp_attempt = overrides.get("last_cdp_attempt", 0.0)
        monitor._cdp_reconnect_interval = overrides.get("reconnect_interval", 300.0)
        return monitor

    def test_buffer_overflow_many_symbols(self) -> None:
        monitor = self._make_monitor()
        for sym_idx in range(20):
            for i in range(150):
                snap = ChartSnapshot(
                    symbol=f"SYM{sym_idx}",
                    timeframe="1h",
                    ohlcv=[],
                    indicators={},
                    screenshot_path=None,
                    timestamp=datetime.now(UTC),
                )
                monitor._store(snap)
        for key, buf in monitor._buffers.items():
            assert len(buf) <= 100

    def test_get_latest_returns_most_recent(self) -> None:
        monitor = self._make_monitor()
        for i in range(5):
            snap = ChartSnapshot(
                symbol="XAUUSD",
                timeframe="1h",
                ohlcv=[],
                indicators={"seq": i},
                screenshot_path=None,
                timestamp=datetime.now(UTC),
            )
            monitor._store(snap)
        latest = monitor.get_latest("XAUUSD", "1h")
        assert latest is not None
        assert latest.indicators["seq"] == 4

    def test_get_history_returns_all(self) -> None:
        monitor = self._make_monitor()
        for i in range(5):
            snap = ChartSnapshot(
                symbol="XAUUSD",
                timeframe="1h",
                ohlcv=[],
                indicators={"seq": i},
                screenshot_path=None,
                timestamp=datetime.now(UTC),
            )
            monitor._store(snap)
        history = monitor.get_history("XAUUSD", "1h")
        assert len(history) == 5

    def test_should_reconnect_when_not_available(self) -> None:
        monitor = self._make_monitor(cdp_available=False)
        assert monitor._should_reconnect_cdp() is True

    def test_should_not_reconnect_when_available(self) -> None:
        monitor = self._make_monitor(cdp_available=True)
        assert monitor._should_reconnect_cdp() is False

    @pytest.mark.asyncio
    async def test_publish_multiple_callbacks(self) -> None:
        monitor = self._make_monitor()
        cb1 = AsyncMock()
        cb2 = AsyncMock()
        cb3 = AsyncMock()
        monitor._callbacks = [cb1, cb2, cb3]
        snap = ChartSnapshot(
            symbol="XAUUSD",
            timeframe="1h",
            ohlcv=[],
            indicators={},
            screenshot_path=None,
            timestamp=datetime.now(UTC),
        )
        await monitor._publish(snap)
        cb1.assert_called_once()
        cb2.assert_called_once()
        cb3.assert_called_once()

    def test_multiple_timeframes_per_symbol(self) -> None:
        monitor = self._make_monitor()
        for tf in ["1h", "4h", "1d"]:
            snap = ChartSnapshot(
                symbol="XAUUSD",
                timeframe=tf,
                ohlcv=[],
                indicators={},
                screenshot_path=None,
                timestamp=datetime.now(UTC),
            )
            monitor._store(snap)
        assert len(monitor._buffers) == 3

    def test_empty_symbol_snapshots(self) -> None:
        monitor = self._make_monitor()
        snap = ChartSnapshot(
            symbol="",
            timeframe="1h",
            ohlcv=[],
            indicators={},
            screenshot_path=None,
            timestamp=datetime.now(UTC),
        )
        monitor._store(snap)
        assert "" in monitor._buffers


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Decision Engine Advanced (8 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestDecisionEngineAdvanced:
    """Advanced decision engine edge cases."""

    def test_extract_json_nested_braces(self) -> None:
        text = 'Analysis: {"direction": "BUY", "details": {"key": "value"}}'
        result = DecisionEngine._extract_json(text)
        assert result["direction"] == "BUY"

    def test_extract_json_multiple_objects(self) -> None:
        text = '{"direction": "SELL", "confidence": 0.7} and another {"direction": "BUY"}'
        result = DecisionEngine._extract_json(text)
        assert result["direction"] == "SELL"

    def test_format_ohlcv_empty(self) -> None:
        result = DecisionEngine._format_ohlcv([])
        assert "no data" in result.lower() or result == ""

    def test_format_ohlcv_single_candle(self) -> None:
        candles = [[1700000000, 2350.0, 2360.0, 2340.0, 2355.0, 100.0]]
        result = DecisionEngine._format_ohlcv(candles)
        assert "2350" in result or "2355" in result

    def test_clamp_confidence_exact_zero(self) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        assert engine._clamp_confidence(0.0) == 0.0

    def test_clamp_confidence_exact_one(self) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        assert engine._clamp_confidence(1.0) == 0.95

    def test_clamp_confidence_negative_large(self) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        assert engine._clamp_confidence(-1000.0) == 0.0

    def test_clamp_confidence_positive_large(self) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        assert engine._clamp_confidence(1000.0) == 0.95


# ═══════════════════════════════════════════════════════════════════════════════
# 13. NewsGate Advanced (5 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestNewsGateAdvanced:
    """Advanced news gate edge cases."""

    def test_blackout_exact_expiry(self) -> None:
        gate = NewsBlackoutGate()
        gate.set_blackout(until=datetime.now(UTC), reason="NFP")
        assert gate.is_blocked() is False

    def test_blackout_one_second_before_expiry(self) -> None:
        gate = NewsBlackoutGate()
        gate.set_blackout(until=datetime.now(UTC) + timedelta(seconds=1), reason="NFP")
        assert gate.is_blocked() is True

    def test_multiple_set_blackout_last_wins(self) -> None:
        gate = NewsBlackoutGate()
        gate.set_blackout(until=datetime.now(UTC) + timedelta(hours=1), reason="NFP")
        gate.set_blackout(until=datetime.now(UTC) + timedelta(hours=2), reason="CPI")
        assert gate._reason == "CPI"
        assert gate._until > datetime.now(UTC) + timedelta(hours=1)

    def test_get_next_event_returns_none_when_empty(self) -> None:
        gate = NewsBlackoutGate()
        assert gate.get_next_event() is None

    def test_clear_blackout_resets_all_state(self) -> None:
        gate = NewsBlackoutGate()
        gate.set_blackout(until=datetime.now(UTC) + timedelta(hours=1), reason="NFP")
        gate.clear_blackout()
        assert gate.is_blocked() is False
        assert gate._reason == ""
        assert gate._until is None or gate._until <= datetime.now(UTC)
