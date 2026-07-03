"""Phase 3 tests — Execution & Cost Model (25 tests)."""

import importlib
import tempfile
from datetime import datetime
from decimal import Decimal

import pytest

from graxia.packages.quant_os.core.exceptions import OrderStateError
from graxia.packages.quant_os.execution.cost_model import (
    ALL_SCENARIOS,
    BASE,
    STRESS_1,
    STRESS_3,
    TradeCosts,
    calculate_trade_costs,
    run_cost_stress_matrix,
)
from graxia.packages.quant_os.execution.fill_model import (
    FillRequest,
    Side,
    can_fill_on_info_candle,
    check_sl_tp_trigger,
    simulate_entry,
    simulate_exit,
)
from graxia.packages.quant_os.execution.order_state_machine import (
    OrderState,
    OrderStateMachine,
)
from graxia.packages.quant_os.execution.trade_ledger import TradeLedger, TradeRecord

GOLD_BID = Decimal("2330.50")
GOLD_ASK = Decimal("2331.50")
SPREAD = GOLD_ASK - GOLD_BID
SLIPPAGE = Decimal("0.10")
SL = Decimal("2325.00")
TP = Decimal("2340.00")


def _long_request(**overrides):
    defaults = dict(
        side=Side.BUY,
        entry_price=Decimal("2330"),
        stop_loss=SL,
        take_profit=TP,
        slippage_entry=SLIPPAGE,
        slippage_exit=SLIPPAGE,
    )
    defaults.update(overrides)
    return FillRequest(**defaults)


def _short_request(**overrides):
    defaults = dict(
        side=Side.SELL,
        entry_price=Decimal("2330"),
        stop_loss=Decimal("2340"),
        take_profit=Decimal("2320"),
        slippage_entry=SLIPPAGE,
        slippage_exit=SLIPPAGE,
    )
    defaults.update(overrides)
    return FillRequest(**defaults)


def _make_trade_record(trade_id="t-001", **overrides):
    defaults = dict(
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
        execution_quality="CONSERVATIVE_BAR",
        strategy_id="mtm",
        contract_snapshot_id="snap-001",
        risk_policy_version="1.0",
        dataset_manifest_id="manifest-001",
        cost_scenario="base",
        git_commit="abc123",
    )
    defaults.update(overrides)
    return TradeRecord(**defaults)


class TestBidAskEntryExit:
    def test_long_entry_at_ask_plus_slippage(self):
        req = _long_request()
        fill = simulate_entry(req, GOLD_BID, GOLD_ASK, SPREAD)
        assert fill.entry_price == GOLD_ASK + SLIPPAGE

    def test_short_entry_at_bid_minus_slippage(self):
        req = _short_request()
        fill = simulate_entry(req, GOLD_BID, GOLD_ASK, SPREAD)
        assert fill.entry_price == GOLD_BID - SLIPPAGE

    def test_close_long_at_bid_minus_slippage(self):
        price, cost = simulate_exit(Side.BUY, GOLD_BID, GOLD_ASK, SLIPPAGE)
        assert price == GOLD_BID - SLIPPAGE
        assert cost == SLIPPAGE

    def test_close_short_at_ask_plus_slippage(self):
        price, cost = simulate_exit(Side.SELL, GOLD_BID, GOLD_ASK, SLIPPAGE)
        assert price == GOLD_ASK + SLIPPAGE
        assert cost == SLIPPAGE


class TestSLTPTriggers:
    def test_long_sl_triggers_on_bid(self):
        assert check_sl_tp_trigger(Side.BUY, SL, TP, Decimal("2324"), GOLD_ASK) == "SL"

    def test_long_tp_triggers_on_bid(self):
        assert check_sl_tp_trigger(Side.BUY, SL, TP, Decimal("2341"), GOLD_ASK) == "TP"

    def test_short_sl_triggers_on_ask(self):
        assert check_sl_tp_trigger(Side.SELL, Decimal("2340"), Decimal("2320"), GOLD_BID, Decimal("2341")) == "SL"

    def test_short_tp_triggers_on_ask(self):
        assert check_sl_tp_trigger(Side.SELL, Decimal("2340"), Decimal("2320"), GOLD_BID, Decimal("2319")) == "TP"

    def test_no_trigger_returns_none(self):
        assert check_sl_tp_trigger(Side.BUY, SL, TP, GOLD_BID, GOLD_ASK) is None


class TestAmbiguousBarAdverseOrdering:
    def test_long_ambiguous_bar_sl_first(self):
        result = check_sl_tp_trigger(Side.BUY, Decimal("2325"), Decimal("2320"), Decimal("2324"), GOLD_ASK)
        assert result == "SL"

    def test_short_ambiguous_bar_sl_first(self):
        result = check_sl_tp_trigger(Side.SELL, Decimal("2340"), Decimal("2335"), GOLD_BID, Decimal("2341"))
        assert result == "SL"


class TestNextBarFillTiming:
    def test_signal_cannot_fill_on_same_bar(self):
        assert can_fill_on_info_candle(signal_bar_index=0, fill_bar_index=0) is False

    def test_fill_on_next_bar_allowed(self):
        assert can_fill_on_info_candle(signal_bar_index=0, fill_bar_index=1) is True


