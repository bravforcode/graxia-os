"""Tests for Phase 3: Order State Machine and Trade Ledger"""

import tempfile
from datetime import datetime
from decimal import Decimal

import pytest

from graxia.packages.quant_os.core.exceptions import OrderStateError
from graxia.packages.quant_os.execution.order_state_machine import (
    OrderState,
    OrderStateMachine,
)
from graxia.packages.quant_os.execution.trade_ledger import TradeLedger, TradeRecord


def _make_lifecycle(order_id: str = "test-001") -> OrderStateMachine:
    return OrderStateMachine(order_id=order_id)


# --- Happy path: full lifecycle ---


class TestFullLifecycle:
    def test_signal_created_transitions_to_risk_checked(self):
        lc = _make_lifecycle()
        assert lc.state == OrderState.SIGNAL_CREATED
        lc.transition(OrderState.RISK_CHECKED, "Risk gate passed")
        assert lc.state == OrderState.RISK_CHECKED

    def test_risk_checked_to_prechecked(self):
        lc = _make_lifecycle()
        lc.transition(OrderState.RISK_CHECKED)
        lc.transition(OrderState.ORDER_PRECHECKED, "Precheck OK")
        assert lc.state == OrderState.ORDER_PRECHECKED

    def test_prechecked_to_submitted(self):
        lc = _make_lifecycle()
        lc.transition(OrderState.RISK_CHECKED)
        lc.transition(OrderState.ORDER_PRECHECKED)
        lc.transition(OrderState.ORDER_SUBMITTED, "Submitted to broker")
        assert lc.state == OrderState.ORDER_SUBMITTED

    def test_submitted_to_acknowledged(self):
        lc = _make_lifecycle()
        for s in (OrderState.RISK_CHECKED, OrderState.ORDER_PRECHECKED, OrderState.ORDER_SUBMITTED):
            lc.transition(s)
        lc.transition(OrderState.ORDER_ACKNOWLEDGED, "Broker ack")
        assert lc.state == OrderState.ORDER_ACKNOWLEDGED

    def test_acknowledged_to_filled(self):
        lc = _make_lifecycle()
        for s in (
            OrderState.RISK_CHECKED,
            OrderState.ORDER_PRECHECKED,
            OrderState.ORDER_SUBMITTED,
            OrderState.ORDER_ACKNOWLEDGED,
        ):
            lc.transition(s)
        lc.transition(OrderState.FILLED, "Full fill")
        assert lc.state == OrderState.FILLED

    def test_filled_to_protective_stops_verified(self):
        lc = _make_lifecycle()
        for s in (
            OrderState.RISK_CHECKED,
            OrderState.ORDER_PRECHECKED,
            OrderState.ORDER_SUBMITTED,
            OrderState.ORDER_ACKNOWLEDGED,
            OrderState.FILLED,
        ):
            lc.transition(s)
        lc.transition(OrderState.PROTECTIVE_STOPS_VERIFIED, "SL/TP placed")
        assert lc.state == OrderState.PROTECTIVE_STOPS_VERIFIED

    def test_protective_to_position_reconciled(self):
        lc = _make_lifecycle()
        for s in (
            OrderState.RISK_CHECKED,
            OrderState.ORDER_PRECHECKED,
            OrderState.ORDER_SUBMITTED,
            OrderState.ORDER_ACKNOWLEDGED,
            OrderState.FILLED,
            OrderState.PROTECTIVE_STOPS_VERIFIED,
        ):
            lc.transition(s)
        lc.transition(OrderState.POSITION_RECONCILED, "Positions match")
        assert lc.state == OrderState.POSITION_RECONCILED

    def test_position_reconciled_to_closed(self):
        lc = _make_lifecycle()
        for s in (
            OrderState.RISK_CHECKED,
            OrderState.ORDER_PRECHECKED,
            OrderState.ORDER_SUBMITTED,
            OrderState.ORDER_ACKNOWLEDGED,
            OrderState.FILLED,
            OrderState.PROTECTIVE_STOPS_VERIFIED,
            OrderState.POSITION_RECONCILED,
        ):
            lc.transition(s)
        lc.transition(OrderState.CLOSED, "Position closed")
        assert lc.state == OrderState.CLOSED

    def test_closed_to_deal_reconciled(self):
        lc = _make_lifecycle()
        for s in (
            OrderState.RISK_CHECKED,
            OrderState.ORDER_PRECHECKED,
            OrderState.ORDER_SUBMITTED,
            OrderState.ORDER_ACKNOWLEDGED,
            OrderState.FILLED,
            OrderState.PROTECTIVE_STOPS_VERIFIED,
            OrderState.POSITION_RECONCILED,
            OrderState.CLOSED,
        ):
            lc.transition(s)
        lc.transition(OrderState.DEAL_RECONCILED, "Deal reconciled")
        assert lc.state == OrderState.DEAL_RECONCILED

    def test_deal_reconciled_to_audited(self):
        lc = _make_lifecycle()
        for s in (
            OrderState.RISK_CHECKED,
            OrderState.ORDER_PRECHECKED,
            OrderState.ORDER_SUBMITTED,
            OrderState.ORDER_ACKNOWLEDGED,
            OrderState.FILLED,
            OrderState.PROTECTIVE_STOPS_VERIFIED,
            OrderState.POSITION_RECONCILED,
            OrderState.CLOSED,
            OrderState.DEAL_RECONCILED,
        ):
            lc.transition(s)
        lc.transition(OrderState.AUDITED, "Audit passed")
        assert lc.state == OrderState.AUDITED
        assert lc.is_terminal()


