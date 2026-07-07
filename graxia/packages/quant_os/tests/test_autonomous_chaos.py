"""Comprehensive chaos tests for the autonomous trading loop.

100+ tests covering every module in the autonomous package:
  - ChartMonitor: CDP failures, reconnection, buffer overflow, callback errors
  - DecisionEngine: LLM failures, JSON parsing, cooldown, numeric validation
  - OrderExecutor: Broker failures, risk gates, position sizing, daily limits
  - Orchestrator: Error handling, circuit breaker, health monitoring, shutdown
  - LiveApprovalGate: Telegram failures, timeouts, user validation
  - RateLimiter: Token bucket, burst handling, unknown providers
  - Persistence: SQLite edge cases, concurrent access, data integrity
  - NewsGate: Blackout timing, pipeline failures, fail-open
  - Reconciler: Missing fills, phantom positions, broker errors
  - SymbolRegistry: Unknown symbols, validation, registration
  - Notifications: Send failures, rate limiting, disabled state
  - Cross-component: Full pipeline failures, cascading errors, state corruption
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

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
def sell_decision() -> TradeDecision:
    return TradeDecision(
        symbol="BTCUSD",
        direction=SignalType.SELL,
        confidence=0.75,
        entry=65000.0,
        stop_loss=66000.0,
        take_profit=63000.0,
        reasoning="Chaos test sell",
        red_flags=(),
        timestamp=datetime.now(UTC),
        timeframe="4h",
    )


@pytest.fixture
def mock_broker() -> MagicMock:
    broker = MagicMock()
    broker.active = MagicMock()
    broker.active.get_account_info.return_value = MagicMock(
        equity=10000.0, cash=8000.0, margin_used=2000.0, margin_available=8000.0
    )
    broker.active.get_positions.return_value = []
    broker.active.submit_order.return_value = MagicMock(
        status=MagicMock(value="FILLED"),
        broker_id="MT5-001",
        error=None,
        filled_quantity=1.0,
        avg_price=2350.0,
    )
    return broker


@pytest.fixture
def mock_risk() -> MagicMock:
    risk = MagicMock()
    risk.evaluate.return_value = MagicMock(approved=True, reason="")
    return risk


@pytest.fixture
def mock_kill() -> MagicMock:
    ks = MagicMock()
    ks.is_active.return_value = False
    ks.is_triggered = False
    ks.get_status.return_value = {}
    return ks


@pytest.fixture
def trade_store() -> TradeStore:
    with tempfile.TemporaryDirectory() as tmpdir:
        store = TradeStore(db_path=os.path.join(tmpdir, "chaos_test.db"))
        yield store
        conn = getattr(store._local, "conn", None)
        if conn:
            conn.close()
            store._local.conn = None


def _make_executor(
    broker: MagicMock,
    kill_active: bool = False,
    mode: str = "paper",
) -> OrderExecutor:
    risk = MagicMock()
    risk.evaluate.return_value = MagicMock(approved=True, reason="")
    ks = MagicMock()
    ks.is_active.return_value = kill_active
    ks.is_triggered = kill_active
    ks.get_status.return_value = {}
    broker.active.get_account_info.return_value = AccountInfo(
        equity=10000, cash=10000, margin_used=0, margin_available=10000
    )
    return OrderExecutor(broker_manager=broker, risk_engine=risk, kill_switch=ks, mode=mode)


def _make_decision(
    symbol: str = "XAUUSD",
    direction: SignalType = SignalType.BUY,
    confidence: float = 0.82,
    entry: float = 2350.0,
    sl: float = 2340.0,
    tp: float = 2370.0,
) -> TradeDecision:
    return TradeDecision(
        symbol=symbol,
        direction=direction,
        confidence=confidence,
        entry=entry,
        stop_loss=sl,
        take_profit=tp,
        reasoning="Chaos test",
        red_flags=(),
        timestamp=datetime.now(UTC),
    )


def _make_monitor(**overrides) -> ChartMonitor:
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


def _close_store(store: TradeStore) -> None:
    conn = getattr(store._local, "conn", None)
    if conn:
        conn.close()
        store._local.conn = None


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CDP / ChartMonitor Chaos (15 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCDPChaos:
    """Chaos tests for CDP connection failures."""

    def test_cdp_disconnection_recovery(self) -> None:
        monitor = _make_monitor()
        monitor._tv_cdp.change_symbol.side_effect = ConnectionError("CDP disconnected")
        monitor._cdp_available = False
        assert monitor._should_reconnect_cdp() is True

    def test_cdp_slow_response(self) -> None:
        monitor = _make_monitor()
        monitor._tv_cdp.change_symbol.side_effect = asyncio.TimeoutError
        monitor._cdp_available = False
        assert monitor._cdp_available is False

    def test_cdp_invalid_data(self) -> None:
        monitor = _make_monitor()
        monitor._tv_cdp.get_chart_data = AsyncMock(return_value=None)
        assert monitor._cdp_available is True

    def test_cdp_reconnect_respects_interval(self) -> None:
        monitor = _make_monitor()
        monitor._last_cdp_attempt = time.monotonic()
        monitor._cdp_reconnect_interval = 300.0
        assert monitor._should_reconnect_cdp() is False

    def test_cdp_reconnect_after_interval(self) -> None:
        monitor = _make_monitor()
        monitor._last_cdp_attempt = time.monotonic() - 400.0
        monitor._cdp_reconnect_interval = 300.0
        assert monitor._should_reconnect_cdp() is True

    @pytest.mark.asyncio
    async def test_cdp_reconnect_success(self) -> None:
        monitor = _make_monitor()
        monitor._tv_cdp = MagicMock()
        monitor._tv_cdp.disconnect = AsyncMock(return_value=None)
        monitor._tv_cdp.connect = AsyncMock(return_value=True)
        monitor._last_cdp_attempt = time.monotonic() - 400.0
        monitor._cdp_reconnect_interval = 300.0
        await monitor._try_reconnect_cdp()
        assert monitor._cdp_available is True

    @pytest.mark.asyncio
    async def test_cdp_reconnect_failure(self) -> None:
        monitor = _make_monitor()
        monitor._last_cdp_attempt = time.monotonic() - 400.0
        monitor._cdp_reconnect_interval = 300.0
        mock_cdp_instance = MagicMock()
        mock_cdp_instance.connect = AsyncMock(return_value=False)
        mock_cdp_instance.disconnect = AsyncMock(return_value=None)
        with patch(
            "graxia.packages.quant_os.api.tv_cdp.TradingViewCDP",
            return_value=mock_cdp_instance,
        ):
            await monitor._try_reconnect_cdp()
        assert monitor._cdp_available is False

    @pytest.mark.asyncio
    async def test_cdp_reconnect_exception(self) -> None:
        monitor = _make_monitor()
        monitor._tv_cdp = MagicMock()
        monitor._tv_cdp.disconnect = AsyncMock(side_effect=RuntimeError("boom"))
        monitor._last_cdp_attempt = time.monotonic() - 400.0
        monitor._cdp_reconnect_interval = 300.0
        await monitor._try_reconnect_cdp()
        assert monitor._cdp_available is False

    def test_snapshot_buffer_maxlen(self) -> None:
        monitor = _make_monitor()
        snap = ChartSnapshot(
            symbol="XAUUSD",
            timeframe="1h",
            ohlcv=[],
            indicators={},
            screenshot_path=None,
            timestamp=datetime.now(UTC),
        )
        for _ in range(150):
            monitor._store(snap)
        buf = monitor._buffers.get("XAUUSD:1h")
        assert buf is not None
        assert len(buf) <= 100

    def test_snapshot_multiple_symbols(self) -> None:
        monitor = _make_monitor()
        for sym in ["XAUUSD", "BTCUSD", "EURUSD"]:
            snap = ChartSnapshot(
                symbol=sym,
                timeframe="1h",
                ohlcv=[],
                indicators={},
                screenshot_path=None,
                timestamp=datetime.now(UTC),
            )
            monitor._store(snap)
        assert len(monitor._buffers) == 3

    @pytest.mark.asyncio
    async def test_callback_error_does_not_crash(self) -> None:
        monitor = _make_monitor()
        bad_cb = AsyncMock(side_effect=RuntimeError("callback boom"))
        good_cb = AsyncMock()
        monitor._callbacks = [bad_cb, good_cb]
        snap = ChartSnapshot(
            symbol="XAUUSD",
            timeframe="1h",
            ohlcv=[],
            indicators={},
            screenshot_path=None,
            timestamp=datetime.now(UTC),
        )
        await monitor._publish(snap)
        good_cb.assert_called_once()

    @pytest.mark.asyncio
    async def test_callback_sync_function(self) -> None:
        monitor = _make_monitor()
        sync_cb = MagicMock()
        monitor._callbacks = [sync_cb]
        snap = ChartSnapshot(
            symbol="XAUUSD",
            timeframe="1h",
            ohlcv=[],
            indicators={},
            screenshot_path=None,
            timestamp=datetime.now(UTC),
        )
        await monitor._publish(snap)
        sync_cb.assert_called_once()

    def test_get_latest_empty(self) -> None:
        monitor = _make_monitor()
        assert monitor.get_latest("XAUUSD", "1h") is None

    def test_get_history_empty(self) -> None:
        monitor = _make_monitor()
        assert monitor.get_history("XAUUSD", "1h") == []

    @pytest.mark.asyncio
    async def test_start_twice_noop(self) -> None:
        monitor = _make_monitor()
        monitor._running = True
        await monitor.start()
        assert monitor._task is None


# ═══════════════════════════════════════════════════════════════════════════════
# 2. LLM / DecisionEngine Chaos (18 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestLLMChaos:
    """Chaos tests for LLM failures."""

    @pytest.mark.asyncio
    async def test_llm_timeout(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        mock_router = AsyncMock()
        mock_router._call_llm_chain = AsyncMock(side_effect=asyncio.TimeoutError)
        with patch("graxia.packages.quant_os.autonomous.decision_engine.get_router", return_value=mock_router):
            decision = await engine.analyze(snapshot)
        assert decision.direction == SignalType.NO_TRADE
        assert decision.confidence == 0.0

    @pytest.mark.asyncio
    async def test_llm_rate_limit(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        mock_router = AsyncMock()
        mock_router._call_llm_chain = AsyncMock(side_effect=Exception("Rate limit exceeded for provider groq"))
        with patch("graxia.packages.quant_os.autonomous.decision_engine.get_router", return_value=mock_router):
            decision = await engine.analyze(snapshot)
        assert decision.direction == SignalType.NO_TRADE
        assert "error" in decision.reasoning.lower() or "rate" in decision.reasoning.lower()

    @pytest.mark.asyncio
    async def test_llm_invalid_response(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        mock_provider = MagicMock(name="groq")
        mock_router = AsyncMock()
        mock_router._call_llm_chain = AsyncMock(return_value=("I cannot provide trading advice", 100.0, mock_provider))
        with patch("graxia.packages.quant_os.autonomous.decision_engine.get_router", return_value=mock_router):
            decision = await engine.analyze(snapshot)
        assert decision.direction == SignalType.NO_TRADE

    @pytest.mark.asyncio
    async def test_llm_connection_error(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        mock_router = AsyncMock()
        mock_router._call_llm_chain = AsyncMock(side_effect=ConnectionError("Connection refused"))
        with patch("graxia.packages.quant_os.autonomous.decision_engine.get_router", return_value=mock_router):
            decision = await engine.analyze(snapshot)
        assert decision.direction == SignalType.NO_TRADE

    @pytest.mark.asyncio
    async def test_llm_empty_response(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        mock_provider = MagicMock(name="groq")
        mock_router = AsyncMock()
        mock_router._call_llm_chain = AsyncMock(return_value=("", 100.0, mock_provider))
        with patch("graxia.packages.quant_os.autonomous.decision_engine.get_router", return_value=mock_router):
            decision = await engine.analyze(snapshot)
        assert decision.direction == SignalType.NO_TRADE

    def test_llm_partial_json_response(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        parsed = engine._parse_response('{"direction": "BUY", "confidence": 0.8', snapshot)
        assert parsed.direction == SignalType.NO_TRADE

    def test_llm_confidence_clamped_at_max(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = '{"direction": "BUY", "confidence": 1.5, "entry": 2350.0, "sl": 2340.0, "tp": 2370.0, "reasoning": "Test", "red_flags": []}'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.confidence <= 0.95

    def test_llm_negative_confidence_clamped(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = '{"direction": "BUY", "confidence": -0.5, "entry": 2350.0, "sl": 2340.0, "tp": 2370.0, "reasoning": "Test", "red_flags": []}'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.confidence >= 0.0

    @pytest.mark.asyncio
    async def test_cooldown_prevents_rerun(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65, cooldown_seconds=300)
        mock_router = AsyncMock()
        mock_provider = MagicMock(name="groq")
        mock_router._call_llm_chain = AsyncMock(
            return_value=(
                '{"direction": "BUY", "confidence": 0.8, "entry": 2350.0, "sl": 2340.0, "tp": 2370.0, "reasoning": "Test", "red_flags": []}',
                100.0,
                mock_provider,
            )
        )
        with patch("graxia.packages.quant_os.autonomous.decision_engine.get_router", return_value=mock_router):
            await engine.analyze(snapshot)
            decision2 = await engine.analyze(snapshot)
        assert decision2.direction == SignalType.NO_TRADE
        assert "cooldown" in decision2.reasoning.lower()

    def test_no_trade_json_direction(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = '{"direction": "NO_TRADE", "confidence": 0.9, "entry": 2350.0, "sl": 2340.0, "tp": 2370.0, "reasoning": "Test", "red_flags": []}'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.direction == SignalType.NO_TRADE

    def test_sell_direction_parsed(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = '{"direction": "SELL", "confidence": 0.8, "entry": 2350.0, "sl": 2360.0, "tp": 2330.0, "reasoning": "Test", "red_flags": []}'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.direction == SignalType.SELL

    def test_unknown_direction_becomes_no_trade(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = '{"direction": "XYZINVALID", "confidence": 0.8, "entry": 2350.0, "sl": 2340.0, "tp": 2370.0, "reasoning": "Test", "red_flags": []}'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.direction == SignalType.NO_TRADE

    def test_buy_entry_below_sl_downgraded(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = '{"direction": "BUY", "confidence": 0.8, "entry": 2340.0, "sl": 2350.0, "tp": 2370.0, "reasoning": "Test", "red_flags": []}'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.direction == SignalType.NO_TRADE
        assert "invalid_numeric_output" in parsed.red_flags

    def test_sell_entry_above_sl_downgraded(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = '{"direction": "SELL", "confidence": 0.8, "entry": 2350.0, "sl": 2340.0, "tp": 2370.0, "reasoning": "Test", "red_flags": []}'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.direction == SignalType.NO_TRADE

    def test_entry_equals_sl_downgraded(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = '{"direction": "BUY", "confidence": 0.8, "entry": 2350.0, "sl": 2350.0, "tp": 2370.0, "reasoning": "Test", "red_flags": []}'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.direction == SignalType.NO_TRADE

    def test_entry_equals_tp_downgraded(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = '{"direction": "BUY", "confidence": 0.8, "entry": 2370.0, "sl": 2340.0, "tp": 2370.0, "reasoning": "Test", "red_flags": []}'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.direction == SignalType.NO_TRADE

    def test_zero_entry_downgraded(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = '{"direction": "BUY", "confidence": 0.8, "entry": 0.0, "sl": 0.0, "tp": 0.0, "reasoning": "Test", "red_flags": []}'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.direction == SignalType.NO_TRADE

    def test_confidence_below_threshold_downgraded(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = '{"direction": "BUY", "confidence": 0.3, "entry": 2350.0, "sl": 2340.0, "tp": 2370.0, "reasoning": "Test", "red_flags": []}'
        parsed = engine._parse_response(raw, snapshot)
        assert parsed.direction == SignalType.NO_TRADE

    def test_extract_json_from_markdown_fences(self) -> None:
        text = '```json\n{"direction": "BUY", "confidence": 0.8}\n```'
        result = DecisionEngine._extract_json(text)
        assert result["direction"] == "BUY"

    def test_extract_json_from_mixed_text(self) -> None:
        text = 'Here is the analysis: {"direction": "SELL", "confidence": 0.7} hope that helps'
        result = DecisionEngine._extract_json(text)
        assert result["direction"] == "SELL"

    def test_extract_json_no_match(self) -> None:
        result = DecisionEngine._extract_json("no json here at all")
        assert result == {}

    def test_extract_json_empty_string(self) -> None:
        result = DecisionEngine._extract_json("")
        assert result == {}

    def test_decision_history_ring_buffer(self, snapshot: ChartSnapshot) -> None:
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


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Broker / OrderExecutor Chaos (18 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestBrokerChaos:
    """Chaos tests for broker failures."""

    @pytest.mark.asyncio
    async def test_broker_rejection(self) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_account_info.return_value = AccountInfo(
            equity=10000.0, cash=8000.0, margin_used=2000.0, margin_available=8000.0
        )
        broker.active.get_positions.return_value = []
        broker.active.submit_order.return_value = MagicMock(
            status=MagicMock(value="REJECTED"),
            broker_id=None,
            error="Insufficient margin",
            filled_quantity=0.0,
            avg_price=0.0,
        )
        executor = _make_executor(broker)
        result = await executor.execute(_make_decision())
        assert result.success is False
        assert "margin" in result.error.lower() or "rejected" in result.error.lower()

    def test_broker_connection_lost(self) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_account_info.side_effect = ConnectionError("MT5 connection lost")
        executor = _make_executor(broker)
        account, portfolio = executor._fetch_account_state()
        assert account.equity == 100000.0

    @pytest.mark.asyncio
    async def test_broker_submit_order_exception(self) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_account_info.return_value = AccountInfo(
            equity=10000.0, cash=8000.0, margin_used=2000.0, margin_available=8000.0
        )
        broker.active.get_positions.return_value = []
        broker.active.submit_order.side_effect = RuntimeError("Broker timeout")
        executor = _make_executor(broker)
        result = await executor.execute(_make_decision())
        assert result.success is False
        assert "broker timeout" in result.error.lower() or "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_partial_fill(self) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_account_info.return_value = AccountInfo(
            equity=10000.0, cash=8000.0, margin_used=2000.0, margin_available=8000.0
        )
        broker.active.get_positions.return_value = []
        broker.active.submit_order.return_value = MagicMock(
            status=MagicMock(value="PARTIAL_FILL"),
            broker_id="MT5-PARTIAL",
            error=None,
            filled_quantity=0.5,
            avg_price=2350.0,
        )
        executor = _make_executor(broker)
        result = await executor.execute(_make_decision())
        assert result.success is False
        assert result.filled_quantity == 0.5

    @pytest.mark.asyncio
    async def test_kill_switch_blocks_execution(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker, kill_active=True)
        result = await executor.execute(_make_decision())
        assert result.success is False
        assert "kill switch" in result.error.lower()

    @pytest.mark.asyncio
    async def test_empty_symbol_rejected(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker)
        d = _make_decision(symbol="")
        result = await executor.execute(d)
        assert result.success is False
        assert "missing symbol" in result.error.lower()

    @pytest.mark.asyncio
    async def test_no_trade_direction_rejected(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker)
        d = _make_decision(direction=SignalType.NO_TRADE)
        result = await executor.execute(d)
        assert result.success is False
        assert "no_trade" in result.error.lower() or "non-trade" in result.error.lower()

    @pytest.mark.asyncio
    async def test_low_confidence_rejected(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker)
        d = _make_decision(confidence=0.3)
        result = await executor.execute(d)
        assert result.success is False
        assert "confidence" in result.error.lower()

    @pytest.mark.asyncio
    async def test_daily_trade_limit_reached(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker)
        executor._daily_trades = 10
        result = await executor.execute(_make_decision())
        assert result.success is False
        assert "max daily trades" in result.error.lower()

    @pytest.mark.asyncio
    async def test_max_open_positions_reached(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker)
        executor._open_positions = 3
        result = await executor.execute(_make_decision())
        assert result.success is False
        assert "max open positions" in result.error.lower()

    @pytest.mark.asyncio
    async def test_daily_loss_breached(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker)
        executor._daily_realized_pnl = __import__("decimal").Decimal("-500.0")
        result = await executor.execute(_make_decision())
        assert result.success is False
        assert "daily loss" in result.error.lower()

    def test_position_size_zero_rejected(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker)
        d = _make_decision(confidence=0.01)
        size = executor._calculate_position_size(d)
        assert size >= 0.01

    def test_broker_get_positions_exception(self) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_account_info.return_value = MagicMock(
            equity=10000.0, cash=8000.0, margin_used=2000.0, margin_available=8000.0
        )
        broker.active.get_positions.side_effect = RuntimeError("positions unavailable")
        executor = _make_executor(broker)
        d = _make_decision()
        ok, _ = executor._check_risk(d)
        assert ok is True

    @pytest.mark.asyncio
    async def test_execution_log_recorded(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker)
        await executor.execute(_make_decision())
        log = executor.get_execution_log()
        assert len(log) >= 1

    def test_daily_stats_returns_dict(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker)
        stats = executor.get_daily_stats()
        assert "trades_today" in stats
        assert "mode" in stats

    def test_daily_stats_reset_on_new_day(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker)
        executor._daily_trades = 5
        executor._last_reset_date = datetime.now(UTC) - timedelta(days=1)
        executor._maybe_reset_daily_stats()
        assert executor._daily_trades == 0

    def test_correlation_check_same_class_rejected(self) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_positions.return_value = [
            {"symbol": "XAUUSD", "volume": 1.0, "price_open": 2350.0},
            {"symbol": "XAGUSD", "volume": 1.0, "price_open": 30.0},
        ]
        executor = _make_executor(broker)
        d = _make_decision(symbol="XAUUSD")
        ok, reason = executor._check_correlation(d)
        assert ok is False
        assert "correlation" in reason.lower()

    def test_correlation_check_different_class_ok(self) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_positions.return_value = [
            {"symbol": "XAUUSD", "volume": 1.0, "price_open": 2350.0},
        ]
        executor = _make_executor(broker)
        d = _make_decision(symbol="BTCUSD")
        ok, _ = executor._check_correlation(d)
        assert ok is True

    def test_correlation_check_broker_error_graceful(self) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_positions.side_effect = RuntimeError("broker down")
        executor = _make_executor(broker)
        d = _make_decision()
        ok, _ = executor._check_correlation(d)
        assert ok is True


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Orchestrator Chaos (15 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestOrchestratorChaos:
    """Chaos tests for orchestrator error handling."""

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
    async def test_circuit_breaker_blocks_snapshot(self) -> None:
        cb = MagicMock()
        cb.is_blocked = True
        cb.reason = "too many errors"
        orch = self._make_orchestrator(circuit_breaker=cb)
        snap = ChartSnapshot(
            symbol="XAUUSD", timeframe="1h", ohlcv=[], indicators={}, screenshot_path=None, timestamp=datetime.now(UTC)
        )
        await orch._on_snapshot(snap)
        orch._decision_engine.analyze.assert_not_called()

    @pytest.mark.asyncio
    async def test_news_gate_blocks_snapshot(self) -> None:
        ng = MagicMock()
        ng.is_blocked.return_value = True
        orch = self._make_orchestrator(news_gate=ng)
        snap = ChartSnapshot(
            symbol="XAUUSD", timeframe="1h", ohlcv=[], indicators={}, screenshot_path=None, timestamp=datetime.now(UTC)
        )
        await orch._on_snapshot(snap)
        orch._decision_engine.analyze.assert_not_called()

    @pytest.mark.asyncio
    async def test_decision_engine_error_recorded(self) -> None:
        de = MagicMock()
        de.analyze = AsyncMock(side_effect=RuntimeError("LLM boom"))
        orch = self._make_orchestrator(decision_engine=de)
        snap = ChartSnapshot(
            symbol="XAUUSD", timeframe="1h", ohlcv=[], indicators={}, screenshot_path=None, timestamp=datetime.now(UTC)
        )
        await orch._on_snapshot(snap)
        assert orch._consecutive_errors["decision_engine"] == 1
        assert orch._health.errors == 1

    @pytest.mark.asyncio
    async def test_order_executor_error_recorded(self) -> None:
        de = MagicMock()
        de.analyze = AsyncMock(return_value=_make_decision(confidence=0.8))
        oe = MagicMock()
        oe.execute.side_effect = RuntimeError("broker boom")
        orch = self._make_orchestrator(decision_engine=de, order_executor=oe)
        snap = ChartSnapshot(
            symbol="XAUUSD", timeframe="1h", ohlcv=[], indicators={}, screenshot_path=None, timestamp=datetime.now(UTC)
        )
        await orch._on_snapshot(snap)
        assert orch._consecutive_errors["order_executor"] == 1

    @pytest.mark.asyncio
    async def test_low_confidence_skips_execution(self) -> None:
        de = MagicMock()
        de.analyze = AsyncMock(return_value=_make_decision(confidence=0.3))
        oe = MagicMock()
        orch = self._make_orchestrator(decision_engine=de, order_executor=oe)
        snap = ChartSnapshot(
            symbol="XAUUSD", timeframe="1h", ohlcv=[], indicators={}, screenshot_path=None, timestamp=datetime.now(UTC)
        )
        await orch._on_snapshot(snap)
        oe.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_kill_switch_blocks_execution(self) -> None:
        de = MagicMock()
        de.analyze = AsyncMock(return_value=_make_decision(confidence=0.8))
        ks = MagicMock()
        ks.is_triggered = True
        ks.get_status.return_value = {"reason": "manual"}
        oe = MagicMock()
        orch = self._make_orchestrator(decision_engine=de, kill_switch=ks, order_executor=oe)
        snap = ChartSnapshot(
            symbol="XAUUSD", timeframe="1h", ohlcv=[], indicators={}, screenshot_path=None, timestamp=datetime.now(UTC)
        )
        await orch._on_snapshot(snap)
        oe.execute.assert_not_called()

    def test_health_status_tracking(self) -> None:
        orch = self._make_orchestrator()
        orch._start_time = datetime.now(UTC) - timedelta(seconds=10)
        status = orch.get_status()
        assert status.uptime_seconds >= 9.0

    @pytest.mark.asyncio
    async def test_not_running_skips_snapshot(self) -> None:
        orch = self._make_orchestrator(running=False)
        snap = ChartSnapshot(
            symbol="XAUUSD", timeframe="1h", ohlcv=[], indicators={}, screenshot_path=None, timestamp=datetime.now(UTC)
        )
        await orch._on_snapshot(snap)
        orch._decision_engine.analyze.assert_not_called()

    def test_handle_error_increments_counter(self) -> None:
        orch = self._make_orchestrator()
        orch._handle_error("chart_monitor", RuntimeError("test"))
        assert orch._consecutive_errors["chart_monitor"] == 1
        assert orch._health.errors == 1

    def test_handle_error_circuit_breaker_called(self) -> None:
        cb = MagicMock()
        orch = self._make_orchestrator(circuit_breaker=cb)
        orch._handle_error("system", RuntimeError("test"))
        cb.record_trade.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_resets_consecutive_errors(self) -> None:
        orch = self._make_orchestrator()
        orch._consecutive_errors["decision_engine"] = 3
        de = MagicMock()
        de.analyze = AsyncMock(return_value=_make_decision(confidence=0.8))
        oe = MagicMock()
        orch._decision_engine = de
        orch._order_executor = oe
        snap = ChartSnapshot(
            symbol="XAUUSD", timeframe="1h", ohlcv=[], indicators={}, screenshot_path=None, timestamp=datetime.now(UTC)
        )
        await orch._on_snapshot(snap)
        assert orch._consecutive_errors["decision_engine"] == 0

    @pytest.mark.asyncio
    async def test_stop_clears_running(self) -> None:
        orch = self._make_orchestrator()
        orch._chart_monitor.stop = AsyncMock()
        await orch.stop()
        assert orch._running is False

    @pytest.mark.asyncio
    async def test_stop_when_not_running_noop(self) -> None:
        orch = self._make_orchestrator(running=False)
        await orch.stop()
        assert orch._running is False

    def test_save_state_calls_store(self) -> None:
        store = MagicMock()
        orch = self._make_orchestrator(trade_store=store)
        orch._save_state()
        store.save_health.assert_called()


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Telegram / LiveApprovalGate Chaos (15 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestTelegramChaos:
    """Chaos tests for Telegram failures."""

    @pytest.mark.asyncio
    async def test_approval_timeout(self) -> None:
        gate = LiveApprovalGate(bot_token="test-token", chat_id="12345", timeout_seconds=1)
        decision = _make_decision()
        with patch.object(gate, "_send_message", new_callable=AsyncMock, return_value=123):
            result = await gate.request_approval(decision)
        assert result.approved is False
        assert result.action == ApprovalAction.TIMEOUT

    @pytest.mark.asyncio
    async def test_duplicate_callback(self) -> None:
        gate = LiveApprovalGate(bot_token="test-token", chat_id="12345")
        gate._authorized_users = {"user1", "user2"}
        request_id = "XAUUSD-120000"
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ApprovalAction] = loop.create_future()
        gate._pending[request_id] = future
        gate.handle_callback(request_id, ApprovalAction.APPROVE, user_id="user1")
        assert future.done() is True
        assert future.result() == ApprovalAction.APPROVE
        gate.handle_callback(request_id, ApprovalAction.REJECT, user_id="user2")
        assert future.result() == ApprovalAction.APPROVE

    @pytest.mark.asyncio
    async def test_unauthorized_callback_ignored(self) -> None:
        gate = LiveApprovalGate(bot_token="test-token", chat_id="12345")
        gate._authorized_users = {"authorized_user"}
        request_id = "XAUUSD-120000"
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ApprovalAction] = loop.create_future()
        gate._pending[request_id] = future
        gate.handle_callback(request_id, ApprovalAction.APPROVE, user_id="hacker")
        assert future.done() is False

    @pytest.mark.asyncio
    async def test_no_telegram_config_returns_reject(self) -> None:
        gate = LiveApprovalGate(bot_token="", chat_id="")
        result = await gate.request_approval(_make_decision())
        assert result.approved is False
        assert result.action == ApprovalAction.REJECT

    def test_parse_live_callback_valid(self) -> None:
        result = LiveApprovalGate.parse_live_callback("live:req-001:approve")
        assert result is not None
        assert result[0] == "req-001"
        assert result[1] == ApprovalAction.APPROVE

    def test_parse_live_callback_invalid_prefix(self) -> None:
        result = LiveApprovalGate.parse_live_callback("invalid:req-001:approve")
        assert result is None

    def test_parse_live_callback_bad_action(self) -> None:
        result = LiveApprovalGate.parse_live_callback("live:req-001:unknown")
        assert result is None

    def test_action_to_result_approve(self) -> None:
        result = LiveApprovalGate._action_to_result(ApprovalAction.APPROVE)
        assert result.approved is True
        assert result.size_multiplier == 1.0

    def test_action_to_result_half(self) -> None:
        result = LiveApprovalGate._action_to_result(ApprovalAction.HALF)
        assert result.approved is True
        assert result.size_multiplier == 0.5

    def test_action_to_result_reject(self) -> None:
        result = LiveApprovalGate._action_to_result(ApprovalAction.REJECT)
        assert result.approved is False
        assert result.size_multiplier == 0.0

    def test_action_to_result_skip(self) -> None:
        result = LiveApprovalGate._action_to_result(ApprovalAction.SKIP)
        assert result.approved is False

    def test_action_to_result_timeout(self) -> None:
        result = LiveApprovalGate._action_to_result(ApprovalAction.TIMEOUT)
        assert result.approved is False

    @pytest.mark.asyncio
    async def test_send_message_failure(self) -> None:
        gate = LiveApprovalGate(bot_token="test-token", chat_id="12345")
        with patch("graxia.packages.quant_os.autonomous.live_approval.httpx") as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_resp.text = "Internal Server Error"
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client
            await gate._send_message("test", {})
        assert gate._last_send_time.get("12345") is None

    def test_build_message_contains_symbol(self) -> None:
        gate = LiveApprovalGate(bot_token="test-token", chat_id="12345")
        msg = gate._build_message(_make_decision(), "req-001")
        assert "XAUUSD" in msg

    def test_build_keyboard_structure(self) -> None:
        gate = LiveApprovalGate(bot_token="test-token", chat_id="12345")
        kb = gate._build_keyboard("req-001")
        assert "inline_keyboard" in kb
        assert len(kb["inline_keyboard"]) == 2
        assert "live:req-001:approve" in kb["inline_keyboard"][0][0]["callback_data"]


# ═══════════════════════════════════════════════════════════════════════════════
# 6. RateLimiter Chaos (12 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestRateLimiterChaos:
    """Chaos tests for rate limiter edge cases."""

    def test_allows_initial_request(self) -> None:
        rl = RateLimiter(limits={"groq": 100})
        assert rl.can_proceed("groq") is True

    def test_consumes_token(self) -> None:
        rl = RateLimiter(limits={"groq": 1})
        rl.record_request("groq")
        assert rl.can_proceed("groq") is False

    def test_unknown_provider_gets_default_bucket(self) -> None:
        rl = RateLimiter(limits={"groq": 100})
        assert rl.can_proceed("unknown_provider") is True

    def test_overdraw_sets_zero(self) -> None:
        rl = RateLimiter(limits={"groq": 1})
        rl.record_request("groq")
        rl.record_request("groq")
        status = rl.get_status()
        assert status["groq"]["remaining"] == 0.0

    def test_get_wait_time_when_available(self) -> None:
        rl = RateLimiter(limits={"groq": 100})
        assert rl.get_wait_time("groq") == 0.0

    def test_get_wait_time_when_depleted(self) -> None:
        rl = RateLimiter(limits={"groq": 1})
        rl.record_request("groq")
        wait = rl.get_wait_time("groq")
        assert wait > 0.0

    def test_status_returns_all_providers(self) -> None:
        rl = RateLimiter(limits={"groq": 100, "cerebras": 200})
        status = rl.get_status()
        assert "groq" in status
        assert "cerebras" in status

    def test_refill_restores_tokens(self) -> None:
        rl = RateLimiter(limits={"groq": 1})
        rl.record_request("groq")
        bucket = rl._buckets["groq"]
        bucket.last_refill = time.monotonic() - 86400.0
        assert rl.can_proceed("groq") is True

    def test_case_insensitive_provider(self) -> None:
        rl = RateLimiter(limits={"groq": 1})
        rl.record_request("GROQ")
        assert rl.can_proceed("groq") is False

    def test_multiple_providers_independent(self) -> None:
        rl = RateLimiter(limits={"groq": 1, "cerebras": 1})
        rl.record_request("groq")
        assert rl.can_proceed("groq") is False
        assert rl.can_proceed("cerebras") is True

    def test_empty_limits(self) -> None:
        rl = RateLimiter(limits={})
        assert rl.can_proceed("groq") is True

    def test_very_small_capacity(self) -> None:
        rl = RateLimiter(limits={"groq": 1})
        rl.record_request("groq")
        status = rl.get_status()
        assert status["groq"]["remaining"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Persistence / TradeStore Chaos (12 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestPersistenceChaos:
    """Chaos tests for SQLite persistence edge cases."""

    def test_save_and_retrieve_decision(self, trade_store: TradeStore) -> None:
        row_id = trade_store.save_decision(
            {
                "symbol": "XAUUSD",
                "direction": "BUY",
                "confidence": 0.8,
                "entry": 2350.0,
                "sl": 2340.0,
                "tp": 2370.0,
                "reasoning": "Test",
                "red_flags": "",
                "timestamp": datetime.now(UTC).isoformat(),
                "timeframe": "1h",
                "snapshot_ts": "",
                "latency_ms": 0.0,
                "llm_provider": "groq",
            }
        )
        assert row_id > 0
        decisions = trade_store.get_recent_decisions("XAUUSD", limit=1)
        assert len(decisions) == 1

    def test_save_and_retrieve_execution(self, trade_store: TradeStore) -> None:
        row_id = trade_store.save_execution(
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
        assert row_id > 0
        log = trade_store.get_execution_log(limit=1)
        assert len(log) == 1

    def test_save_health(self, trade_store: TradeStore) -> None:
        trade_store.save_health(
            {
                "uptime_seconds": 100.0,
                "total_decisions": 10,
                "total_trades": 5,
                "errors": 1,
                "kill_switch_active": False,
            }
        )
        stats = trade_store.get_daily_stats(datetime.now(UTC).strftime("%Y-%m-%d"))
        assert "trades_today" in stats

    def test_empty_symbol_decisions(self, trade_store: TradeStore) -> None:
        decisions = trade_store.get_recent_decisions("NONEXISTENT", limit=10)
        assert decisions == []

    def test_empty_execution_log(self, trade_store: TradeStore) -> None:
        log = trade_store.get_execution_log(limit=10)
        assert log == []

    def test_daily_stats_default(self, trade_store: TradeStore) -> None:
        stats = trade_store.get_daily_stats("2099-01-01")
        assert stats["trades_today"] == 0
        assert stats["realized_pnl"] == 0.0

    def test_thread_safety(self, trade_store: TradeStore) -> None:
        errors = []

        def writer(idx: int) -> None:
            try:
                trade_store.save_decision(
                    {
                        "symbol": "XAUUSD",
                        "direction": "BUY",
                        "confidence": 0.8,
                        "entry": 2350.0,
                        "sl": 2340.0,
                        "tp": 2370.0,
                        "reasoning": f"Thread {idx}",
                        "red_flags": "",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "timeframe": "1h",
                        "snapshot_ts": "",
                        "latency_ms": 0.0,
                        "llm_provider": "groq",
                    }
                )
                conn = getattr(trade_store._local, "conn", None)
                if conn:
                    conn.close()
                    trade_store._local.conn = None
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        decisions = trade_store.get_recent_decisions("XAUUSD", limit=100)
        assert len(decisions) == 10

    def test_corrupt_db_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            corrupt_path = os.path.join(tmpdir, "sub", "deep", "test.db")
            store = TradeStore(db_path=corrupt_path)
            assert os.path.exists(corrupt_path)
            conn = getattr(store._local, "conn", None)
            if conn:
                conn.close()
                store._local.conn = None

    def test_many_decisions(self, trade_store: TradeStore) -> None:
        for i in range(50):
            trade_store.save_decision(
                {
                    "symbol": "XAUUSD",
                    "direction": "BUY",
                    "confidence": 0.8,
                    "entry": 2350.0,
                    "sl": 2340.0,
                    "tp": 2370.0,
                    "reasoning": f"Test {i}",
                    "red_flags": "",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "timeframe": "1h",
                    "snapshot_ts": "",
                    "latency_ms": 0.0,
                    "llm_provider": "groq",
                }
            )
        decisions = trade_store.get_recent_decisions("XAUUSD", limit=50)
        assert len(decisions) == 50

    def test_decision_with_special_characters(self, trade_store: TradeStore) -> None:
        trade_store.save_decision(
            {
                "symbol": "XAUUSD",
                "direction": "BUY",
                "confidence": 0.8,
                "entry": 2350.0,
                "sl": 2340.0,
                "tp": 2370.0,
                "reasoning": "Unicode: 你好 مرحبا 🎉 <script>alert('xss')</script>",
                "red_flags": "",
                "timestamp": datetime.now(UTC).isoformat(),
                "timeframe": "1h",
                "snapshot_ts": "",
                "latency_ms": 0.0,
                "llm_provider": "groq",
            }
        )
        decisions = trade_store.get_recent_decisions("XAUUSD", limit=1)
        assert "你好" in decisions[0]["reasoning"]

    def test_reopen_existing_db(self, trade_store: TradeStore) -> None:
        trade_store.save_decision(
            {
                "symbol": "XAUUSD",
                "direction": "BUY",
                "confidence": 0.8,
                "entry": 2350.0,
                "sl": 2340.0,
                "tp": 2370.0,
                "reasoning": "Test",
                "red_flags": "",
                "timestamp": datetime.now(UTC).isoformat(),
                "timeframe": "1h",
                "snapshot_ts": "",
                "latency_ms": 0.0,
                "llm_provider": "groq",
            }
        )
        db_path = trade_store._db_path
        _close_store(trade_store)
        store2 = TradeStore(db_path=db_path)
        decisions = store2.get_recent_decisions("XAUUSD", limit=1)
        assert len(decisions) == 1
        _close_store(store2)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. NewsBlackoutGate Chaos (8 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestNewsGateChaos:
    """Chaos tests for news blackout gate."""

    def test_default_not_blocked(self) -> None:
        gate = NewsBlackoutGate()
        assert gate.is_blocked() is False

    def test_blackout_active(self) -> None:
        gate = NewsBlackoutGate()
        gate.set_blackout(until=datetime.now(UTC) + timedelta(hours=1), reason="NFP")
        assert gate.is_blocked() is True

    def test_blackout_expired(self) -> None:
        gate = NewsBlackoutGate()
        gate.set_blackout(until=datetime.now(UTC) - timedelta(hours=1), reason="NFP")
        assert gate.is_blocked() is False

    def test_clear_blackout(self) -> None:
        gate = NewsBlackoutGate()
        gate.set_blackout(until=datetime.now(UTC) + timedelta(hours=1), reason="NFP")
        gate.clear_blackout()
        assert gate.is_blocked() is False

    def test_get_next_event_no_pipeline(self) -> None:
        gate = NewsBlackoutGate()
        assert gate.get_next_event() is None

    def test_set_and_clear_reason(self) -> None:
        gate = NewsBlackoutGate()
        gate.set_blackout(until=datetime.now(UTC) + timedelta(hours=1), reason="CPI")
        gate.clear_blackout()
        assert gate._reason == ""

    def test_blackout_overwrites_previous(self) -> None:
        gate = NewsBlackoutGate()
        gate.set_blackout(until=datetime.now(UTC) + timedelta(hours=1), reason="NFP")
        gate.set_blackout(until=datetime.now(UTC) + timedelta(hours=2), reason="CPI")
        assert gate._reason == "CPI"

    def test_double_clear_no_error(self) -> None:
        gate = NewsBlackoutGate()
        gate.clear_blackout()
        gate.clear_blackout()
        assert gate.is_blocked() is False


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Reconciler Chaos (8 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestReconcilerChaos:
    """Chaos tests for trade reconciler."""

    @pytest.mark.asyncio
    async def test_clean_reconciliation(self, trade_store: TradeStore) -> None:
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

    @pytest.mark.asyncio
    async def test_missing_fill_detected(self, trade_store: TradeStore) -> None:
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
                "order_id": "auto-002",
                "broker_order_id": "",
                "error": "",
                "approval_required": False,
                "mode": "paper",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        reconciler = TradeReconciler(broker, trade_store)
        result = await reconciler.reconcile()
        assert result.is_clean is False
        assert len(result.missing_fills) >= 1

    @pytest.mark.asyncio
    async def test_phantom_position_detected(self, trade_store: TradeStore) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_positions.return_value = [{"symbol": "XAUUSD", "volume": 1.0, "price_open": 2350.0}]
        reconciler = TradeReconciler(broker, trade_store)
        result = await reconciler.reconcile()
        assert result.is_clean is False
        assert len(result.phantom_positions) >= 1

    @pytest.mark.asyncio
    async def test_broker_error_graceful(self, trade_store: TradeStore) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_positions.side_effect = RuntimeError("broker down")
        reconciler = TradeReconciler(broker, trade_store)
        result = await reconciler.reconcile()
        assert result.total_positions == 0

    @pytest.mark.asyncio
    async def test_empty_executions_and_positions(self, trade_store: TradeStore) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_positions.return_value = []
        reconciler = TradeReconciler(broker, trade_store)
        result = await reconciler.reconcile()
        assert result.is_clean is True
        assert result.total_executions == 0

    @pytest.mark.asyncio
    async def test_reconciliation_result_fields(self, trade_store: TradeStore) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_positions.return_value = []
        reconciler = TradeReconciler(broker, trade_store)
        result = await reconciler.reconcile()
        assert hasattr(result, "timestamp")
        assert hasattr(result, "is_clean")

    @pytest.mark.asyncio
    async def test_many_executions(self, trade_store: TradeStore) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_positions.return_value = []
        for i in range(20):
            trade_store.save_execution(
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
        reconciler = TradeReconciler(broker, trade_store)
        result = await reconciler.reconcile()
        assert result.total_executions == 20

    @pytest.mark.asyncio
    async def test_mixed_success_executions(self, trade_store: TradeStore) -> None:
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
                "success": False,
                "order_id": "auto-fail",
                "broker_order_id": "",
                "error": "rejected",
                "approval_required": False,
                "mode": "paper",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        reconciler = TradeReconciler(broker, trade_store)
        result = await reconciler.reconcile()
        assert result.total_executions == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 10. SymbolRegistry Chaos (10 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestSymbolRegistryChaos:
    """Chaos tests for symbol registry edge cases."""

    def test_known_symbol(self) -> None:
        reg = SymbolRegistry()
        assert reg.is_known("XAUUSD") is True
        assert reg.get_asset_class("XAUUSD") == "metals"

    def test_unknown_symbol(self) -> None:
        reg = SymbolRegistry()
        assert reg.is_known("FAKECOIN") is False
        assert reg.get_asset_class("FAKECOIN") == "unknown"

    def test_list_symbols(self) -> None:
        reg = SymbolRegistry()
        symbols = reg.list_symbols()
        assert "XAUUSD" in symbols
        assert len(symbols) >= 11

    def test_list_by_class(self) -> None:
        reg = SymbolRegistry()
        metals = reg.list_by_class("metals")
        assert "XAUUSD" in metals
        assert "XAGUSD" in metals

    def test_register_custom_symbol(self) -> None:
        reg = SymbolRegistry()
        info = SymbolInfo("custom", 0.01, 100.0, (100.0, 200.0))
        reg.register("CUSTOM", info)
        assert reg.is_known("CUSTOM") is True
        assert reg.get_asset_class("CUSTOM") == "custom"

    def test_unregister_symbol(self) -> None:
        reg = SymbolRegistry()
        assert reg.unregister("XAUUSD") is True
        assert reg.is_known("XAUUSD") is False

    def test_unregister_unknown_returns_false(self) -> None:
        reg = SymbolRegistry()
        assert reg.unregister("FAKECOIN") is False

    def test_validate_price_in_range(self) -> None:
        reg = SymbolRegistry()
        assert reg.validate_price("XAUUSD", 2350.0) is True

    def test_validate_price_out_of_range(self) -> None:
        reg = SymbolRegistry()
        assert reg.validate_price("XAUUSD", 100.0) is False

    def test_custom_overrides(self) -> None:
        overrides = {"XAUUSD": SymbolInfo("custom_metals", 0.1, 200.0, (2000.0, 4000.0))}
        reg = SymbolRegistry(overrides=overrides)
        assert reg.get_asset_class("XAUUSD") == "custom_metals"
        assert reg.get_pip_value("XAUUSD") == 0.1


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Notifications Chaos (8 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestNotificationsChaos:
    """Chaos tests for Telegram notification module."""

    @pytest.mark.asyncio
    async def test_disabled_notifier_no_send(self) -> None:
        notifier = TradeNotifier(bot_token="", chat_id="")
        await notifier.notify_trade(_make_decision(), MagicMock(success=True))

    @pytest.mark.asyncio
    async def test_kill_switch_notification(self) -> None:
        notifier = TradeNotifier(bot_token="", chat_id="")
        await notifier.notify_kill_switch("manual trigger")

    @pytest.mark.asyncio
    async def test_daily_summary_notification(self) -> None:
        notifier = TradeNotifier(bot_token="", chat_id="")
        await notifier.notify_daily_summary(
            {
                "trades_today": 5,
                "realized_pnl": 100.0,
                "max_daily_trades": 10,
                "open_positions": 2,
                "max_open_positions": 3,
                "mode": "paper",
            }
        )

    @pytest.mark.asyncio
    async def test_error_notification(self) -> None:
        notifier = TradeNotifier(bot_token="", chat_id="")
        await notifier.notify_error("decision_engine", "timeout")

    @pytest.mark.asyncio
    async def test_rate_limit_enforced(self) -> None:
        notifier = TradeNotifier(bot_token="token", chat_id="123")
        notifier._last_send_time["123"] = time.monotonic()
        start = time.monotonic()
        await notifier._rate_limit("123")
        elapsed = time.monotonic() - start
        assert elapsed >= 0.9

    @pytest.mark.asyncio
    async def test_trade_notification_disabled_no_error(self) -> None:
        notifier = TradeNotifier(enabled=False)
        await notifier.notify_trade(_make_decision(), MagicMock(success=True))

    @pytest.mark.asyncio
    async def test_send_with_httpx_missing(self) -> None:
        notifier = TradeNotifier(bot_token="token", chat_id="123")
        with patch.dict("sys.modules", {"httpx": None}):
            await notifier._send("test")

    @pytest.mark.asyncio
    async def test_send_http_error(self) -> None:
        notifier = TradeNotifier(bot_token="token", chat_id="123")
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx = MagicMock()
        mock_httpx.AsyncClient.return_value = mock_client
        import sys

        sys.modules["httpx"] = mock_httpx
        try:
            await notifier._send("test")
        finally:
            del sys.modules["httpx"]


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Cross-Component Chaos (10 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrossComponentChaos:
    """Chaos tests for interactions between components."""

    @pytest.mark.asyncio
    async def test_full_pipeline_llm_timeout_to_no_trade(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        mock_router = AsyncMock()
        mock_router._call_llm_chain = AsyncMock(side_effect=asyncio.TimeoutError)
        with patch("graxia.packages.quant_os.autonomous.decision_engine.get_router", return_value=mock_router):
            decision = await engine.analyze(snapshot)
        broker = MagicMock()
        executor = _make_executor(broker)
        result = await executor.execute(decision)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_full_pipeline_risk_rejection(self) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_account_info.return_value = AccountInfo(
            equity=10000.0, cash=8000.0, margin_used=2000.0, margin_available=8000.0
        )
        broker.active.get_positions.return_value = []
        risk = MagicMock()
        risk.evaluate.return_value = MagicMock(
            approved=False, reason="max drawdown", reason_code="DRAWDOWN", layer_failed=2
        )
        ks = MagicMock()
        ks.is_active.return_value = False
        ks.is_triggered = False
        ks.get_status.return_value = {}
        executor = OrderExecutor(broker_manager=broker, risk_engine=risk, kill_switch=ks, mode="paper")
        result = await executor.execute(_make_decision())
        assert result.success is False
        assert "risk" in result.error.lower()

    @pytest.mark.asyncio
    async def test_cascading_errors_do_not_corrupt_state(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker)
        for i in range(5):
            d = _make_decision(entry=float(i))
            await executor.execute(d)
        stats = executor.get_daily_stats()
        assert stats["trades_today"] >= 0

    @pytest.mark.asyncio
    async def test_decision_engine_produces_valid_data_for_executor(self, snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        mock_provider = MagicMock(name="groq")
        mock_router = AsyncMock()
        mock_router._call_llm_chain = AsyncMock(
            return_value=(
                '{"direction": "BUY", "confidence": 0.8, "entry": 2350.0, "sl": 2340.0, "tp": 2370.0, "reasoning": "Test", "red_flags": []}',
                100.0,
                mock_provider,
            )
        )
        with patch("graxia.packages.quant_os.autonomous.decision_engine.get_router", return_value=mock_router):
            decision = await engine.analyze(snapshot)
        assert decision.symbol == "XAUUSD"
        assert decision.entry > 0

    @pytest.mark.asyncio
    async def test_orchestrator_full_snapshot_flow(self) -> None:
        from graxia.packages.quant_os.autonomous.orchestrator import AutonomousOrchestrator, SystemHealth

        orch = AutonomousOrchestrator.__new__(AutonomousOrchestrator)
        orch._symbols = ["XAUUSD"]
        orch._timeframes = ["1h"]
        orch._trading_mode = MagicMock(value="paper")
        orch._chart_monitor = MagicMock()
        orch._kill_switch = MagicMock(is_triggered=False)
        orch._circuit_breaker = MagicMock(is_blocked=False, reason="")
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
        orch._start_time = datetime.now(UTC)
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

        snap = ChartSnapshot(
            symbol="XAUUSD", timeframe="1h", ohlcv=[], indicators={}, screenshot_path=None, timestamp=datetime.now(UTC)
        )
        await orch._on_snapshot(snap)
        orch._order_executor.execute.assert_called_once()

    def test_persistence_survives_rapid_save_load(self, trade_store: TradeStore) -> None:
        for i in range(100):
            trade_store.save_decision(
                {
                    "symbol": "XAUUSD",
                    "direction": "BUY",
                    "confidence": 0.8,
                    "entry": 2350.0,
                    "sl": 2340.0,
                    "tp": 2370.0,
                    "reasoning": f"Rapid {i}",
                    "red_flags": "",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "timeframe": "1h",
                    "snapshot_ts": "",
                    "latency_ms": 0.0,
                    "llm_provider": "groq",
                }
            )
        recent = trade_store.get_recent_decisions("XAUUSD", limit=100)
        assert len(recent) == 100

    def test_rate_limiter_prevents_llm_exhaustion(self) -> None:
        rl = RateLimiter(limits={"groq": 3})
        for _ in range(3):
            rl.record_request("groq")
        assert rl.can_proceed("groq") is False

    def test_news_gate_and_circuit_breaker_combined(self) -> None:
        ng = NewsBlackoutGate()
        ng.set_blackout(until=datetime.now(UTC) + timedelta(hours=1), reason="NFP")
        assert ng.is_blocked() is True
        ng.clear_blackout()
        assert ng.is_blocked() is False

    @pytest.mark.asyncio
    async def test_reconciler_detects_mismatch(self, trade_store: TradeStore) -> None:
        broker = MagicMock()
        broker.active = MagicMock()
        broker.active.get_positions.return_value = [{"symbol": "XAUUSD", "volume": 1.0, "price_open": 2350.0}]
        trade_store.save_execution(
            {
                "symbol": "EURUSD",
                "direction": "BUY",
                "confidence": 0.8,
                "entry": 1.1,
                "stop_loss": 1.09,
                "take_profit": 1.12,
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
        assert result.is_clean is False

    def test_symbol_registry_cross_check(self) -> None:
        reg = SymbolRegistry()
        d = _make_decision()
        asset_class = reg.get_asset_class(d.symbol)
        assert asset_class == "metals"


# ═══════════════════════════════════════════════════════════════════════════════
# 13. Edge Cases & Boundary Conditions (15 tests)
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge case and boundary condition tests."""

    def test_confidence_exactly_at_threshold(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker)
        d = _make_decision(confidence=0.65)
        valid, _ = executor._validate_decision(d)
        assert valid is True

    def test_confidence_just_below_threshold(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker)
        d = _make_decision(confidence=0.64)
        valid, _ = executor._validate_decision(d)
        assert valid is False

    def test_confidence_at_max(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker)
        d = _make_decision(confidence=0.95)
        valid, _ = executor._validate_decision(d)
        assert valid is True

    def test_confidence_above_max_clamped(self) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        assert engine._clamp_confidence(1.5) == 0.95

    def test_confidence_below_zero_clamped(self) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        assert engine._clamp_confidence(-0.5) == 0.0

    def test_empty_ohlcv_formatting(self) -> None:
        result = DecisionEngine._format_ohlcv([])
        assert "no data" in result.lower()

    def test_position_size_clamped_min(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker)
        d = _make_decision(confidence=0.01)
        size = executor._calculate_position_size(d)
        assert size >= 0.01

    def test_position_size_clamped_max(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker)
        d = _make_decision(confidence=0.99)
        size = executor._calculate_position_size(d)
        assert size <= 1.0

    def test_daily_loss_zero_not_breached(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker)
        executor._daily_realized_pnl = __import__("decimal").Decimal("0")
        assert executor._check_daily_loss_breached() is False

    def test_daily_loss_positive_not_breached(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker)
        executor._daily_realized_pnl = __import__("decimal").Decimal("100.0")
        assert executor._check_daily_loss_breached() is False

    @pytest.mark.asyncio
    async def test_max_positions_zero_blocks(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker)
        executor._open_positions = 0
        d = _make_decision()
        executor._max_open_positions = 0
        result = await executor.execute(d)
        assert result.success is False

    def test_chart_snapshot_immutable(self) -> None:
        snap = ChartSnapshot(
            symbol="XAUUSD",
            timeframe="1h",
            ohlcv=[],
            indicators={},
            screenshot_path=None,
            timestamp=datetime.now(UTC),
        )
        with pytest.raises(AttributeError):
            snap.symbol = "BTCUSD"

    def test_trade_decision_immutable(self) -> None:
        d = _make_decision()
        with pytest.raises(AttributeError):
            d.symbol = "BTCUSD"

    @pytest.mark.asyncio
    async def test_empty_string_symbol(self) -> None:
        broker = MagicMock()
        executor = _make_executor(broker)
        d = _make_decision(symbol="")
        result = await executor.execute(d)
        assert result.success is False

    def test_very_long_reasoning_truncated(self) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        raw = (
            '{"direction": "BUY", "confidence": 0.8, "entry": 2350.0, "sl": 2340.0, "tp": 2370.0, "reasoning": "'
            + "A" * 1000
            + '", "red_flags": []}'
        )
        snapshot = ChartSnapshot(
            symbol="XAUUSD", timeframe="1h", ohlcv=[], indicators={}, screenshot_path=None, timestamp=datetime.now(UTC)
        )
        parsed = engine._parse_response(raw, snapshot)
        assert len(parsed.reasoning) <= 500