class TestCostModelScenarios:
    ENTRY = Decimal("2330")
    EXIT = Decimal("2335")
    VOL = Decimal("0.1")
    CONTRACT = Decimal("100")
    SPREAD_PTS = Decimal("10")

    def test_base_scenario_spread(self):
        costs = calculate_trade_costs(
            self.ENTRY,
            self.EXIT,
            self.VOL,
            self.CONTRACT,
            self.SPREAD_PTS,
            BASE,
        )
        assert costs.spread_cost == self.SPREAD_PTS * self.CONTRACT * self.VOL

    def test_stress_1_1_5x_spread(self):
        costs = calculate_trade_costs(
            self.ENTRY,
            self.EXIT,
            self.VOL,
            self.CONTRACT,
            self.SPREAD_PTS,
            STRESS_1,
        )
        expected = self.SPREAD_PTS * Decimal("1.5") * self.CONTRACT * self.VOL
        assert costs.spread_cost == expected

    def test_stress_3_3x_spread(self):
        costs = calculate_trade_costs(
            self.ENTRY,
            self.EXIT,
            self.VOL,
            self.CONTRACT,
            self.SPREAD_PTS,
            STRESS_3,
        )
        expected = self.SPREAD_PTS * Decimal("3.0") * self.CONTRACT * self.VOL
        assert costs.spread_cost == expected

    def test_run_cost_stress_matrix_returns_all_scenarios(self):
        results = run_cost_stress_matrix(
            self.ENTRY,
            self.EXIT,
            self.VOL,
            self.CONTRACT,
            self.SPREAD_PTS,
        )
        assert len(results) == len(ALL_SCENARIOS)
        for r in results:
            assert isinstance(r, TradeCosts)


class TestOrderStateMachineTransitions:
    def test_happy_path_to_audited(self):
        lc = OrderStateMachine(order_id="test-001")
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
        lc.transition(OrderState.AUDITED, "ok")
        assert lc.state == OrderState.AUDITED
        assert lc.is_terminal()

    def test_invalid_transition_raises(self):
        lc = OrderStateMachine(order_id="test-002")
        with pytest.raises(OrderStateError):
            lc.transition(OrderState.FILLED, "skip steps")

    def test_terminal_states_block_transition(self):
        for terminal in (OrderState.REJECTED, OrderState.EXPIRED, OrderState.AUDITED, OrderState.CRITICAL_INCIDENT):
            lc = OrderStateMachine(order_id=f"test-{terminal.value}")
            if terminal == OrderState.REJECTED:
                lc.transition(OrderState.RISK_CHECKED)
                lc.transition(terminal, "rejected")
            elif terminal == OrderState.EXPIRED:
                for s in (OrderState.RISK_CHECKED, OrderState.ORDER_PRECHECKED, OrderState.ORDER_SUBMITTED):
                    lc.transition(s)
                lc.transition(terminal, "expired")
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
                lc.transition(terminal, "audited")
            elif terminal == OrderState.CRITICAL_INCIDENT:
                for s in (
                    OrderState.RISK_CHECKED,
                    OrderState.ORDER_PRECHECKED,
                    OrderState.ORDER_SUBMITTED,
                    OrderState.ORDER_ACKNOWLEDGED,
                    OrderState.FILLED,
                ):
                    lc.transition(s)
                lc.transition(terminal, "critical")
            assert lc.is_terminal()
            with pytest.raises(OrderStateError):
                lc.transition(OrderState.RISK_CHECKED)

    def test_advance_alias_works(self):
        lc = OrderStateMachine(order_id="test-advance")
        lc.advance(OrderState.RISK_CHECKED, "via alias")
        assert lc.state == OrderState.RISK_CHECKED

    def test_needs_protective_stop_verification_alias(self):
        lc = OrderStateMachine(order_id="test-needs-alias")
        for s in (
            OrderState.RISK_CHECKED,
            OrderState.ORDER_PRECHECKED,
            OrderState.ORDER_SUBMITTED,
            OrderState.ORDER_ACKNOWLEDGED,
            OrderState.FILLED,
        ):
            lc.transition(s)
        lc.transition(OrderState.PROTECTIVE_STOPS_PENDING, "pending")
        assert lc.needs_protective_stop_verification() is True


class TestTradeLedger:
    def test_record_and_retrieve(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = TradeLedger(ledger_dir=tmpdir)
            rec = _make_trade_record()
            ledger.record_trade(rec)
            trades = ledger.get_trades()
            assert len(trades) == 1
            assert trades[0].trade_id == "t-001"
            assert trades[0].entry_price == Decimal("2350.50")

    def test_ledger_hash_deterministic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = TradeLedger(ledger_dir=tmpdir)
            ledger.record_trade(_make_trade_record())
            h1 = ledger.ledger_hash()
            h2 = ledger.ledger_hash()
            assert h1 == h2
            assert len(h1) == 64


class TestNoOrderSend:
    def test_no_order_send_in_execution_modules(self):
        for mod_name in (
            "graxia.packages.quant_os.execution.fill_model",
            "graxia.packages.quant_os.execution.cost_model",
            "graxia.packages.quant_os.execution.order_state_machine",
            "graxia.packages.quant_os.execution.trade_ledger",
        ):
            mod = importlib.import_module(mod_name)
            src = importlib.util.find_spec(mod.__name__).origin
            content = open(src).read()
            assert "order_send" not in content, f"order_send in {mod.__name__}"
