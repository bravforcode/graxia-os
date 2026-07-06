"""Integration tests for the autonomous trading loop.

Tests real code paths with mocked external dependencies (MT5, LLM APIs).
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from graxia.packages.quant_os.autonomous.chart_monitor import ChartSnapshot
from graxia.packages.quant_os.autonomous.decision_engine import DecisionEngine, TradeDecision
from graxia.packages.quant_os.autonomous.orchestrator import AutonomousOrchestrator
from graxia.packages.quant_os.autonomous.order_executor import OrderExecutor
from graxia.packages.quant_os.autonomous.rate_limiter import RateLimiter
from graxia.packages.quant_os.autonomous.symbol_registry import SymbolRegistry
from graxia.packages.quant_os.core.enums import SignalType
from graxia.packages.quant_os.execution.adapters.base import AccountInfo

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_broker_manager() -> MagicMock:
    broker = MagicMock()
    broker.active = MagicMock()
    broker.active.get_account_info.return_value = AccountInfo(
        equity=10000.0, cash=8000.0, margin_used=2000.0, margin_available=8000.0
    )
    broker.active.get_positions.return_value = []
    broker.active.submit_order.return_value = MagicMock(
        status=MagicMock(value="FILLED"),
        broker_id="MT5-123",
        error=None,
        filled_quantity=1.0,
        avg_price=2350.0,
    )
    return broker


@pytest.fixture
def mock_risk_engine() -> MagicMock:
    risk = MagicMock()
    risk.evaluate.return_value = MagicMock(approved=True, reason="")
    return risk


@pytest.fixture
def mock_kill_switch() -> MagicMock:
    ks = MagicMock()
    ks.is_active.return_value = False
    ks.is_triggered = False
    ks.get_status.return_value = {}
    return ks


@pytest.fixture
def make_snapshot() -> ChartSnapshot:
    return ChartSnapshot(
        symbol="XAUUSD",
        timeframe="1h",
        ohlcv=[],
        indicators={"RSI": 65.0, "EMA_20": 2348.5},
        screenshot_path=None,
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def make_buy_decision() -> TradeDecision:
    return TradeDecision(
        symbol="XAUUSD",
        direction=SignalType.BUY,
        confidence=0.82,
        entry=2350.0,
        stop_loss=2340.0,
        take_profit=2370.0,
        reasoning="Strong bullish momentum",
        red_flags=(),
        timestamp=datetime.now(UTC),
        timeframe="1h",
    )


@pytest.fixture
def make_sell_decision() -> TradeDecision:
    return TradeDecision(
        symbol="XAUUSD",
        direction=SignalType.SELL,
        confidence=0.78,
        entry=2350.0,
        stop_loss=2360.0,
        take_profit=2330.0,
        reasoning="Bearish rejection at resistance",
        red_flags=(),
        timestamp=datetime.now(UTC),
        timeframe="1h",
    )


@pytest.fixture
def make_executor(
    mock_broker_manager: MagicMock,
    mock_risk_engine: MagicMock,
    mock_kill_switch: MagicMock,
) -> OrderExecutor:
    return OrderExecutor(
        broker_manager=mock_broker_manager,
        risk_engine=mock_risk_engine,
        kill_switch=mock_kill_switch,
        mode="paper",
    )


# ── MT5 Integration ──────────────────────────────────────────────────────────


class TestMT5Integration:
    """Integration tests for MT5 connection in autonomous loop."""

    def test_order_executor_connects_to_mt5(
        self, mock_broker_manager: MagicMock, mock_risk_engine: MagicMock, mock_kill_switch: MagicMock
    ) -> None:
        executor = OrderExecutor(
            broker_manager=mock_broker_manager,
            risk_engine=mock_risk_engine,
            kill_switch=mock_kill_switch,
            mode="paper",
        )
        assert executor._broker_manager is mock_broker_manager
        assert executor._broker_manager.active is not None

    def test_order_executor_fetches_account_state(self, make_executor: OrderExecutor) -> None:
        result = make_executor._fetch_account_state()
        account, portfolio = result
        assert account.equity == 10000.0
        assert account.balance == 8000.0
        assert account.free_margin == 8000.0
        assert account.margin_level_pct == pytest.approx(500.0)

    @pytest.mark.asyncio
    async def test_order_executor_places_order(
        self,
        make_executor: OrderExecutor,
        make_buy_decision: TradeDecision,
        mock_broker_manager: MagicMock,
    ) -> None:
        result = await make_executor.execute(make_buy_decision)
        assert result.success is True
        assert result.order_id.startswith("auto-")
        assert result.filled_quantity == 1.0
        assert result.avg_price == 2350.0
        mock_broker_manager.active.submit_order.assert_called_once()

    def test_orchestrator_creates_broker_manager(self) -> None:
        from graxia.packages.quant_os.core.enums import TradingMode

        orch = AutonomousOrchestrator.__new__(AutonomousOrchestrator)
        orch._trading_mode = MagicMock(value="paper")
        orch._kill_switch = MagicMock()
        orch._kill_switch.is_triggered = False
        orch._circuit_breaker = MagicMock()
        orch._circuit_breaker.is_blocked = False
        orch._news_gate = MagicMock()
        orch._news_gate.is_blocked.return_value = False
        orch._symbol_registry = SymbolRegistry()
        orch._chart_monitor = MagicMock()
        orch._decision_engine = MagicMock()
        orch._notifier = MagicMock()
        orch._trade_store = MagicMock()

        with (
            patch.object(TradingMode, "LIVE", TradingMode.LIVE_MICRO, create=True),
            patch("graxia.packages.quant_os.execution.adapters.manager.BrokerManager") as MockManager,
        ):
            MockManager.return_value = MagicMock()
            manager = orch._create_broker_manager()
            assert manager is not None

    def test_broker_account_info_fallback_on_error(self, make_executor: OrderExecutor) -> None:
        make_executor._broker_manager.active.get_account_info.side_effect = RuntimeError("MT5 down")
        account, portfolio = make_executor._fetch_account_state()
        assert account.equity == 100000.0
        assert portfolio.total_exposure_pct == 0.0


# ── LLM Integration ──────────────────────────────────────────────────────────


class TestLLMIntegration:
    """Integration tests for LLM connection in autonomous loop."""

    @pytest.mark.asyncio
    async def test_decision_engine_calls_llm(self, make_snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        llm_response = json.dumps(
            {
                "direction": "BUY",
                "confidence": 0.82,
                "entry": 2350.0,
                "sl": 2340.0,
                "tp": 2370.0,
                "reasoning": "Strong momentum",
                "red_flags": [],
            }
        )

        mock_provider = MagicMock(name="groq")
        mock_router = AsyncMock()
        mock_router._call_llm_chain = AsyncMock(return_value=(llm_response, 150.0, mock_provider))

        with patch("graxia.packages.quant_os.autonomous.decision_engine.get_router", return_value=mock_router):
            decision = await engine.analyze(make_snapshot)

        assert decision.direction == SignalType.BUY
        assert decision.confidence == pytest.approx(0.82)
        assert decision.entry == 2350.0
        assert decision.stop_loss == 2340.0
        assert decision.take_profit == 2370.0
        mock_router._call_llm_chain.assert_called_once()

    def test_decision_engine_parses_response(self, make_snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)

        raw = '{"direction": "SELL", "confidence": 0.75, "entry": 2355.0, "sl": 2365.0, "tp": 2335.0, "reasoning": "Bearish", "red_flags": ["low_volume"]}'
        parsed = engine._parse_response(raw, make_snapshot)

        assert parsed.direction == SignalType.SELL
        assert parsed.confidence == pytest.approx(0.75)
        assert parsed.red_flags == ("low_volume",)

    @pytest.mark.asyncio
    async def test_decision_engine_handles_timeout(self, make_snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        mock_router = AsyncMock()
        mock_router._call_llm_chain = AsyncMock(side_effect=asyncio.TimeoutError)

        with patch("graxia.packages.quant_os.autonomous.decision_engine.get_router", return_value=mock_router):
            decision = await engine.analyze(make_snapshot)

        assert decision.direction == SignalType.NO_TRADE
        assert "timed out" in decision.reasoning.lower() or "cooldown" in decision.reasoning.lower()

    def test_decision_engine_handles_invalid_json(self, make_snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)

        parsed = engine._parse_response("this is not json at all", make_snapshot)
        assert parsed.direction == SignalType.NO_TRADE

    def test_decision_engine_handles_markdown_fenced_json(self, make_snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)

        raw = '```json\n{"direction": "BUY", "confidence": 0.88, "entry": 2350.0, "sl": 2340.0, "tp": 2370.0, "reasoning": "Test", "red_flags": []}\n```'
        parsed = engine._parse_response(raw, make_snapshot)

        assert parsed.direction == SignalType.BUY
        assert parsed.confidence == pytest.approx(0.88)

    def test_rate_limiter_enforces_limits(self) -> None:
        limiter = RateLimiter(limits={"groq": 2})

        assert limiter.can_proceed("groq") is True
        limiter.record_request("groq")
        assert limiter.can_proceed("groq") is True
        limiter.record_request("groq")
        assert limiter.can_proceed("groq") is False

    def test_rate_limiter_unknown_provider_gets_fallback(self) -> None:
        limiter = RateLimiter(limits={})
        assert limiter.can_proceed("unknown_provider") is True

    def test_rate_limiter_get_wait_time(self) -> None:
        limiter = RateLimiter(limits={"groq": 1})
        limiter.record_request("groq")
        wait = limiter.get_wait_time("groq")
        assert wait > 0.0

    def test_rate_limiter_status(self) -> None:
        limiter = RateLimiter(limits={"groq": 100})
        status = limiter.get_status()
        assert "groq" in status
        assert status["groq"]["capacity"] == 100.0


# ── End-to-End Flow ──────────────────────────────────────────────────────────


class TestEndToEnd:
    """End-to-end integration tests."""

    @pytest.mark.asyncio
    async def test_snapshot_to_decision_flow(self, make_snapshot: ChartSnapshot) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        llm_response = json.dumps(
            {
                "direction": "BUY",
                "confidence": 0.85,
                "entry": 2350.0,
                "sl": 2340.0,
                "tp": 2370.0,
                "reasoning": "Bullish confluence",
                "red_flags": [],
            }
        )

        mock_provider = MagicMock(name="groq")
        mock_router = AsyncMock()
        mock_router._call_llm_chain = AsyncMock(return_value=(llm_response, 200.0, mock_provider))

        with patch("graxia.packages.quant_os.autonomous.decision_engine.get_router", return_value=mock_router):
            decision = await engine.analyze(make_snapshot)

        assert decision.direction == SignalType.BUY
        assert decision.symbol == "XAUUSD"
        assert decision.timeframe == "1h"
        assert decision.entry > 0
        assert decision.stop_loss > 0
        assert decision.take_profit > 0

    @pytest.mark.asyncio
    async def test_decision_to_execution_flow(
        self,
        make_executor: OrderExecutor,
        make_buy_decision: TradeDecision,
    ) -> None:
        result = await make_executor.execute(make_buy_decision)
        assert result.success is True
        assert result.order_id != ""
        assert make_executor._daily_trades == 1
        assert make_executor._open_positions == 1

    @pytest.mark.asyncio
    async def test_full_loop_iteration(
        self,
        make_snapshot: ChartSnapshot,
        mock_broker_manager: MagicMock,
        mock_risk_engine: MagicMock,
        mock_kill_switch: MagicMock,
    ) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        executor = OrderExecutor(
            broker_manager=mock_broker_manager,
            risk_engine=mock_risk_engine,
            kill_switch=mock_kill_switch,
            mode="paper",
        )

        llm_response = json.dumps(
            {
                "direction": "BUY",
                "confidence": 0.88,
                "entry": 2350.0,
                "sl": 2340.0,
                "tp": 2370.0,
                "reasoning": "Full loop test",
                "red_flags": [],
            }
        )

        mock_provider = MagicMock(name="groq")
        mock_router = AsyncMock()
        mock_router._call_llm_chain = AsyncMock(return_value=(llm_response, 100.0, mock_provider))

        with patch("graxia.packages.quant_os.autonomous.decision_engine.get_router", return_value=mock_router):
            decision = await engine.analyze(make_snapshot)

        assert decision.direction == SignalType.BUY

        exec_result = await executor.execute(decision)
        assert exec_result.success is True
        assert exec_result.filled_quantity > 0

        stats = executor.get_daily_stats()
        assert stats["trades_today"] == 1

    @pytest.mark.asyncio
    async def test_full_loop_rejects_low_confidence(
        self,
        make_snapshot: ChartSnapshot,
        mock_broker_manager: MagicMock,
        mock_risk_engine: MagicMock,
        mock_kill_switch: MagicMock,
    ) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        executor = OrderExecutor(
            broker_manager=mock_broker_manager,
            risk_engine=mock_risk_engine,
            kill_switch=mock_kill_switch,
            mode="paper",
        )

        llm_response = json.dumps(
            {
                "direction": "BUY",
                "confidence": 0.30,
                "entry": 2350.0,
                "sl": 2340.0,
                "tp": 2370.0,
                "reasoning": "Uncertain",
                "red_flags": [],
            }
        )

        mock_provider = MagicMock(name="groq")
        mock_router = AsyncMock()
        mock_router._call_llm_chain = AsyncMock(return_value=(llm_response, 100.0, mock_provider))

        with patch("graxia.packages.quant_os.autonomous.decision_engine.get_router", return_value=mock_router):
            decision = await engine.analyze(make_snapshot)

        exec_result = await executor.execute(decision)
        assert exec_result.success is False
        assert "no_trade" in exec_result.error.lower() or "non-trade" in exec_result.error.lower()

    @pytest.mark.asyncio
    async def test_full_loop_kill_switch_blocks(
        self,
        make_snapshot: ChartSnapshot,
        mock_broker_manager: MagicMock,
        mock_risk_engine: MagicMock,
    ) -> None:
        kill_switch = MagicMock()
        kill_switch.is_active.return_value = True
        kill_switch.is_triggered = True
        kill_switch.get_status.return_value = {"reason": "manual"}

        executor = OrderExecutor(
            broker_manager=mock_broker_manager,
            risk_engine=mock_risk_engine,
            kill_switch=kill_switch,
            mode="paper",
        )

        decision = TradeDecision(
            symbol="XAUUSD",
            direction=SignalType.BUY,
            confidence=0.85,
            entry=2350.0,
            stop_loss=2340.0,
            take_profit=2370.0,
            reasoning="Test",
            red_flags=(),
            timestamp=datetime.now(UTC),
        )

        result = await executor.execute(decision)
        assert result.success is False
        assert "kill switch" in result.error.lower()

    @pytest.mark.asyncio
    async def test_full_loop_paper_mode_execution_audit_trail(
        self,
        make_snapshot: ChartSnapshot,
        mock_broker_manager: MagicMock,
        mock_risk_engine: MagicMock,
        mock_kill_switch: MagicMock,
    ) -> None:
        engine = DecisionEngine(min_confidence=0.65)
        executor = OrderExecutor(
            broker_manager=mock_broker_manager,
            risk_engine=mock_risk_engine,
            kill_switch=mock_kill_switch,
            mode="paper",
        )

        llm_response = json.dumps(
            {
                "direction": "SELL",
                "confidence": 0.78,
                "entry": 2355.0,
                "sl": 2365.0,
                "tp": 2335.0,
                "reasoning": "Audit trail test",
                "red_flags": [],
            }
        )

        mock_provider = MagicMock(name="groq")
        mock_router = AsyncMock()
        mock_router._call_llm_chain = AsyncMock(return_value=(llm_response, 100.0, mock_provider))

        with patch("graxia.packages.quant_os.autonomous.decision_engine.get_router", return_value=mock_router):
            decision = await engine.analyze(make_snapshot)

        exec_result = await executor.execute(decision)
        assert exec_result.success is True

        log = executor.get_execution_log()
        assert len(log) == 1
        assert log[0]["symbol"] == "XAUUSD"
        assert log[0]["direction"] == "SELL"
        assert log[0]["success"] is True