# --- Invalid transitions ---


class TestInvalidTransitions:
    def test_invalid_transition_raises(self):
        lc = _make_lifecycle()
        with pytest.raises(OrderStateError):
            lc.transition(OrderState.FILLED, "Skip to filled")

    def test_terminal_states_no_transition(self):
        for terminal in (OrderState.REJECTED, OrderState.EXPIRED, OrderState.AUDITED, OrderState.CRITICAL_INCIDENT):
            lc = _make_lifecycle()
            # Get to a state that can reach terminal
            if terminal == OrderState.REJECTED:
                lc.transition(OrderState.RISK_CHECKED)
                lc.transition(terminal, "Rejected")
            elif terminal == OrderState.EXPIRED:
                lc.transition(OrderState.RISK_CHECKED)
                lc.transition(OrderState.ORDER_PRECHECKED)
                lc.transition(OrderState.ORDER_SUBMITTED)
                lc.transition(terminal, "Expired")
            elif terminal == OrderState.AUDITED:
                for s in (
                    OrderState.RISK_CHECKED,
                    OrderState.ORDER_PRECHECKED,
                    OrderState.ORDER_SUBMITTED,
                    OrderState.ORDER_ACKNOWLEDGED,
                    OrderState.FILLED,
                    OrderState.PROTECTIVE_STOPS_VERIFIED,
                    OrderState.POSITION_RECONCILED,
                    OrderState.CLOSED,
                    OrderState.DEAL_RECONCILED,
                ):
                    lc.transition(s)
                lc.transition(terminal, "Audited")
            elif terminal == OrderState.CRITICAL_INCIDENT:
                for s in (
                    OrderState.RISK_CHECKED,
                    OrderState.ORDER_PRECHECKED,
                    OrderState.ORDER_SUBMITTED,
                    OrderState.ORDER_ACKNOWLEDGED,
                    OrderState.FILLED,
                ):
                    lc.transition(s)
                lc.transition(terminal, "Critical")

            assert lc.is_terminal()
            with pytest.raises(OrderStateError):
                lc.transition(OrderState.RISK_CHECKED, "Should fail")


# --- Critical incident ---


