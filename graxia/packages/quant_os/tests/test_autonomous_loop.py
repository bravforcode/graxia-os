"""Integration tests for the autonomous trading loop.

Verifies component instantiation, wiring, and basic safety flows.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from graxia.packages.quant_os.autonomous.chart_monitor import ChartSnapshot
from graxia.packages.quant_os.autonomous.config import (
    SYMBOLS,
    TIMEFRAMES,
    TRADING_MODE,
)
from graxia.packages.quant_os.autonomous.decision_engine import TradeDecision
from graxia.packages.quant_os.autonomous.live_approval import (
    ApprovalAction,
    LiveApprovalGate,
)
from graxia.packages.quant_os.autonomous.orchestrator import SystemHealth
from graxia.packages.quant_os.autonomous.order_executor import OrderExecutor
from graxia.packages.quant_os.core.enums import SignalType

# ── ChartSnapshot ──────────────────────────────────────────────────


class TestChartSnapshot:
    def test_creation(self):
        snap = ChartSnapshot(
            symbol="XAUUSD",
            timeframe="1h",
            ohlcv=[],
            indicators={},
            screenshot_path=None,
            timestamp=datetime.now(UTC),
        )
        assert snap.symbol == "XAUUSD"
        assert snap.timeframe == "1h"

    def test_frozen(self):
        snap = ChartSnapshot(
            symbol="BTCUSD",
            timeframe="15m",
            ohlcv=[],
            indicators={},
            screenshot_path=None,
            timestamp=datetime.now(UTC),
        )
        with pytest.raises(AttributeError):
            snap.symbol = "ETHUSD"


# ── TradeDecision ──────────────────────────────────────────────────


class TestTradeDecision:
    def test_buy_decision(self):
        d = TradeDecision(
            symbol="XAUUSD",
            direction=SignalType.BUY,
            confidence=0.82,
            entry=2350.0,
            stop_loss=2340.0,
            take_profit=2370.0,
            reasoning="Strong bullish momentum",
            red_flags=(),
            timestamp=datetime.now(UTC),
        )
        assert d.direction == SignalType.BUY
        assert d.confidence == 0.82

    def test_no_trade_decision(self):
        d = TradeDecision(
            symbol="XAUUSD",
            direction=SignalType.NO_TRADE,
            confidence=0.3,
            entry=0.0,
            stop_loss=0.0,
            take_profit=0.0,
            reasoning="Unclear trend",
            red_flags=("low_volume",),
            timestamp=datetime.now(UTC),
        )
        assert d.direction == SignalType.NO_TRADE


# ── OrderExecutor ──────────────────────────────────────────────────


class TestOrderExecutor:
    def _make_executor(self, mode="paper"):
        broker = MagicMock()
        broker.active = MagicMock()
        risk_engine = MagicMock()
        risk_engine.evaluate.return_value = MagicMock(approved=True, approved_quantity=1.0)
        kill_switch = MagicMock()
        kill_switch.is_active.return_value = False
        kill_switch.is_triggered = False
        return OrderExecutor(
            broker_manager=broker,
            risk_engine=risk_engine,
            kill_switch=kill_switch,
            mode=mode,
        )

    def _make_decision(self, direction=SignalType.BUY, confidence=0.8):
        return TradeDecision(
            symbol="XAUUSD",
            direction=direction,
            confidence=confidence,
            entry=2350.0,
            stop_loss=2340.0,
            take_profit=2370.0,
            reasoning="Test",
            red_flags=(),
            timestamp=datetime.now(UTC),
        )

    @pytest.mark.asyncio
    async def test_kill_switch_blocks(self):
        executor = self._make_executor()
        executor._kill_switch.is_triggered = True
        result = await executor.execute(self._make_decision())
        assert not result.success
        assert "Kill switch" in result.error

    @pytest.mark.asyncio
    async def test_no_trade_rejected(self):
        executor = self._make_executor()
        result = await executor.execute(self._make_decision(direction=SignalType.NO_TRADE))
        assert not result.success

    @pytest.mark.asyncio
    async def test_low_confidence_rejected(self):
        executor = self._make_executor()
        result = await executor.execute(self._make_decision(confidence=0.3))
        assert not result.success
        assert "below minimum" in result.error

    @pytest.mark.asyncio
    async def test_live_mode_requires_approval(self):
        executor = self._make_executor(mode="live")
        account_info = MagicMock()
        account_info.equity = 10000.0
        account_info.cash = 10000.0
        account_info.margin_used = 0.0
        account_info.margin_available = 10000.0
        executor._broker_manager.active.get_account_info.return_value = account_info
        result = await executor.execute(self._make_decision())
        assert not result.success
        assert result.approval_required
        assert "LIVE_APPROVAL" in result.error

    def test_daily_stats(self):
        executor = self._make_executor()
        stats = executor.get_daily_stats()
        assert stats["trades_today"] == 0
        assert stats["mode"] == "paper"


# ── SystemHealth ───────────────────────────────────────────────────


class TestSystemHealth:
    def test_defaults(self):
        h = SystemHealth()
        assert h.total_decisions == 0
        assert h.total_trades == 0
        assert h.is_running is False
        assert h.kill_switch_active is False


# ── Config ─────────────────────────────────────────────────────────


class TestConfig:
    def test_symbols_loaded(self):
        assert len(SYMBOLS) > 0
        assert "XAUUSD" in SYMBOLS

    def test_timeframes_loaded(self):
        assert len(TIMEFRAMES) > 0

    def test_trading_mode(self):
        assert TRADING_MODE in ("paper", "live")


# ── LiveApprovalGate ───────────────────────────────────────────────


class TestLiveApprovalGate:
    @pytest.mark.asyncio
    async def test_no_config_returns_reject(self):
        gate = LiveApprovalGate(bot_token="", chat_id="")
        decision = TradeDecision(
            symbol="XAUUSD",
            direction=SignalType.BUY,
            confidence=0.8,
            entry=2350.0,
            stop_loss=2340.0,
            take_profit=2370.0,
            reasoning="Test",
            red_flags=(),
            timestamp=datetime.now(UTC),
        )
        result = await gate.request_approval(decision)
        assert not result.approved
        assert result.action == ApprovalAction.REJECT

    def test_approve_action(self):
        result = LiveApprovalGate._action_to_result(ApprovalAction.APPROVE)
        assert result.approved
        assert result.size_multiplier == 1.0

    def test_half_action(self):
        result = LiveApprovalGate._action_to_result(ApprovalAction.HALF)
        assert result.approved
        assert result.size_multiplier == 0.5

    def test_reject_action(self):
        result = LiveApprovalGate._action_to_result(ApprovalAction.REJECT)
        assert not result.approved

    def test_skip_action(self):
        result = LiveApprovalGate._action_to_result(ApprovalAction.SKIP)
        assert not result.approved

    def test_timeout_action(self):
        result = LiveApprovalGate._action_to_result(ApprovalAction.TIMEOUT)
        assert not result.approved
