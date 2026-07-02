"""
Tests for TradingLoop, PositionManager, and OMS state machine integration.

Validates the complete signal → order → fill → position lifecycle.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from graxia.packages.quant_os.core.enums import SignalType, TradingMode
from graxia.packages.quant_os.core.events import (
    FillEvent,
    KillSwitchEvent,
    OrderEvent,
    SignalEvent,
    TradeClosedEvent,
)
from graxia.packages.quant_os.core.event_bus import EventBus
from graxia.packages.quant_os.core.trading_loop import (
    PaperExecutor,
    TradingLoop,
    _symbol_to_asset_class,
)
from graxia.packages.quant_os.core.position_manager import Position, PositionManager
from graxia.packages.quant_os.execution.order_state_machine import (
    OrderStateMachine,
    TRANSITIONS,
)
from graxia.packages.quant_os.execution.adapters.base import OrderStatus


# ── Helpers ───────────────────────────────────────────────────────────────

def _make_signal(
    symbol: str = "XAUUSD",
    signal_type: SignalType = SignalType.BUY,
    confidence: float = 0.8,
    entry_price: float = 2400.0,
    stop_loss: float = 2390.0,
    take_profit: float = 2430.0,
    source: str = "technical_analyst",
    final: bool = True,
    approved_quantity: float = 0.1,
) -> SignalEvent:
    return SignalEvent(
        symbol=symbol,
        signal_type=signal_type,
        confidence=confidence,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        source=source,
        metadata={"final": final, "approved_quantity": approved_quantity},
    )


# ── Symbol → Asset Class ─────────────────────────────────────────────────

class TestSymbolAssetClass:
    def test_xauusd_is_metals(self):
        assert _symbol_to_asset_class("XAUUSD") == "metals"

    def test_eurusd_is_forex(self):
        assert _symbol_to_asset_class("EURUSD") == "forex"

    def test_us30_is_indices(self):
        assert _symbol_to_asset_class("US30") == "indices"

    def test_btcusd_is_crypto(self):
        assert _symbol_to_asset_class("BTCUSD") == "crypto"

    def test_unknown_defaults_to_forex(self):
        assert _symbol_to_asset_class("XYZXYZ") == "forex"


# ── Paper Executor ────────────────────────────────────────────────────────

class TestPaperExecutor:
    def test_buy_fills_above_entry(self):
        pe = PaperExecutor(slippage_pips=0.5)
        fill = pe.submit("XAUUSD", "BUY", 0.1, 2400.0, 2390.0, 2430.0)
        assert fill["fill_price"] > 2400.0
        assert fill["fill_quantity"] == 0.1
        assert fill["commission"] > 0

    def test_sell_fills_below_entry(self):
        pe = PaperExecutor(slippage_pips=0.5)
        fill = pe.submit("XAUUSD", "SELL", 0.1, 2400.0, 2410.0, 2370.0)
        assert fill["fill_price"] < 2400.0

    def test_fills_tracked(self):
        pe = PaperExecutor()
        pe.submit("EURUSD", "BUY", 1.0, 1.1000)
        pe.submit("GBPUSD", "SELL", 0.5, 1.3000)
        assert len(pe.get_fills()) == 2


# ── Trading Loop ──────────────────────────────────────────────────────────

class TestTradingLoop:
    def test_observes_final_signal(self):
        bus = EventBus()
        loop = TradingLoop(bus=bus)
        events = []
        bus.subscribe(FillEvent, lambda e: events.append(e))

        sig = _make_signal()
        loop.observe(sig)
        assert len(events) == 1
        assert isinstance(events[0], FillEvent)

    def test_ignores_non_final_signal(self):
        bus = EventBus()
        loop = TradingLoop(bus=bus)
        events = []
        bus.subscribe(FillEvent, lambda e: events.append(e))

        sig = _make_signal(final=False)
        loop.observe(sig)
        assert len(events) == 0

    def test_ignores_no_trade_signal(self):
        bus = EventBus()
        loop = TradingLoop(bus=bus)
        events = []
        bus.subscribe(FillEvent, lambda e: events.append(e))

        sig = _make_signal(signal_type=SignalType.NO_TRADE)
        loop.observe(sig)
        assert len(events) == 0

    def test_rejects_signal_without_sl(self):
        bus = EventBus()
        loop = TradingLoop(bus=bus)
        events = []
        bus.subscribe(FillEvent, lambda e: events.append(e))

        sig = _make_signal(stop_loss=0)
        loop.observe(sig)
        assert len(events) == 0
        assert loop.get_stats()["total_rejected"] == 1

    def test_rejects_signal_without_quantity(self):
        bus = EventBus()
        loop = TradingLoop(bus=bus)
        events = []
        bus.subscribe(FillEvent, lambda e: events.append(e))

        sig = _make_signal(approved_quantity=0)
        loop.observe(sig)
        assert len(events) == 0

    def test_kill_switch_stops_trading(self):
        bus = EventBus()
        loop = TradingLoop(bus=bus)
        events = []
        bus.subscribe(FillEvent, lambda e: events.append(e))

        kill = KillSwitchEvent(trigger="manual", reason="test")
        loop.on_kill_switch(kill)
        assert loop.get_stats()["kill_switch_active"] is True

        sig = _make_signal()
        loop.observe(sig)
        assert len(events) == 0

    def test_kill_switch_cancels_oms_orders(self):
        bus = EventBus()
        mock_oms = MagicMock()
        mock_oms.cancel_all.return_value = [MagicMock()]
        loop = TradingLoop(bus=bus, oms=mock_oms)

        kill = KillSwitchEvent(trigger="drawdown", reason="15% hit")
        loop.on_kill_switch(kill)
        mock_oms.cancel_all.assert_called_once()

    def test_emits_order_event(self):
        bus = EventBus()
        loop = TradingLoop(bus=bus)
        order_events = []
        bus.subscribe(OrderEvent, lambda e: order_events.append(e))

        sig = _make_signal()
        loop.observe(sig)
        assert len(order_events) == 1
        assert order_events[0].symbol == "XAUUSD"
        assert order_events[0].side == "BUY"

    def test_sell_signal_produces_sell_order(self):
        bus = EventBus()
        loop = TradingLoop(bus=bus)
        order_events = []
        bus.subscribe(OrderEvent, lambda e: order_events.append(e))

        sig = _make_signal(signal_type=SignalType.SELL, stop_loss=2410, take_profit=2370)
        loop.observe(sig)
        assert order_events[0].side == "SELL"

    def test_paper_fill_emits_trade_closed(self):
        bus = EventBus()
        loop = TradingLoop(bus=bus)
        closed = []
        bus.subscribe(TradeClosedEvent, lambda e: closed.append(e))

        sig = _make_signal()
        loop.observe(sig)
        assert len(closed) == 1
        assert closed[0].symbol == "XAUUSD"
        assert closed[0].entry_price == 2400.0

    def test_daily_limit_enforced_micro(self):
        from graxia.packages.quant_os.core.config import QuantConfig

        config = QuantConfig()
        config.trading_mode = TradingMode.LIVE_MICRO
        bus = EventBus()
        loop = TradingLoop(bus=bus, config=config)

        for _ in range(5):
            sig = _make_signal()
            loop.observe(sig)

        assert loop.get_stats()["total_filled"] == 5

        sig = _make_signal()
        loop.observe(sig)
        assert loop.get_stats()["total_rejected"] == 1

    def test_get_stats(self):
        bus = EventBus()
        loop = TradingLoop(bus=bus)
        stats = loop.get_stats()
        assert "kill_switch_active" in stats
        assert "total_filled" in stats
        assert "trading_mode" in stats

    def test_reset(self):
        bus = EventBus()
        loop = TradingLoop(bus=bus)
        loop.observe(_make_signal())
        loop.reset()
        stats = loop.get_stats()
        assert stats["total_filled"] == 0
        assert stats["tracked_orders"] == 0


# ── Position Manager ──────────────────────────────────────────────────────

class TestPositionManager:
    def test_on_fill_opens_position(self):
        bus = EventBus()
        with tempfile.TemporaryDirectory() as tmp:
            pm = PositionManager(bus=bus, data_dir=Path(tmp))
            fill = FillEvent(
                symbol="XAUUSD",
                side="BUY",
                fill_price=2400.0,
                fill_quantity=0.1,
                strategy_id="test",
            )
            pm.on_fill(fill)

            positions = pm.get_positions()
            assert len(positions) == 1
            pos = positions["XAUUSD:BUY"]
            assert pos.symbol == "XAUUSD"
            assert pos.quantity == 0.1
            assert pos.entry_price == 2400.0

    def test_on_fill_increases_position(self):
        bus = EventBus()
        with tempfile.TemporaryDirectory() as tmp:
            pm = PositionManager(bus=bus, data_dir=Path(tmp))
            fill1 = FillEvent(
                symbol="XAUUSD", side="BUY", fill_price=2400.0,
                fill_quantity=0.1, strategy_id="test",
            )
            fill2 = FillEvent(
                symbol="XAUUSD", side="BUY", fill_price=2410.0,
                fill_quantity=0.1, strategy_id="test",
            )
            pm.on_fill(fill1)
            pm.on_fill(fill2)

            pos = pm.get_positions()["XAUUSD:BUY"]
            assert pos.quantity == pytest.approx(0.2, abs=1e-6)
            assert pos.entry_price == pytest.approx(2405.0, abs=0.1)

    def test_on_close_removes_position(self):
        bus = EventBus()
        with tempfile.TemporaryDirectory() as tmp:
            pm = PositionManager(bus=bus, data_dir=Path(tmp))
            fill = FillEvent(
                symbol="XAUUSD", side="BUY", fill_price=2400.0,
                fill_quantity=0.1, strategy_id="test",
            )
            pm.on_fill(fill)
            assert len(pm.get_positions()) == 1

            close = TradeClosedEvent(
                symbol="XAUUSD", side="BUY", entry_price=2400.0,
                exit_price=2430.0, quantity=0.1, pnl=30.0,
                close_reason="TAKE_PROFIT", strategy_id="test",
            )
            pm.on_close(close)
            assert len(pm.get_positions()) == 0
            assert len(pm.get_closed_trades()) == 1

    def test_pnl_calculation(self):
        pos = Position(symbol="XAUUSD", side="BUY", quantity=0.1, entry_price=2400.0)
        pos.update_pnl(2430.0)
        assert pos.unrealized_pnl == pytest.approx(3.0, abs=0.01)

        pos2 = Position(symbol="XAUUSD", side="SELL", quantity=0.1, entry_price=2400.0)
        pos2.update_pnl(2370.0)
        assert pos2.unrealized_pnl == pytest.approx(3.0, abs=0.01)

    def test_update_prices(self):
        with tempfile.TemporaryDirectory() as tmp:
            pm = PositionManager(data_dir=Path(tmp))
            fill = FillEvent(
                symbol="XAUUSD", side="BUY", fill_price=2400.0,
                fill_quantity=0.1, strategy_id="test",
            )
            pm.on_fill(fill)

            pm.update_prices({"XAUUSD": 2430.0})
            pos = pm.get_positions()["XAUUSD:BUY"]
            assert pos.unrealized_pnl == pytest.approx(3.0, abs=0.01)

    def test_exposure_calculation(self):
        with tempfile.TemporaryDirectory() as tmp:
            pm = PositionManager(data_dir=Path(tmp))
            fill1 = FillEvent(
                symbol="XAUUSD", side="BUY", fill_price=2400.0,
                fill_quantity=0.1, strategy_id="test",
            )
            fill2 = FillEvent(
                symbol="EURUSD", side="BUY", fill_price=1.1000,
                fill_quantity=10000, strategy_id="test",
            )
            pm.on_fill(fill1)
            pm.on_fill(fill2)

            total = pm.get_total_exposure()
            assert total == pytest.approx(2400.0 * 0.1 + 1.1000 * 10000, abs=1.0)

    def test_get_position_by_symbol(self):
        with tempfile.TemporaryDirectory() as tmp:
            pm = PositionManager(data_dir=Path(tmp))
            fill = FillEvent(
                symbol="XAUUSD", side="BUY", fill_price=2400.0,
                fill_quantity=0.1, strategy_id="test",
            )
            pm.on_fill(fill)

            pos = pm.get_position("XAUUSD")
            assert pos is not None
            assert pos.symbol == "XAUUSD"

    def test_persistence_across_instances(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pm1 = PositionManager(data_dir=tmp_path)
            fill = FillEvent(
                symbol="XAUUSD", side="BUY", fill_price=2400.0,
                fill_quantity=0.1, strategy_id="test",
            )
            pm1.on_fill(fill)

            pm2 = PositionManager(data_dir=tmp_path)
            assert len(pm2.get_positions()) == 1
            assert pm2.get_positions()["XAUUSD:BUY"].entry_price == 2400.0


# ── Order State Machine Integration ───────────────────────────────────────

class TestOrderStateMachineIntegration:
    def test_valid_transitions(self):
        sm = OrderStateMachine(order_id="test-001", initial=OrderStatus.SIGNAL_CREATED)
        sm.advance(OrderStatus.RISK_CHECKED)
        sm.advance(OrderStatus.ORDER_PRECHECKED)
        sm.advance(OrderStatus.ORDER_SUBMITTED)
        sm.advance(OrderStatus.ORDER_ACKNOWLEDGED)
        sm.advance(OrderStatus.FILLED)
        assert sm.state == OrderStatus.FILLED
        assert len(sm._history) == 6

    def test_invalid_transition_raises(self):
        sm = OrderStateMachine(order_id="test-002", initial=OrderStatus.SIGNAL_CREATED)
        with pytest.raises(Exception):
            sm.advance(OrderStatus.FILLED)  # skip中间 steps

    def test_terminal_states_have_no_outgoing(self):
        for terminal in [
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
            OrderStatus.AUDITED,
            OrderStatus.CRITICAL_INCIDENT,
        ]:
            assert TRANSITIONS[terminal] == set()

    def test_is_terminal(self):
        sm = OrderStateMachine(initial=OrderStatus.REJECTED)
        assert sm.is_terminal() is True

        sm2 = OrderStateMachine(initial=OrderStatus.SIGNAL_CREATED)
        assert sm2.is_terminal() is False