class TestCriticalIncident:
    def test_critical_incident_is_terminal(self):
        lc = _make_lifecycle()
        for s in (
            OrderState.RISK_CHECKED,
            OrderState.ORDER_PRECHECKED,
            OrderState.ORDER_SUBMITTED,
            OrderState.ORDER_ACKNOWLEDGED,
            OrderState.FILLED,
        ):
            lc.transition(s)
        lc.transition(OrderState.CRITICAL_INCIDENT, "Protective stops failed")
        assert lc.is_terminal()

    def test_critical_from_early_state(self):
        lc = _make_lifecycle()
        lc.transition(OrderState.RISK_CHECKED)
        lc.transition(OrderState.CRITICAL_INCIDENT, "Early failure")
        assert lc.state == OrderState.CRITICAL_INCIDENT
        assert lc.is_terminal()

    def test_history_recorded(self):
        lc = _make_lifecycle()
        lc.transition(OrderState.RISK_CHECKED, "ok")
        # ponytail: _history stores OrderState enums; initial state counts as entry 0
        assert len(lc._history) == 2  # initial + 1 transition
        assert lc._history[0] == OrderState.SIGNAL_CREATED
        assert lc._history[1] == OrderState.RISK_CHECKED


# --- Trade Ledger ---


class TestTradeLedger:
    def _make_record(self, trade_id: str = "t-001") -> TradeRecord:
        return TradeRecord(
            trade_id=trade_id,
            order_id="o-001",
            symbol="XAUUSD",
            side="BUY",
            entry_price=Decimal("2350.50"),
            exit_price=Decimal("2365.00"),
            volume=Decimal("0.1"),
            entry_time=datetime(2026, 6, 20, 10, 0, 0),
            exit_time=datetime(2026, 6, 20, 14, 30, 0),
            pnl=Decimal("145.00"),
            pnl_pct=Decimal("0.62"),
            fees=Decimal("3.50"),
            spread_cost=Decimal("1.20"),
            slippage_cost=Decimal("0.80"),
            close_reason="TAKE_PROFIT",
            execution_quality="BAR_ONLY",
            strategy_id="mtm",
            contract_snapshot_id="snap-001",
            risk_policy_version="1.0",
            dataset_manifest_id="manifest-001",
            cost_scenario="base",
            git_commit="abc123",
        )

    def test_trade_ledger_record_and_retrieve(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = TradeLedger(ledger_dir=tmpdir)
            rec = self._make_record()
            ledger.record_trade(rec)

            trades = ledger.get_trades()
            assert len(trades) == 1
            assert trades[0].trade_id == "t-001"
            assert trades[0].entry_price == Decimal("2350.50")
            assert trades[0].symbol == "XAUUSD"

    def test_trade_ledger_hash_deterministic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = TradeLedger(ledger_dir=tmpdir)
            rec = self._make_record()
            ledger.record_trade(rec)

            h1 = ledger.ledger_hash()
            h2 = ledger.ledger_hash()
            assert h1 == h2
            assert len(h1) == 64  # SHA-256 hex

    def test_trade_ledger_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = TradeLedger(ledger_dir=tmpdir)
            rec1 = self._make_record("t-001")
            rec2 = self._make_record("t-002")
            rec2.pnl = Decimal("-50.00")
            rec2.pnl_pct = Decimal("-0.21")
            ledger.record_trade(rec1)
            ledger.record_trade(rec2)

            s = ledger.get_summary()
            # ponytail: summary is intentionally simple — total_trades, total_pnl, total_fees
            assert s["total_trades"] == 2
            assert Decimal(s["total_pnl"]) == Decimal("95.00")

    def test_trade_ledger_filter_by_symbol(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = TradeLedger(ledger_dir=tmpdir)
            rec_xau = self._make_record("t-001")
            rec_eur = self._make_record("t-002")
            rec_eur.symbol = "EURUSD"
            ledger.record_trade(rec_xau)
            ledger.record_trade(rec_eur)

            xau_only = ledger.get_trades(symbol="XAUUSD")
            assert len(xau_only) == 1
            assert xau_only[0].symbol == "XAUUSD"


# --- Execution safety ---


class TestExecutionSafety:
    def test_no_order_send_in_execution(self):
        """execution/ module has no order_send in new files."""
        import importlib

        import graxia.packages.quant_os.execution.order_state_machine as osm
        import graxia.packages.quant_os.execution.trade_ledger as tl

        for mod in (osm, tl):
            src = importlib.util.find_spec(mod.__name__).origin
            content = open(src).read()
            assert "order_send" not in content, f"order_send found in {mod.__name__}"
            assert "order_modify" not in content, f"order_modify found in {mod.__name__}"
            assert "order_close" not in content, f"order_close found in {mod.__name__}"
