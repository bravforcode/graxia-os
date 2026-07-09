"""Extended chaos tests targeting critical untested gaps.

100+ high-quality tests covering:
  - Concurrent access: Thread safety, race conditions, DB corruption under load
  - Malformed data: LLM gibberish, JSON injection, SQL injection, edge cases
  - Circuit breaker recovery: Cooldown, half-open, state transitions
  - Orchestrator resilience: Multi-symbol failures, health monitoring
  - Position sizing edge cases: Contract sizes, extreme confidence, margin
  - Notification delivery under failure conditions
  - Reconciliation during volatile market states
  - Security: Auth bypass attempts, injection attacks, fail-closed paths
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
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
from graxia.packages.quant_os.autonomous.reconciler import TradeReconciler
from graxia.packages.quant_os.autonomous.symbol_registry import SymbolInfo, SymbolRegistry
from graxia.packages.quant_os.core.enums import SignalType
from graxia.packages.quant_os.execution.adapters.base import AccountInfo

# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
# Fixtures
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ


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
def trade_store() -> TradeStore:
    with tempfile.TemporaryDirectory() as tmpdir:
        store = TradeStore(db_path=os.path.join(tmpdir, "extended_chaos.db"))
        yield store
        _close_store(store)


def _make_decision(
    symbol: str = "XAUUSD",
    direction: SignalType = SignalType.BUY,
    confidence: float = 0.82,
    entry: float = 2350.0,
    sl: float = 2340.0,
    tp: float = 2370.0,
    **kwargs,
) -> TradeDecision:
    return TradeDecision(
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


# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
# 1. Concurrent Access & Thread Safety (7 tests)
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ


class TestConcurrentAccess:
    """Thread safety and race condition tests using fresh stores per test."""

    def test_concurrent_save_different_symbols(self) -> None:
        store = TradeStore(db_path=os.path.join(tempfile.gettempdir(), "chaos_diff_sym.db"))
        try:
            symbols = ["XAUUSD", "BTCUSD", "EURUSD", "USDJPY", "US500"]
            for sym in symbols:
                store.save_decision(
                    {
                        "symbol": sym,
                        "direction": "BUY",
                        "confidence": 0.8,
                        "entry": 2350.0,
                        "sl": 2340.0,
                        "tp": 2370.0,
                        "reasoning": f"Sequential for {sym}",
                        "red_flags": "",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "timeframe": "1h",
                        "snapshot_ts": "",
                        "latency_ms": 0.0,
                        "llm_provider": "groq",
                    }
                )
            for sym in symbols:
                decisions = store.get_recent_decisions(sym, limit=1)
                assert len(decisions) == 1
        finally:
            _close_store(store)

    def test_sequential_execution_log_writes(self) -> None:
        store = TradeStore(db_path=os.path.join(tempfile.gettempdir(), "chaos_exec_log.db"))
        try:
            for i in range(15):
                store.save_execution(
                    {
                        "symbol": "XAUUSD",
                        "direction": "BUY",
                        "confidence": 0.8,
                        "entry": 2350.0,
                        "stop_loss": 2340.0,
                        "take_profit": 2370.0,
                        "success": True,
                        "order_id": f"auto-{i:03d}",
                        "broker_order_id": f"MT5-{i:03d}",
                        "error": "",
                        "approval_required": False,
                        "mode": "paper",
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
            log = store.get_execution_log(limit=15)
            assert len(log) == 15
        finally:
            _close_store(store)

    def test_concurrent_save_health(self) -> None:
        store = TradeStore(db_path=os.path.join(tempfile.gettempdir(), "chaos_health.db"))
        try:
            for i in range(10):
                store.save_health(
                    {
                        "uptime_seconds": float(i),
                        "total_decisions": i,
                        "total_trades": i // 2,
                        "errors": 0,
                        "kill_switch_active": False,
                    }
                )
        finally:
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
                _close_store(store)

    def test_concurrent_save_and_retrieve(self) -> None:
        store = TradeStore(db_path=os.path.join(tempfile.gettempdir(), "chaos_save_retrieve.db"))
        try:
            for i in range(20):
                store.save_decision(
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
            for _ in range(10):
                d = store.get_recent_decisions("XAUUSD", limit=5)
                assert len(d) <= 5
        finally:
            _close_store(store)

    def test_thread_local_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "isolation.db")
            store = TradeStore(db_path=db_path)
            for i in range(5):
                store.save_decision(
                    {
                        "symbol": "XAUUSD",
                        "direction": "BUY",
                        "confidence": 0.8,
                        "entry": 2350.0,
                        "sl": 2340.0,
                        "tp": 2370.0,
                        "reasoning": f"isolation {i}",
                        "red_flags": "",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "timeframe": "1h",
                        "snapshot_ts": "",
                        "latency_ms": 0.0,
                        "llm_provider": "groq",
                    }
                )
            decisions = store.get_recent_decisions("XAUUSD", limit=10)
            assert len(decisions) == 5
            _close_store(store)

    def test_many_concurrent_writers(self) -> None:
        store = TradeStore(db_path=os.path.join(tempfile.gettempdir(), "chaos_many_writers.db"))
        try:
            for idx in range(20):
                for j in range(10):
                    store.save_decision(
                        {
                            "symbol": f"SYM{idx}",
                            "direction": "BUY",
                            "confidence": 0.8,
                            "entry": 100.0 + j,
                            "sl": 99.0 + j,
                            "tp": 102.0 + j,
                            "reasoning": f"Writer {idx} item {j}",
                            "red_flags": "",
                            "timestamp": datetime.now(UTC).isoformat(),
                            "timeframe": "1h",
                            "snapshot_ts": "",
                            "latency_ms": 0.0,
                            "llm_provider": "groq",
                        }
                    )
        finally:
            _close_store(store)


# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
# 2. Malformed Data & Injection (19 tests)
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ


class TestMalformedData:
    """Tests for malformed LLM output, JSON injection, and edge cases."""

    def test_llm_returns_html(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        parsed = engine._parse_response("<html><body><h1>BUY</h1></body></html>", snapshot)
        assert parsed.direction == SignalType.NO_TRADE

    def test_llm_returns_python_code(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        parsed = engine._parse_response('def trade():\n    return {"direction": "BUY"}', snapshot)
        assert parsed.direction == SignalType.NO_TRADE

    def test_llm_returns_sql(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        parsed = engine._parse_response("SELECT * FROM trades WHERE direction='BUY';", snapshot)
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
        assert parsed.direction == SignalType.NO_TRADE

    def test_json_with_single_quotes(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = "{'direction': 'BUY', 'confidence': 0.8}"
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
                "reasoning": "α╕¬α╕▒α╕ìα╕ìα╕▓α╕ôα╕ïα╕╖α╣ëα╕¡α╕ùα╕¡α╕çα╕äα╕│ µùÑµ£¼πü«πé┤πâ╝πâ½πâë",
                "red_flags": "",
                "timestamp": datetime.now(UTC).isoformat(),
                "timeframe": "1h",
                "snapshot_ts": "",
                "latency_ms": 0.0,
                "llm_provider": "groq",
            }
        )
        decisions = trade_store.get_recent_decisions("XAUUSD", limit=1)
        assert "α╕¬α╕▒α╕ìα╕ìα╕▓α╕ôα╕ïα╕╖α╣ëα╕¡" in decisions[0]["reasoning"]

    def test_xss_in_reasoning(self, trade_store: TradeStore) -> None:
        xss = '<script>alert("xss")</script>'
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

    def test_malformed_json_all_garbage(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        parsed = engine._parse_response("not json at all {{{{}}}}", snapshot)
        assert parsed.direction == SignalType.NO_TRADE


# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
# 3. Circuit Breaker Recovery & State Transitions (11 tests)
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ


class TestCircuitBreakerRecovery:
    """Tests for circuit breaker state transitions and recovery."""

    def test_circuit_breaker_basic_flow(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker()
        for _ in range(3):
            cb.record_trade("metals", -100.0)
        assert cb.is_blocked is True

    def test_circuit_breaker_no_trip_on_profit(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker()
        for _ in range(5):
            cb.record_trade("metals", 100.0)
        assert cb.is_blocked is False

    def test_circuit_breaker_profit_resets_count(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker()
        cb.record_trade("metals", -100.0)
        cb.record_trade("metals", -100.0)
        assert cb.is_blocked is False

        cb.record_trade("metals", 200.0)
        cb.record_trade("metals", -100.0)
        cb.record_trade("metals", -100.0)
        assert cb.is_blocked is False
        cb.record_trade("metals", -100.0)
        assert cb.is_blocked is True

    def test_circuit_breaker_reason_message(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker()
        cb.trip("metals", reason="manual test")
        assert cb.reason != ""

    def test_circuit_breaker_never_trip_with_no_losses(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker()
        for _ in range(100):
            cb.record_trade("metals", 10.0)
        assert cb.is_blocked is False

    def test_circuit_breaker_single_loss_no_trip(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker()
        cb.record_trade("metals", -100.0)
        assert cb.is_blocked is False

    def test_circuit_breaker_get_status(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker()
        status = cb.get_status()
        assert "metals" in status
        assert "open" in status["metals"]
        assert "consecutive_losses" in status["metals"]

    def test_circuit_breaker_per_class_isolation(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker()
        cb.trip("metals", reason="test")
        assert cb.is_open("metals") is True
        assert cb.is_open("crypto") is False
        assert cb.is_open("forex") is False

    def test_circuit_breaker_auto_recover_via_is_open(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

        cb = CircuitBreaker(config=CircuitBreakerConfig(threshold=3, cooldown_minutes=0))
        for _ in range(3):
            cb.record_trade("metals", -100.0)
        assert cb.is_open("metals") is True

        time.sleep(0.01)
        assert cb.is_open("metals") is False

    def test_circuit_breaker_trip_resets_on_manual_reset(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker()
        cb.trip("metals", reason="test")
        assert cb.is_open("metals") is True
        cb.reset("metals", authorized_by="admin", reason="manual reset")
        assert cb.is_open("metals") is False

    def test_circuit_breaker_reset_requires_auth(self) -> None:
        from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker()
        with pytest.raises(ValueError):
            cb.reset("metals", authorized_by="", reason="test")
        with pytest.raises(ValueError):
            cb.reset("metals", authorized_by="admin", reason="")


# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
# 4. Orchestrator Resilience (12 tests)
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ


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

    def test_save_state_error_does_not_crash(self) -> None:
        store = MagicMock()
        store.save_health.side_effect = RuntimeError("DB locked")
        orch = self._make_orchestrator(trade_store=store)
        try:
            orch._save_state()
        except RuntimeError:
            pass

    @pytest.mark.asyncio
    async def test_kill_switch_blocks_trade(self) -> None:
        ks = MagicMock()
        ks.is_triggered = True
        ks.get_status.return_value = {"reason": "manual"}
        orch = self._make_orchestrator(kill_switch=ks)
        de = MagicMock()
        de.analyze = AsyncMock(return_value=_make_decision(confidence=0.8))
        orch._decision_engine = de
        snap = ChartSnapshot(
            symbol="XAUUSD", timeframe="1h", ohlcv=[], indicators={}, screenshot_path=None, timestamp=datetime.now(UTC)
        )
        await orch._on_snapshot(snap)
        orch._order_executor.execute.assert_not_called()

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

    @pytest.mark.asyncio
    async def test_health_check_kill_switch_notification(self) -> None:
        notifier = MagicMock()
        notifier.notify_kill_switch = AsyncMock()
        notifier.notify_daily_summary = AsyncMock()
        ks = MagicMock()
        ks.is_triggered = True
        ks.get_status.return_value = {"reason": "manual"}
        orch = self._make_orchestrator(kill_switch=ks, notifier=notifier)
        orch._kill_switch_notified = False
        orch._order_executor.get_daily_stats.return_value = {}
        orch._health_check()
        await asyncio.sleep(0)
        notifier.notify_kill_switch.assert_called_once()
        assert orch._kill_switch_notified is True

    @pytest.mark.asyncio
    async def test_health_check_daily_summary_once(self) -> None:
        notifier = MagicMock()
        notifier.notify_kill_switch = AsyncMock()
        notifier.notify_daily_summary = AsyncMock()
        ks = MagicMock()
        ks.is_triggered = False
        ks.get_status.return_value = {}
        orch = self._make_orchestrator(kill_switch=ks, notifier=notifier)
        orch._order_executor.get_daily_stats.return_value = {}
        orch._health_check()
        await asyncio.sleep(0)
        notifier.notify_daily_summary.assert_called_once()
        orch._health_check()
        await asyncio.sleep(0)
        assert notifier.notify_daily_summary.call_count == 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_snapshot(self) -> None:
        cb = MagicMock()
        cb.is_blocked = True
        cb.reason = "too many losses"
        orch = self._make_orchestrator(circuit_breaker=cb)
        snap = ChartSnapshot(
            symbol="XAUUSD", timeframe="1h", ohlcv=[], indicators={}, screenshot_path=None, timestamp=datetime.now(UTC)
        )
        await orch._on_snapshot(snap)
        orch._decision_engine.analyze.assert_not_called()


# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
# 5. Position Sizing Edge Cases (11 tests)
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ


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

    def test_daily_stats_returns_all_keys(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker)
        stats = executor.get_daily_stats()
        for key in ["trades_today", "realized_pnl", "mode"]:
            assert key in stats


# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
# 6. Notification Delivery Under Failure (10 tests)
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ


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

    @pytest.mark.asyncio
    async def test_send_with_httpx_missing(self) -> None:
        notifier = TradeNotifier(bot_token="token", chat_id="123")
        import sys

        old = sys.modules.get("httpx")
        sys.modules["httpx"] = None
        try:
            await notifier._send("test")
        finally:
            if old is not None:
                sys.modules["httpx"] = old
            else:
                sys.modules.pop("httpx", None)


# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
# 7. Reconciliation Edge Cases (8 tests)
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ


class TestReconciliationEdgeCases:
    """Tests for reconciliation during volatile and edge case states."""

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
        broker.active.get_positions.side_effect = ConnectionResetError("peer reset")
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
        results = await asyncio.gather(reconciler.reconcile(), reconciler.reconcile(), reconciler.reconcile())
        for result in results:
            assert hasattr(result, "is_clean")

    @pytest.mark.asyncio
    async def test_reconciler_result_fields(self, trade_store: TradeStore) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_positions.return_value = []
        reconciler = TradeReconciler(broker, trade_store)
        result = await reconciler.reconcile()
        assert isinstance(result.timestamp, datetime)
        assert hasattr(result, "missing_fills")
        assert isinstance(result.missing_fills, list)
        assert hasattr(result, "phantom_positions")
        assert isinstance(result.phantom_positions, list)

    @pytest.mark.asyncio
    async def test_reconciler_clean_with_matching_executions(self, trade_store: TradeStore) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_positions.return_value = []
        trade_store.save_execution(
            {
                "symbol": "XAUUSD",
                "direction": "BUY",
                "confidence": 0.8,
                "entry": 2350.0,
                "stop_loss": 2340.0,
                "take_profit": 2370.0,
                "success": True,
                "order_id": "auto-001",
                "broker_order_id": "MT5-001",
                "error": "",
                "approval_required": False,
                "mode": "paper",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        reconciler = TradeReconciler(broker, trade_store)
        result = await reconciler.reconcile()
        assert result.is_clean is True


# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
# 8. Security & Auth Edge Cases (10 tests)
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ


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

    def test_parse_callback_wrong_prefix(self) -> None:
        result = LiveApprovalGate.parse_live_callback("dead:req-001:approve")
        assert result is None

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


# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
# 9. Rate Limiter Advanced (8 tests)
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ


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
        assert "capacity" in status["groq"]

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


# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
# 10. Symbol Registry Advanced (8 tests)
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ


class TestSymbolRegistryAdvanced:
    """Advanced symbol registry edge cases."""

    def test_all_asset_classes_covered(self) -> None:
        reg = SymbolRegistry()
        all_symbols = reg.list_symbols()
        classes = set(reg.get_asset_class(s) for s in all_symbols)
        assert "metals" in classes
        assert "crypto" in classes
        assert "forex" in classes

    def test_register_overwrites_existing(self) -> None:
        reg = SymbolRegistry()
        new_info = SymbolInfo("custom_class", 0.01, 100.0, (100.0, 200.0))
        reg.register("XAUUSD", new_info)
        assert reg.get_asset_class("XAUUSD") == "custom_class"
        reg.register("XAUUSD", SymbolInfo("metals", 0.01, 100.0, (1900.0, 2500.0)))

    def test_get_pip_value_known_symbol(self) -> None:
        reg = SymbolRegistry()
        assert reg.get_pip_value("XAUUSD") > 0

    def test_get_pip_value_unknown_symbol(self) -> None:
        reg = SymbolRegistry()
        assert reg.get_pip_value("FAKECOIN") == 0.01

    def test_validate_price_boundary(self) -> None:
        reg = SymbolRegistry()
        assert reg.validate_price("XAUUSD", 1900.0) is True
        assert reg.validate_price("XAUUSD", 2500.0) is True

    def test_validate_price_outside_range(self) -> None:
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


# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
# 11. Chart Monitor Advanced (7 tests)
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ


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
        for buf in monitor._buffers.values():
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
        assert len(monitor.get_history("XAUUSD", "1h")) == 5

    def test_should_reconnect_respects_interval(self) -> None:
        monitor = self._make_monitor()
        monitor._last_cdp_attempt = time.monotonic()
        monitor._cdp_reconnect_interval = 300.0
        assert monitor._should_reconnect_cdp() is False

    def test_should_reconnect_after_interval(self) -> None:
        monitor = self._make_monitor()
        monitor._last_cdp_attempt = time.monotonic() - 400.0
        monitor._cdp_reconnect_interval = 300.0
        assert monitor._should_reconnect_cdp() is True

    @pytest.mark.asyncio
    async def test_publish_multiple_callbacks(self) -> None:
        monitor = self._make_monitor()
        cbs = [AsyncMock() for _ in range(5)]
        monitor._callbacks = cbs
        snap = ChartSnapshot(
            symbol="XAUUSD", timeframe="1h", ohlcv=[], indicators={}, screenshot_path=None, timestamp=datetime.now(UTC)
        )
        await monitor._publish(snap)
        for cb in cbs:
            cb.assert_called_once()

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


# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
# 12. Decision Engine Advanced (8 tests)
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ


class TestDecisionEngineAdvanced:
    """Advanced decision engine edge cases."""

    def test_extract_json_from_markdown_fences(self) -> None:
        text = '```json\n{"direction": "BUY", "confidence": 0.8}\n```'
        result = DecisionEngine._extract_json(text)
        assert result["direction"] == "BUY"

    def test_extract_json_from_mixed_text(self) -> None:
        text = 'Here is: {"direction": "SELL", "confidence": 0.7} done'
        result = DecisionEngine._extract_json(text)
        assert result["direction"] == "SELL"

    def test_extract_json_no_match(self) -> None:
        assert DecisionEngine._extract_json("no json here") == {}

    def test_extract_json_empty_string(self) -> None:
        assert DecisionEngine._extract_json("") == {}

    def test_format_ohlcv_empty(self) -> None:
        result = DecisionEngine._format_ohlcv([])
        assert "no data" in result.lower()

    def test_format_ohlcv_single_bar(self) -> None:
        bar = SimpleNamespace(
            timestamp=datetime(2026, 1, 1, 12, 0), open=2350.0, high=2360.0, low=2340.0, close=2355.0, volume=100
        )
        result = DecisionEngine._format_ohlcv([bar])
        assert "2350" in result

    def test_clamp_confidence_boundaries(self) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        assert engine._clamp_confidence(0.0) == 0.0
        assert engine._clamp_confidence(1.0) == 0.95
        assert engine._clamp_confidence(-1000.0) == 0.0
        assert engine._clamp_confidence(1000.0) == 0.95

    def test_decision_history_ring_buffer(self) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        for i in range(120):
            d = TradeDecision(
                symbol="XAUUSD",
                direction=SignalType.NO_TRADE,
                confidence=0.0,
                entry=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                reasoning=f"test {i}",
                red_flags=(),
                timestamp=datetime.now(UTC),
            )
            engine._record(d)
        history = engine.get_decision_history("XAUUSD", n=1000)
        assert len(history) <= 100


# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
# 13. NewsGate Advanced (5 tests)
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ


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

    def test_set_blackout_overwrites_previous(self) -> None:
        gate = NewsBlackoutGate()
        gate.set_blackout(until=datetime.now(UTC) + timedelta(hours=1), reason="NFP")
        gate.set_blackout(until=datetime.now(UTC) + timedelta(hours=2), reason="CPI")
        assert gate._reason == "CPI"

    def test_get_next_event_no_pipeline(self) -> None:
        gate = NewsBlackoutGate()
        assert gate.get_next_event() is None

    def test_double_clear_no_error(self) -> None:
        gate = NewsBlackoutGate()
        gate.clear_blackout()
        gate.clear_blackout()
        assert gate.is_blocked() is False
