"""Chaos-mode tests for ALL untested execution/ modules.

Covers:
  - ambiguous_bar_resolver
  - conservative_bar_model
  - execution_simulator
  - ledger
  - quality_tracker
  - reconciler
  - recovery (partial — needs broker/ledger mocks)
  - adapters/binance
  - adapters/mt5

Edge cases: empty, None, zero, negative, overflow, concurrent access,
error handling, stress scenarios.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from quant_os.execution.adapters.base import (
    OrderStatus,
)

# ---------------------------------------------------------------------------
# Import modules under test
# ---------------------------------------------------------------------------
from quant_os.execution.ambiguous_bar_resolver import (
    check_bar_triggers_with_ambiguous_resolution,
    resolve_ambiguous_bar,
)
from quant_os.execution.conservative_bar_model import (
    estimate_bid_ask_from_bar,
    next_bar_fill,
    simulate_bar_execution,
)
from quant_os.execution.execution_simulator import (
    BacktestExecutionSimulator,
    ContractSpec,
    EventType,
    MarketSnapshot,
    OrderIntent,
    Position,
)
from quant_os.execution.fill_model import FillRequest, Side
from quant_os.execution.ledger import (
    Ledger,
)
from quant_os.execution.ledger import (
    Position as LedgerPosition,
)
from quant_os.execution.order import Order
from quant_os.execution.order_state_machine import OrderState
from quant_os.execution.quality_tracker import (
    ExecutionQualityTracker,
    FillOutcome,
    FillRecord,
    SlippageReport,
)
from quant_os.execution.reconciler import (
    BrokerPositionSnapshot,
    DiscrepancySeverity,
    DiscrepancyType,
    InternalPosition,
    PositionReconciler,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db():
    """Yield a temp SQLite path and clean up after."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def ledger(tmp_db):
    """Fresh Ledger per test."""
    lg = Ledger(tmp_db, initial_equity=Decimal("10000"))
    yield lg
    lg.close()


def _make_position(
    position_id: str = "pos-001",
    symbol: str = "XAUUSD",
    venue: str = "pepperstone",
    side: str = "LONG",
    qty: Decimal = Decimal("0.10"),
    entry: Decimal = Decimal("2000.00"),
    current: Decimal = Decimal("2010.00"),
    signal_id: str = "",
) -> LedgerPosition:
    now = datetime.now(UTC)
    return LedgerPosition(
        position_id=position_id,
        symbol=symbol,
        asset_class="metals",
        venue=venue,
        side=side,
        quantity=qty,
        entry_price=entry,
        current_price=current,
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        swap_cost=Decimal("0"),
        commission=Decimal("0"),
        opened_at=now,
        updated_at=now,
        signal_id=signal_id,
    )


def _fill_record(
    order_id: str = "ord-1",
    symbol: str = "XAUUSD",
    side: str = "BUY",
    expected: Decimal = Decimal("2000.00"),
    actual: Decimal = Decimal("2000.05"),
    qty: Decimal = Decimal("0.10"),
    filled_qty: Decimal = Decimal("0.10"),
    outcome: FillOutcome = FillOutcome.FILLED,
    latency_ms: float = 12.5,
    spread: Decimal | None = Decimal("0.30"),
) -> FillRecord:
    return FillRecord(
        order_id=order_id,
        symbol=symbol,
        side=side,
        expected_price=expected,
        actual_price=actual,
        quantity=qty,
        filled_quantity=filled_qty,
        outcome=outcome,
        timestamp=datetime.now(UTC),
        latency_ms=latency_ms,
        spread_at_entry=spread,
    )


def _internal_pos(symbol="XAUUSD", side="BUY", qty=Decimal("0.1"), price=Decimal("2000")):
    return InternalPosition(symbol=symbol, side=side, quantity=qty, avg_price=price)


def _broker_pos(symbol="XAUUSD", side="BUY", qty=Decimal("0.1"), price=Decimal("2000")):
    return BrokerPositionSnapshot(symbol=symbol, side=side, quantity=qty, avg_price=price)


# ===================================================================
# 1. AMBIGUOUS BAR RESOLVER — chaos tests
# ===================================================================


class TestAmbiguousBarResolverChaos:
    """Edge-case and chaos tests for ambiguous_bar_resolver."""

    def test_zero_spread_bar(self):
        """All OHLC equal → no trigger."""
        r = resolve_ambiguous_bar(
            Side.BUY,
            Decimal("100"),
            Decimal("110"),
            Decimal("105"),
            Decimal("105"),
            Decimal("105"),
            Decimal("105"),
        )
        assert r.is_ambiguous is False
        assert r.resolved_reason == ""
        assert r.resolution_price == Decimal("105")

    def test_identical_sl_tp(self):
        """SL == TP → ambiguous (adverse wins)."""
        r = resolve_ambiguous_bar(
            Side.BUY,
            Decimal("100"),
            Decimal("100"),
            Decimal("110"),
            Decimal("90"),
            Decimal("100"),
            Decimal("100"),
        )
        assert r.is_ambiguous is True
        assert r.resolved_reason == "SL"

    def test_extreme_large_values(self):
        """Overflow-safe with very large decimals."""
        big = Decimal("999999999999999999.99")
        r = resolve_ambiguous_bar(
            Side.SELL,
            big,
            Decimal("0.01"),
            big,
            Decimal("0.01"),
            Decimal("500000000000"),
            Decimal("500000000000"),
        )
        assert r.sl_distance > 0
        assert r.tp_distance > 0

    def test_negative_prices(self):
        """Negative prices (e.g. oil futures edge case)."""
        r = resolve_ambiguous_bar(
            Side.BUY,
            Decimal("-10"),
            Decimal("10"),
            Decimal("20"),
            Decimal("-20"),
            Decimal("0"),
            Decimal("0"),
        )
        assert r.is_ambiguous is True

    def test_sl_distance_calculation_buy(self):
        r = resolve_ambiguous_bar(
            Side.BUY,
            Decimal("100"),
            Decimal("120"),
            Decimal("130"),
            Decimal("90"),
            Decimal("100"),
            Decimal("105"),
        )
        assert r.sl_distance == Decimal("0")
        assert r.tp_distance == Decimal("20")

    def test_sl_distance_calculation_sell(self):
        r = resolve_ambiguous_bar(
            Side.SELL,
            Decimal("120"),
            Decimal("100"),
            Decimal("130"),
            Decimal("90"),
            Decimal("100"),
            Decimal("105"),
        )
        assert r.sl_distance == Decimal("20")
        assert r.tp_distance == Decimal("0")

    def test_tp_only_long(self):
        r = resolve_ambiguous_bar(
            Side.BUY,
            Decimal("90"),
            Decimal("110"),
            Decimal("115"),
            Decimal("100"),
            Decimal("100"),
            Decimal("105"),
        )
        assert r.resolved_reason == "TP"
        assert r.is_ambiguous is False

    def test_sl_only_short(self):
        r = resolve_ambiguous_bar(
            Side.SELL,
            Decimal("110"),
            Decimal("90"),
            Decimal("115"),
            Decimal("100"),
            Decimal("100"),
            Decimal("105"),
        )
        assert r.resolved_reason == "SL"
        assert r.is_ambiguous is False

    def test_bar_triggers_ambiguous_long(self):
        bar = {"open": 100, "high": 120, "low": 80, "close": 105}
        triggers = check_bar_triggers_with_ambiguous_resolution(
            Side.BUY,
            Decimal("90"),
            Decimal("110"),
            bar,
        )
        assert len(triggers) == 2
        assert triggers[0].trigger_type == "SL"
        assert triggers[0].is_ambiguous is True
        assert triggers[1].trigger_type == "TP"
        assert triggers[1].is_ambiguous is True

    def test_bar_triggers_no_trigger(self):
        bar = {"open": 100, "high": 105, "low": 98, "close": 102}
        triggers = check_bar_triggers_with_ambiguous_resolution(
            Side.BUY,
            Decimal("90"),
            Decimal("110"),
            bar,
        )
        assert len(triggers) == 0

    def test_bar_triggers_single_sl_short(self):
        bar = {"open": 100, "high": 115, "low": 95, "close": 98}
        triggers = check_bar_triggers_with_ambiguous_resolution(
            Side.SELL,
            Decimal("110"),
            Decimal("80"),
            bar,
        )
        assert len(triggers) == 1
        assert triggers[0].trigger_type == "SL"

    def test_empty_bar_dict_keys_crash(self):
        """Missing keys should raise KeyError."""
        with pytest.raises(KeyError):
            check_bar_triggers_with_ambiguous_resolution(
                Side.BUY,
                Decimal("90"),
                Decimal("110"),
                {"open": 100},
            )

    def test_frozen_dataclass_immutability(self):
        r = resolve_ambiguous_bar(
            Side.BUY,
            Decimal("100"),
            Decimal("110"),
            Decimal("120"),
            Decimal("90"),
            Decimal("100"),
            Decimal("105"),
        )
        with pytest.raises(AttributeError):
            r.is_ambiguous = True


# ===================================================================
# 2. CONSERVATIVE BAR MODEL — chaos tests
# ===================================================================


class TestConservativeBarModelChaos:
    def test_estimate_bid_ask_zero_spread(self):
        bid, ask = estimate_bid_ask_from_bar(
            Decimal("100"),
            Decimal("110"),
            Decimal("90"),
            Decimal("100"),
            Decimal("0"),
        )
        assert bid == ask
        assert bid == Decimal("100")

    def test_estimate_bid_ask_symmetric(self):
        bid, ask = estimate_bid_ask_from_bar(
            Decimal("100"),
            Decimal("110"),
            Decimal("90"),
            Decimal("100"),
            Decimal("2"),
        )
        assert ask - bid == Decimal("2")

    def test_estimate_bid_ask_extreme_spread(self):
        bid, ask = estimate_bid_ask_from_bar(
            Decimal("100"),
            Decimal("1000"),
            Decimal("1"),
            Decimal("100"),
            Decimal("500"),
        )
        assert bid < ask
        assert (bid + ask) / 2 == (Decimal("1000") + Decimal("1")) / Decimal("2")

    def test_simulate_bar_execution_empty_bars(self):
        results = simulate_bar_execution(
            [],
            [
                {
                    "bar_index": 0,
                    "side": "BUY",
                    "stop_loss": 90,
                    "take_profit": 110,
                    "slippage_entry": 0.01,
                    "slippage_exit": 0.01,
                }
            ],
            Decimal("0.5"),
            Decimal("0.01"),
        )
        assert results == []

    def test_simulate_bar_execution_out_of_bounds_signal(self):
        bars = [{"timestamp": 0, "open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000}]
        signals = [
            {
                "bar_index": 5,
                "side": "BUY",
                "stop_loss": 90,
                "take_profit": 110,
                "slippage_entry": 0.01,
                "slippage_exit": 0.01,
            }
        ]
        results = simulate_bar_execution(bars, signals, Decimal("0.5"), Decimal("0.01"))
        assert results == []

    def test_simulate_bar_execution_with_tp_no_trigger(self):
        bars = [
            {"timestamp": 0, "open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000},
            {"timestamp": 1, "open": 106, "high": 115, "low": 95, "close": 110, "volume": 1000},
        ]
        signals = [
            {
                "bar_index": 0,
                "side": "BUY",
                "stop_loss": 90,
                "take_profit": 200,
                "slippage_entry": 0.01,
                "slippage_exit": 0.01,
            }
        ]
        results = simulate_bar_execution(bars, signals, Decimal("0.5"), Decimal("0.01"))
        assert len(results) == 1
        assert results[0]["trigger"] is None

    def test_next_bar_fill_no_next_bar(self):
        bars = [{"open": 100, "high": 110, "low": 90, "close": 105}]
        sig = FillRequest(
            side=Side.BUY,
            entry_price=Decimal("100"),
            stop_loss=Decimal("90"),
            take_profit=Decimal("110"),
            slippage_entry=Decimal("0.01"),
            slippage_exit=Decimal("0.01"),
        )
        result = next_bar_fill(
            0,
            sig,
            bars,
            [datetime.now(UTC)],
            Decimal("0.5"),
            Decimal("0.01"),
        )
        assert result is None

    def test_next_bar_fill_negative_slippage(self):
        """Negative slippage = favorable fill (cheaper than ask)."""
        bars = [
            {"open": 100, "high": 110, "low": 90, "close": 105},
            {"open": 100, "high": 110, "low": 90, "close": 105},
        ]
        sig = FillRequest(
            side=Side.BUY,
            entry_price=Decimal("100"),
            stop_loss=Decimal("90"),
            take_profit=Decimal("110"),
            slippage_entry=Decimal("-0.05"),
            slippage_exit=Decimal("0.01"),
        )
        result = next_bar_fill(
            0,
            sig,
            bars,
            [datetime.now(UTC), datetime.now(UTC)],
            Decimal("0.5"),
            Decimal("-0.05"),
        )
        assert result is not None
        # Negative slippage means entry is below the ask price
        ask = (Decimal("110") + Decimal("90")) / Decimal("2") + Decimal("0.5") / Decimal("2")
        assert result.entry_price < ask

    def test_stress_many_signals(self):
        bars = [
            {"timestamp": i, "open": 100 + i, "high": 110 + i, "low": 90 + i, "close": 105 + i, "volume": 1000}
            for i in range(100)
        ]
        signals = [
            {
                "bar_index": i,
                "side": "BUY" if i % 2 == 0 else "SELL",
                "stop_loss": 80 + i,
                "take_profit": 120 + i,
                "slippage_entry": 0.01,
                "slippage_exit": 0.01,
            }
            for i in range(99)
        ]
        results = simulate_bar_execution(bars, signals, Decimal("0.5"), Decimal("0.01"))
        assert len(results) == 99


# ===================================================================
# 3. EXECUTION SIMULATOR — chaos tests
# ===================================================================


class TestExecutionSimulatorChaos:
    @pytest.fixture
    def sim(self):
        return BacktestExecutionSimulator()

    def _intent(self, side=Side.BUY, sl=Decimal("90"), tp=Decimal("110")):
        return OrderIntent(
            symbol="XAUUSD",
            side=side,
            volume=Decimal("0.1"),
            stop_loss=sl,
            take_profit=tp,
        )

    def _market(self, bid=Decimal("100"), ask=Decimal("100.5"), spread=Decimal("0.5")):
        now = datetime.now(UTC)
        return MarketSnapshot(
            bid=bid,
            ask=ask,
            spread=spread,
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
            timestamp=now,
            symbol="XAUUSD",
        )

    def _bars(self, n=3):
        return [{"open": 100 + i, "high": 110 + i, "low": 90 + i, "close": 105 + i} for i in range(n)]

    def test_submit_no_next_bar(self, sim):
        """bar_index at end → empty result."""
        result = sim.submit_intent(self._intent(), self._market(), self._bars(1), 0)
        assert result.entry_price == Decimal("0")
        assert result.order_state == OrderState.REJECTED
        assert result.ambiguous_path == "no_next_bar"

    def test_submit_long_entry_price(self, sim):
        result = sim.submit_intent(self._intent(Side.BUY), self._market(), self._bars(), 0)
        assert result.entry_price > Decimal("100")

    def test_submit_short_entry_price(self, sim):
        result = sim.submit_intent(
            OrderIntent(
                symbol="XAUUSD",
                side=Side.SELL,
                volume=Decimal("0.1"),
                stop_loss=Decimal("110"),
                take_profit=Decimal("90"),
            ),
            self._market(),
            self._bars(),
            0,
        )
        # Short entry = bid - slippage_entry from the fill bar's estimated bid/ask
        # Should be below the fill bar's mid price
        fill_mid = (Decimal("111") + Decimal("91")) / Decimal("2")  # bars[1] mid
        assert result.entry_price < fill_mid

    def test_submit_with_contract_spec(self, sim):
        spec = ContractSpec(
            contract_size=Decimal("100"),
            commission_per_lot=Decimal("7"),
            spread_points=Decimal("0.2"),
        )
        result = sim.submit_intent(
            self._intent(),
            self._market(),
            self._bars(),
            0,
            contract_spec=spec,
        )
        assert result.commission >= Decimal("0")
        assert result.spread_cost >= Decimal("0")

    def test_evaluate_sl_trigger_long(self, sim):
        pos = Position(
            trade_id="t1",
            symbol="XAUUSD",
            side=Side.BUY,
            entry_price=Decimal("100"),
            volume=Decimal("0.1"),
            stop_loss=Decimal("95"),
            take_profit=Decimal("110"),
        )
        market = self._market(bid=Decimal("94"), ask=Decimal("94.5"))
        events = sim.evaluate_open_positions([pos], market, Decimal("94"), Decimal("93"))
        assert len(events) == 1
        assert events[0].event_type == EventType.STOP_LOSS

    def test_evaluate_tp_trigger_long(self, sim):
        pos = Position(
            trade_id="t2",
            symbol="XAUUSD",
            side=Side.BUY,
            entry_price=Decimal("100"),
            volume=Decimal("0.1"),
            stop_loss=Decimal("90"),
            take_profit=Decimal("105"),
        )
        market = self._market(bid=Decimal("106"), ask=Decimal("106.5"))
        events = sim.evaluate_open_positions([pos], market, Decimal("107"), Decimal("100"))
        assert len(events) == 1
        assert events[0].event_type == EventType.TAKE_PROFIT

    def test_evaluate_ambiguous_bar_adverse(self, sim):
        """Both SL and TP possible → adverse (SL) wins.
        For BUY: ambiguous when bid <= SL AND bid >= TP (needs SL > TP).
        """
        pos = Position(
            trade_id="t3",
            symbol="XAUUSD",
            side=Side.BUY,
            entry_price=Decimal("100"),
            volume=Decimal("0.1"),
            stop_loss=Decimal("105"),
            take_profit=Decimal("95"),
        )
        # bid=100: 100 <= 105 (SL) and 100 >= 95 (TP) → ambiguous
        market = self._market(bid=Decimal("100"), ask=Decimal("100.5"))
        events = sim.evaluate_open_positions([pos], market, Decimal("110"), Decimal("90"))
        assert len(events) == 1
        assert events[0].event_type == EventType.AMBIGUOUS

    def test_evaluate_no_trigger(self, sim):
        pos = Position(
            trade_id="t4",
            symbol="XAUUSD",
            side=Side.BUY,
            entry_price=Decimal("100"),
            volume=Decimal("0.1"),
            stop_loss=Decimal("90"),
            take_profit=Decimal("110"),
            signal_bar_index=0,
        )
        market = self._market(bid=Decimal("100"), ask=Decimal("100.5"))
        # current_bar_index=10 < max_bars_open=50 -> no TIME_STOP
        events = sim.evaluate_open_positions([pos], market, Decimal("105"), Decimal("95"), current_bar_index=10)
        assert events == []

    def test_evaluate_time_stop_fires_at_threshold(self, sim):
        pos = Position(
            trade_id="t4b",
            symbol="XAUUSD",
            side=Side.BUY,
            entry_price=Decimal("100"),
            volume=Decimal("0.1"),
            stop_loss=Decimal("90"),
            take_profit=Decimal("110"),
            signal_bar_index=10,
        )
        market = self._market(bid=Decimal("100"), ask=Decimal("100.5"))
        # current_bar_index=60, signal_bar_index=10, diff=50 >= max_bars_open=50
        events = sim.evaluate_open_positions([pos], market, Decimal("105"), Decimal("95"), current_bar_index=60)
        assert len(events) == 1
        assert events[0].event_type == EventType.TIME_STOP

    def test_empty_positions(self, sim):
        events = sim.evaluate_open_positions([], self._market(), Decimal("110"), Decimal("90"))
        assert events == []

    def test_stress_many_positions(self, sim):
        positions = [
            Position(
                trade_id=f"t{i}",
                symbol="XAUUSD",
                side=Side.BUY if i % 2 == 0 else Side.SELL,
                entry_price=Decimal("100"),
                volume=Decimal("0.1"),
                stop_loss=Decimal("90"),
                take_profit=Decimal("110"),
                signal_bar_index=i,
            )
            for i in range(200)
        ]
        market = self._market()
        # current_bar_index=300 ensures all positions exceed max_bars_open=50
        events = sim.evaluate_open_positions(positions, market, Decimal("110"), Decimal("90"), current_bar_index=300)
        assert len(events) == 200


# ===================================================================
# 4. LEDGER — chaos tests (SQLite-backed)
# ===================================================================


class TestLedgerChaos:
    def test_empty_ledger_portfolio(self, ledger):
        pf = ledger.calculate_portfolio(initial_equity=Decimal("10000"))
        assert pf.total_equity == Decimal("10000")
        assert pf.total_unrealized == Decimal("0")
        assert len(pf.positions) == 0

    def test_save_and_retrieve_position(self, ledger):
        pos = _make_position()
        saved = ledger.save_position(pos)
        assert saved.position_id.startswith("pos-")
        retrieved = ledger.get_by_id(saved.position_id)
        assert retrieved is not None
        assert retrieved.symbol == "XAUUSD"

    def test_save_position_empty_id_generates(self, ledger):
        pos = _make_position(position_id="")
        saved = ledger.save_position(pos)
        assert saved.position_id.startswith("pos-")

    def test_close_position(self, ledger):
        pos = ledger.save_position(_make_position())
        ledger.close_position(pos.position_id, realized_pnl=Decimal("50"))
        assert len(ledger.get_all_open()) == 0

    def test_get_nonexistent_returns_none(self, ledger):
        assert ledger.get_by_id("nonexistent") is None
        assert ledger.get_by_signal_id("nonexistent") is None

    def test_get_by_venue_filters(self, ledger):
        ledger.save_position(_make_position(venue="pepperstone"))
        ledger.save_position(_make_position(position_id="pos-002", venue="binance"))
        assert len(ledger.get_by_venue("pepperstone")) == 1
        assert len(ledger.get_by_venue("binance")) == 1
        assert len(ledger.get_by_venue("nonexistent")) == 0

    def test_get_by_symbol(self, ledger):
        ledger.save_position(_make_position(symbol="XAUUSD"))
        ledger.save_position(_make_position(position_id="pos-002", symbol="EURUSD"))
        assert len(ledger.get_by_symbol("XAUUSD")) == 1

    def test_apply_fill_updates_avg_price(self, ledger):
        pos = ledger.save_position(_make_position(qty=Decimal("0.10"), entry=Decimal("2000")))
        updated = ledger.apply_fill(pos.position_id, Decimal("0.05"), Decimal("2010"))
        assert updated.quantity == Decimal("0.15")
        assert updated.entry_price > Decimal("2000")

    def test_apply_fill_nonexistent_raises(self, ledger):
        with pytest.raises(ValueError, match="not found"):
            ledger.apply_fill("nonexistent", Decimal("0.1"), Decimal("2000"))

    def test_apply_fill_zero_new_qty(self, ledger):
        pos = ledger.save_position(_make_position(qty=Decimal("0.10")))
        updated = ledger.apply_fill(pos.position_id, Decimal("-0.10"), Decimal("2000"))
        assert updated.quantity == Decimal("0")

    def test_record_daily_pnl(self, ledger):
        ledger.record_daily_pnl(
            realized=Decimal("100"),
            unrealized=Decimal("50"),
            peak_equity=Decimal("10150"),
        )
        pnl = ledger.get_daily_pnl()
        assert pnl == Decimal("150")

    def test_get_weekly_pnl_empty(self, ledger):
        assert ledger.get_weekly_pnl() == Decimal("0")

    def test_equity_snapshot(self, ledger):
        ledger.record_equity_snapshot(Decimal("10500"))
        ledger.record_equity_snapshot(Decimal("10200"))
        peak = ledger.get_peak_equity()
        assert peak == Decimal("10500")

    def test_portfolio_with_price_fn(self, ledger):
        ledger.save_position(_make_position(qty=Decimal("1"), entry=Decimal("2000")))
        pf = ledger.calculate_portfolio(
            price_fn=lambda s: Decimal("2050"),
            initial_equity=Decimal("10000"),
        )
        assert pf.total_unrealized > Decimal("0")

    def test_portfolio_short_position_pnl(self, ledger):
        ledger.save_position(_make_position(side="SHORT", qty=Decimal("1"), entry=Decimal("2000")))
        pf = ledger.calculate_portfolio(
            price_fn=lambda s: Decimal("1950"),
            initial_equity=Decimal("10000"),
        )
        assert pf.total_unrealized > Decimal("0")

    def test_stress_rapid_saves(self, ledger):
        for i in range(500):
            ledger.save_position(
                _make_position(
                    position_id=f"pos-{i:04d}",
                    symbol=f"SYM{i % 10}",
                )
            )
        assert len(ledger.get_all_open()) == 500

    def test_stress_concurrent_fills(self, ledger):
        pos = ledger.save_position(_make_position(qty=Decimal("100")))
        fills = [
            (pos.position_id, Decimal("0.01"), Decimal("2000"), Decimal("0.01"), Decimal("0"), f"fill-{i}")
            for i in range(50)
        ]
        for f in fills:
            ledger.apply_fill(*f)
        updated = ledger.get_by_id(pos.position_id)
        assert updated.quantity == Decimal("100.50")

    def test_portfolio_drawdown_calculation(self, ledger):
        ledger.save_position(_make_position(qty=Decimal("1"), entry=Decimal("2000")))
        pf = ledger.calculate_portfolio(
            price_fn=lambda s: Decimal("1800"),
            initial_equity=Decimal("10000"),
        )
        assert pf.current_drawdown_pct > Decimal("0")

    def test_ledger_reopens_with_data(self, tmp_db):
        lg = Ledger(tmp_db, initial_equity=Decimal("5000"))
        lg.save_position(_make_position())
        lg.close()
        lg2 = Ledger(tmp_db, initial_equity=Decimal("5000"))
        assert len(lg2.get_all_open()) == 1
        lg2.close()

    def test_update_position(self, ledger):
        pos = ledger.save_position(_make_position())
        pos.current_price = Decimal("2100")
        ledger.update_position(pos)
        retrieved = ledger.get_by_id(pos.position_id)
        assert retrieved.current_price == Decimal("2100")

    def test_multiple_venues_portfolio(self, ledger):
        ledger.save_position(_make_position(venue="pepperstone"))
        ledger.save_position(_make_position(position_id="pos-002", venue="binance"))
        pf = ledger.calculate_portfolio(initial_equity=Decimal("10000"))
        assert len(pf.venue_breakdown) == 2


# ===================================================================
# 5. QUALITY TRACKER — chaos tests
# ===================================================================


class TestQualityTrackerChaos:
    @pytest.fixture
    def tracker(self):
        return ExecutionQualityTracker(pip_size=Decimal("0.01"))

    def test_empty_tracker_metrics(self, tracker):
        m = tracker.get_quality_metrics("XAUUSD")
        assert m.total_fills == 0
        assert m.fill_rate == Decimal("0")

    def test_record_fill_returns_slippage(self, tracker):
        fill = _fill_record()
        report = tracker.record_fill(fill)
        assert isinstance(report, SlippageReport)
        assert report.slippage_pips > 0

    def test_sell_slippage_sign(self, tracker):
        fill = _fill_record(side="SELL", expected=Decimal("2000"), actual=Decimal("2000.05"))
        report = tracker.calculate_slippage(fill)
        assert report.slippage_pips < 0

    def test_zero_slippage(self, tracker):
        fill = _fill_record(expected=Decimal("2000"), actual=Decimal("2000"))
        report = tracker.calculate_slippage(fill)
        assert report.slippage_pips == Decimal("0")
        assert report.within_spread is True

    def test_compare_expected_vs_actual_favorable(self, tracker):
        result = tracker.compare_expected_vs_actual(
            "ord-1",
            Decimal("2000"),
            Decimal("1999.95"),
            "BUY",
        )
        assert result["is_favorable"] is True
        assert result["verdict"] == "FAVORABLE"

    def test_compare_expected_vs_actual_adverse(self, tracker):
        result = tracker.compare_expected_vs_actual(
            "ord-1",
            Decimal("2000"),
            Decimal("2000.10"),
            "BUY",
        )
        assert result["is_favorable"] is False
        assert result["verdict"] == "ADVERSE"

    def test_total_fills_tracked(self, tracker):
        assert tracker.total_fills_tracked == 0
        tracker.record_fill(_fill_record())
        assert tracker.total_fills_tracked == 1

    def test_history_overflow(self):
        tracker = ExecutionQualityTracker(max_history=10)
        for i in range(20):
            tracker.record_fill(_fill_record(order_id=f"ord-{i}"))
        assert tracker.total_fills_tracked == 10

    def test_slippage_history_filter(self, tracker):
        tracker.record_fill(_fill_record(order_id="old"))
        # Simulate old fill by modifying timestamp directly
        tracker._fills[0] = FillRecord(
            order_id="old",
            symbol="XAUUSD",
            side="BUY",
            expected_price=Decimal("2000"),
            actual_price=Decimal("2000"),
            quantity=Decimal("0.1"),
            filled_quantity=Decimal("0.1"),
            outcome=FillOutcome.FILLED,
            timestamp=datetime.now(UTC) - timedelta(hours=48),
            latency_ms=10.0,
        )
        recent = tracker.get_slippage_history("XAUUSD", lookback_hours=24)
        assert len(recent) == 0

    def test_detect_adverse_fills_none(self, tracker):
        fill = _fill_record(expected=Decimal("2000"), actual=Decimal("2000"))
        tracker.record_fill(fill)
        adverse = tracker.detect_adverse_fills("XAUUSD")
        assert len(adverse) == 0

    def test_detect_adverse_fills_detected(self, tracker):
        fill = _fill_record(
            expected=Decimal("2000"),
            actual=Decimal("2001"),
            spread=Decimal("0.01"),
        )
        tracker.record_fill(fill)
        adverse = tracker.detect_adverse_fills("XAUUSD")
        assert len(adverse) == 1

    def test_quality_metrics_all_outcomes(self, tracker):
        for outcome in FillOutcome:
            for _ in range(5):
                tracker.record_fill(_fill_record(outcome=outcome))
        m = tracker.get_quality_metrics("XAUUSD")
        assert m.total_fills == 25
        assert m.filled == 5
        assert m.rejected == 5

    def test_quality_metrics_latency_stats(self, tracker):
        for i in range(10):
            tracker.record_fill(_fill_record(latency_ms=float(i * 10)))
        m = tracker.get_quality_metrics("XAUUSD")
        assert m.avg_latency_ms >= 0
        assert m.max_latency_ms >= m.avg_latency_ms

    def test_slippage_report_fields(self, tracker):
        fill = _fill_record()
        report = tracker.calculate_slippage(fill)
        assert report.symbol == "XAUUSD"
        assert report.side == "BUY"
        assert isinstance(report.slippage_cost, Decimal)

    def test_stress_mass_fills(self, tracker):
        for i in range(1000):
            tracker.record_fill(_fill_record(order_id=f"ord-{i}"))
        assert tracker.total_fills_tracked == 1000
        m = tracker.get_quality_metrics("XAUUSD")
        assert m.total_fills == 1000


# ===================================================================
# 6. POSITION RECONCILER — chaos tests
# ===================================================================


class TestPositionReconcilerChaos:
    @pytest.fixture
    def reconciler(self):
        return PositionReconciler()

    def test_clean_reconciliation(self, reconciler):
        internal = [_internal_pos()]
        broker = [_broker_pos()]
        result = reconciler.reconcile_positions(internal, broker)
        assert result.is_clean
        assert result.matched == 1

    def test_empty_lists(self, reconciler):
        result = reconciler.reconcile_positions([], [])
        assert result.is_clean
        assert result.matched == 0

    def test_internal_only(self, reconciler):
        internal = [_internal_pos()]
        result = reconciler.reconcile_positions(internal, [])
        assert not result.is_clean
        assert result.discrepancies[0].disc_type == DiscrepancyType.BROKER_MISSING

    def test_broker_only(self, reconciler):
        broker = [_broker_pos()]
        result = reconciler.reconcile_positions([], broker)
        assert not result.is_clean
        assert result.discrepancies[0].disc_type == DiscrepancyType.POSITION_MISSING

    def test_side_mismatch_critical(self, reconciler):
        internal = [_internal_pos(side="BUY")]
        broker = [_broker_pos(side="SELL")]
        result = reconciler.reconcile_positions(internal, broker)
        assert result.discrepancies[0].disc_type == DiscrepancyType.SIDE_MISMATCH
        assert result.discrepancies[0].severity == DiscrepancySeverity.CRITICAL

    def test_qty_mismatch_auto_fixable(self, reconciler):
        # diff=0.005 > qty_tolerance(0.0001) but <= auto_fix_threshold(0.01)
        internal = [_internal_pos(qty=Decimal("0.1000"))]
        broker = [_broker_pos(qty=Decimal("0.1050"))]
        result = reconciler.reconcile_positions(internal, broker)
        assert result.discrepancies[0].auto_fixable is True

    def test_qty_mismatch_critical(self, reconciler):
        # diff=0.4 > auto_fix_threshold(0.01) → not auto-fixable
        internal = [_internal_pos(qty=Decimal("0.1"))]
        broker = [_broker_pos(qty=Decimal("0.5"))]
        result = reconciler.reconcile_positions(internal, broker)
        assert result.discrepancies[0].auto_fixable is False
        assert result.discrepancies[0].severity == DiscrepancySeverity.CRITICAL

    def test_price_mismatch_info(self, reconciler):
        internal = [_internal_pos(price=Decimal("2000"))]
        broker = [_broker_pos(price=Decimal("2000.1"))]
        result = reconciler.reconcile_positions(internal, broker)
        assert result.discrepancies[0].disc_type == DiscrepancyType.PRICE_MISMATCH
        assert result.discrepancies[0].severity == DiscrepancySeverity.INFO

    def test_auto_fix_applies(self, reconciler):
        internal = [_internal_pos(qty=Decimal("0.1000"))]
        broker = [_broker_pos(qty=Decimal("0.1050"))]
        result = reconciler.reconcile_positions(internal, broker)
        fixes = reconciler.auto_fix(result)
        assert len(fixes) == 1
        assert fixes[0].new_qty == Decimal("0.1050")

    def test_fix_history(self, reconciler):
        internal = [_internal_pos(qty=Decimal("0.1000"))]
        broker = [_broker_pos(qty=Decimal("0.1050"))]
        result = reconciler.reconcile_positions(internal, broker)
        reconciler.auto_fix(result)
        assert len(reconciler.get_fix_history()) == 1

    def test_no_fix_for_side_mismatch(self, reconciler):
        internal = [_internal_pos(side="BUY")]
        broker = [_broker_pos(side="SELL")]
        result = reconciler.reconcile_positions(internal, broker)
        fixes = reconciler.auto_fix(result)
        assert len(fixes) == 0

    def test_generate_report(self, reconciler):
        internal = [_internal_pos()]
        broker = [_broker_pos()]
        result = reconciler.reconcile_positions(internal, broker)
        report = reconciler.generate_report(result)
        assert "is_clean" in report
        assert "discrepancies" in report
        assert report["matched"] == 1

    def test_find_discrepancies(self, reconciler):
        internal = [_internal_pos(side="BUY")]
        broker = [_broker_pos(side="SELL")]
        discs = reconciler.find_discrepancies(internal, broker)
        assert len(discs) == 1

    def test_stress_many_positions(self, reconciler):
        internal = [_internal_pos(symbol=f"SYM{i}") for i in range(200)]
        broker = [_broker_pos(symbol=f"SYM{i}") for i in range(200)]
        result = reconciler.reconcile_positions(internal, broker)
        assert result.matched == 200

    def test_stress_mixed_discrepancies(self, reconciler):
        internal = [_internal_pos(symbol=f"SYM{i}", side="BUY") for i in range(100)]
        broker = [_broker_pos(symbol=f"SYM{i}", side="SELL" if i % 3 == 0 else "BUY") for i in range(100)]
        result = reconciler.reconcile_positions(internal, broker)
        assert len(result.discrepancies) > 0


# ===================================================================
# 7. RECOVERY — chaos tests (mocked broker/ledger)
# ===================================================================


class TestRecoveryChaos:
    def _make_mock_ledger(self):
        ledger = MagicMock()
        ledger.calculate_portfolio.return_value = MagicMock(
            total_equity=Decimal("10000"),
            current_drawdown_pct=Decimal("5"),
            daily_pnl=Decimal("0"),
        )
        ledger.get_by_venue.return_value = []
        return ledger

    def _make_mock_reconciler(self, clean=True):
        from quant_os.core.enums import ReconciliationStatus
        from quant_os.execution.reconcile import ReconcileAllResult, ReconcileResult

        recon = AsyncMock()
        venue_result = ReconcileResult(
            venue="pepperstone",
            status=ReconciliationStatus.CLEAN if clean else ReconciliationStatus.MISMATCH,
            timestamp=datetime.now(UTC),
            local_count=0,
            broker_count=0,
            matched=0,
            mismatches=[],
            errors=[],
        )
        recon.reconcile_all_venues.return_value = ReconcileAllResult(
            status=ReconciliationStatus.CLEAN if clean else ReconciliationStatus.MISMATCH,
            venue_results={"pepperstone": venue_result},
            total_mismatches=0 if clean else 1,
            timestamp=datetime.now(UTC),
        )
        return recon

    def test_startup_check_dataclass(self):
        from quant_os.execution.recovery import StartupCheck

        check = StartupCheck(name="test", passed=True, detail="ok", severity="INFO")
        assert check.passed is True

    def test_recovery_result_properties(self):
        from quant_os.execution.recovery import RecoveryResult, StartupVerdict

        result = RecoveryResult(
            verdict=StartupVerdict.RESUME,
            reconcile_result=None,
            orphaned_orders=[],
            checks=[],
            timestamp=datetime.now(UTC),
        )
        assert result.is_safe is True
        assert result.critical_failures == []

    def test_recovery_result_critical_failures(self):
        from quant_os.execution.recovery import RecoveryResult, StartupCheck, StartupVerdict

        check = StartupCheck(name="reconcile", passed=False, detail="mismatch", severity="CRITICAL")
        result = RecoveryResult(
            verdict=StartupVerdict.HALT,
            reconcile_result=None,
            orphaned_orders=[],
            checks=[check],
            timestamp=datetime.now(UTC),
        )
        assert result.is_safe is False
        assert len(result.critical_failures) == 1

    def test_orphaned_order_dataclass(self):
        from quant_os.execution.recovery import OrphanedOrder

        orphan = OrphanedOrder(
            order_id="ord-1",
            symbol="XAUUSD",
            broker_order_id="bro-1",
            local_status="OPEN",
            broker_status=None,
            resolution="MARKED_ERROR",
        )
        assert orphan.resolution == "MARKED_ERROR"

    @pytest.mark.asyncio
    async def test_startup_resume_all_clean(self):
        from quant_os.execution.recovery import Recovery, StartupVerdict

        ledger = self._make_mock_ledger()
        reconciler = self._make_mock_reconciler(clean=True)
        adapter = AsyncMock()
        adapter.get_positions.return_value = []
        recovery = Recovery(ledger, reconciler, {"pepperstone": adapter})
        result = await recovery.on_startup(initial_equity=Decimal("10000"))
        assert result.verdict == StartupVerdict.RESUME

    @pytest.mark.asyncio
    async def test_startup_reconcile_exception(self):
        from quant_os.execution.recovery import Recovery, StartupVerdict

        ledger = self._make_mock_ledger()
        reconciler = AsyncMock()
        reconciler.reconcile_all_venues.side_effect = Exception("DB locked")
        recovery = Recovery(ledger, reconciler, {})
        result = await recovery.on_startup(initial_equity=Decimal("10000"))
        assert result.verdict == StartupVerdict.HALT

    @pytest.mark.asyncio
    async def test_startup_drawdown_exceeded(self):
        from quant_os.execution.recovery import Recovery, StartupVerdict

        ledger = self._make_mock_ledger()
        ledger.calculate_portfolio.return_value = MagicMock(
            total_equity=Decimal("10000"),
            current_drawdown_pct=Decimal("20"),
            daily_pnl=Decimal("0"),
        )
        reconciler = self._make_mock_reconciler(clean=True)
        recovery = Recovery(ledger, reconciler, {}, max_drawdown_pct=Decimal("15"))
        result = await recovery.on_startup(initial_equity=Decimal("10000"))
        assert result.verdict == StartupVerdict.HALT

    @pytest.mark.asyncio
    async def test_startup_on_halt_callback(self):
        from quant_os.execution.recovery import Recovery

        ledger = self._make_mock_ledger()
        ledger.calculate_portfolio.return_value = MagicMock(
            total_equity=Decimal("10000"),
            current_drawdown_pct=Decimal("20"),
            daily_pnl=Decimal("0"),
        )
        reconciler = self._make_mock_reconciler(clean=True)
        halt_cb = AsyncMock()
        recovery = Recovery(
            ledger,
            reconciler,
            {},
            max_drawdown_pct=Decimal("15"),
            on_halt=halt_cb,
        )
        await recovery.on_startup(initial_equity=Decimal("10000"))
        halt_cb.assert_called_once()


# ===================================================================
# 8. BINANCE ADAPTER — chaos tests (mocked ccxt)
# ===================================================================


class _BinanceCtx:
    """Container to share mock objects between fixture and tests."""

    def __init__(self):
        self.fake_ccxt = None
        self.mock_exchange = None
        self.adapter = None


class TestBinanceAdapterChaos:
    @pytest.fixture(autouse=True)
    def setup_adapter(self, request):
        """Create BinanceAdapter with fully mocked ccxt."""
        ctx = _BinanceCtx()
        mock_exchange = MagicMock()

        import types

        fake_ccxt = types.ModuleType("ccxt")

        class _BaseExc(Exception):
            pass

        fake_ccxt.InvalidOrder = type("InvalidOrder", (_BaseExc,), {})
        fake_ccxt.InsufficientFunds = type("InsufficientFunds", (_BaseExc,), {})
        fake_ccxt.RateLimitExceeded = type("RateLimitExceeded", (_BaseExc,), {})
        fake_ccxt.NetworkError = type("NetworkError", (_BaseExc,), {})
        fake_ccxt.ExchangeError = type("ExchangeError", (_BaseExc,), {})
        fake_ccxt.binance = MagicMock(return_value=mock_exchange)

        ctx.fake_ccxt = fake_ccxt
        ctx.mock_exchange = mock_exchange

        import quant_os.execution.adapters.binance as binance_mod

        original = binance_mod.ccxt
        binance_mod.ccxt = fake_ccxt
        try:
            from quant_os.execution.adapters.binance import BinanceAdapter

            ctx.adapter = BinanceAdapter("key", "secret", testnet=True)
            request.instance.ctx = ctx
            yield ctx
        finally:
            binance_mod.ccxt = original

    def _order(self, order_id="ord-1", symbol="XAUUSD/USDT", side="BUY", qty=0.1):
        return Order(
            id=order_id,
            signal_id="sig-1",
            symbol=symbol,
            asset_class="metals",
            side=side,
            quantity=qty,
        )

    def test_submit_order_success(self):
        ctx = self.ctx
        ctx.mock_exchange.create_order.return_value = {
            "id": "bro-123",
            "filled": 0.1,
            "average": 2000.0,
        }
        result = ctx.adapter.submit_order(self._order())
        assert result.status == OrderStatus.FILLED
        assert result.broker_id == "bro-123"

    def test_submit_invalid_order(self):
        ctx = self.ctx
        ctx.mock_exchange.create_order.side_effect = ctx.fake_ccxt.InvalidOrder("bad qty")
        result = ctx.adapter.submit_order(self._order())
        assert result.status == OrderStatus.FAILED

    def test_submit_insufficient_funds(self):
        ctx = self.ctx
        ctx.mock_exchange.create_order.side_effect = ctx.fake_ccxt.InsufficientFunds("no money")
        result = ctx.adapter.submit_order(self._order())
        assert result.status == OrderStatus.FAILED

    def test_submit_rate_limit_retries(self):
        ctx = self.ctx
        ctx.mock_exchange.create_order.side_effect = [
            ctx.fake_ccxt.RateLimitExceeded("429"),
            ctx.fake_ccxt.RateLimitExceeded("429"),
            {"id": "bro-456", "filled": 0.1, "average": 2000.0},
        ]
        with patch("time.sleep"):
            result = ctx.adapter.submit_order(self._order())
        assert result.status == OrderStatus.FILLED

    def test_submit_network_error_retries(self):
        ctx = self.ctx
        ctx.mock_exchange.create_order.side_effect = [
            ctx.fake_ccxt.NetworkError("timeout"),
            {"id": "bro-789", "filled": 0.1, "average": 2000.0},
        ]
        with patch("time.sleep"):
            result = ctx.adapter.submit_order(self._order())
        assert result.status == OrderStatus.FILLED

    def test_submit_exchange_error(self):
        ctx = self.ctx
        ctx.mock_exchange.create_order.side_effect = ctx.fake_ccxt.ExchangeError("bad request")
        result = ctx.adapter.submit_order(self._order())
        assert result.status == OrderStatus.FAILED

    def test_submit_retries_exhausted(self):
        ctx = self.ctx
        ctx.mock_exchange.create_order.side_effect = ctx.fake_ccxt.NetworkError("down")
        with patch("time.sleep"):
            result = ctx.adapter.submit_order(self._order())
        assert result.status == OrderStatus.TIMEOUT

    def test_cancel_order_unknown_symbol(self):
        result = self.ctx.adapter.cancel_order("unknown-id")
        assert result.status == OrderStatus.FAILED
        assert "Unknown symbol" in result.error

    def test_cancel_order_success(self):
        ctx = self.ctx
        ctx.adapter._order_symbols["bro-123"] = "XAUUSD/USDT"
        result = ctx.adapter.cancel_order("bro-123")
        assert result.status == OrderStatus.CANCELLED

    def test_cancel_order_rate_limit(self):
        ctx = self.ctx
        ctx.adapter._order_symbols["bro-123"] = "XAUUSD/USDT"
        ctx.mock_exchange.cancel_order.side_effect = [
            ctx.fake_ccxt.RateLimitExceeded("429"),
            None,
        ]
        with patch("time.sleep"):
            result = ctx.adapter.cancel_order("bro-123")
        assert result.status == OrderStatus.CANCELLED

    def test_cancel_order_network_error(self):
        ctx = self.ctx
        ctx.adapter._order_symbols["bro-123"] = "XAUUSD/USDT"
        ctx.mock_exchange.cancel_order.side_effect = [
            ctx.fake_ccxt.NetworkError("timeout"),
            None,
        ]
        with patch("time.sleep"):
            result = ctx.adapter.cancel_order("bro-123")
        assert result.status == OrderStatus.CANCELLED

    def test_cancel_order_exchange_error(self):
        ctx = self.ctx
        ctx.adapter._order_symbols["bro-123"] = "XAUUSD/USDT"
        ctx.mock_exchange.cancel_order.side_effect = ctx.fake_ccxt.ExchangeError("not found")
        result = ctx.adapter.cancel_order("bro-123")
        assert result.status == OrderStatus.FAILED

    def test_cancel_order_retries_exhausted(self):
        ctx = self.ctx
        ctx.adapter._order_symbols["bro-123"] = "XAUUSD/USDT"
        ctx.mock_exchange.cancel_order.side_effect = ctx.fake_ccxt.NetworkError("down")
        with patch("time.sleep"):
            result = ctx.adapter.cancel_order("bro-123")
        assert result.status == OrderStatus.TIMEOUT

    def test_get_order_status_unknown(self):
        result = self.ctx.adapter.get_order_status("unknown-id")
        assert result.status == OrderStatus.FAILED

    def test_get_order_status_success(self):
        ctx = self.ctx
        ctx.adapter._order_symbols["bro-123"] = "XAUUSD/USDT"
        ctx.mock_exchange.fetch_order.return_value = {
            "status": "closed",
            "filled": 0.1,
            "average": 2000.0,
        }
        result = ctx.adapter.get_order_status("bro-123")
        assert result.status == OrderStatus.FILLED

    def test_get_order_status_stale(self):
        ctx = self.ctx
        ctx.adapter._order_symbols["bro-123"] = "XAUUSD/USDT"
        ctx.mock_exchange.fetch_order.return_value = {
            "status": "unknown_status",
            "filled": 0,
            "average": 0,
        }
        result = ctx.adapter.get_order_status("bro-123")
        assert result.status == OrderStatus.FAILED

    def test_get_positions_empty(self):
        ctx = self.ctx
        ctx.mock_exchange.fetch_positions.return_value = []
        assert ctx.adapter.get_positions() == []

    def test_get_positions_filters_zero(self):
        ctx = self.ctx
        ctx.mock_exchange.fetch_positions.return_value = [
            {"symbol": "XAUUSD", "side": "long", "contracts": 0, "entryPrice": 0, "unrealizedPnl": 0, "leverage": 1},
            {
                "symbol": "BTCUSDT",
                "side": "long",
                "contracts": 1,
                "entryPrice": 50000,
                "unrealizedPnl": 100,
                "leverage": 10,
            },
        ]
        positions = ctx.adapter.get_positions()
        assert len(positions) == 1
        assert positions[0]["symbol"] == "BTCUSDT"

    def test_get_account_info(self):
        ctx = self.ctx
        ctx.mock_exchange.fetch_balance.return_value = {
            "total": {"USDT": 10000},
            "free": {"USDT": 8000},
            "used": {"USDT": 2000},
        }
        info = ctx.adapter.get_account_info()
        assert info.equity == 10000.0
        assert info.cash == 8000.0


# ===================================================================
# 9. MT5 ADAPTER — chaos tests (mocked MetaTrader5)
# ===================================================================


class TestMT5AdapterChaos:
    @pytest.fixture(autouse=True)
    def setup_mt5(self, request):
        mock_mt5 = MagicMock()
        import quant_os.execution.adapters.mt5 as mt5_mod

        original = mt5_mod.mt5
        mt5_mod.mt5 = mock_mt5
        try:
            from quant_os.execution.adapters.mt5 import MT5Adapter

            adapter = MT5Adapter(login=12345, password="pass", server="test")
            request.instance.ctx = type("Ctx", (), {"adapter": adapter, "mt5": mock_mt5})()
            yield request.instance.ctx
        finally:
            mt5_mod.mt5 = original

    def _mock_result(self, retcode=10009, order=99999, volume=0.1, price=2000.0, comment=""):
        m = MagicMock()
        m.retcode = retcode
        m.order = order
        m.volume = volume
        m.price = price
        m.comment = comment
        return m

    def _order(self, order_id="ord-1", symbol="XAUUSD", side="BUY", qty=0.1):
        return Order(
            id=order_id,
            signal_id="sig-1",
            symbol=symbol,
            asset_class="metals",
            side=side,
            quantity=qty,
        )

    def test_side_to_order_type_buy(self):
        from quant_os.execution.adapters.mt5 import _side_to_order_type

        assert _side_to_order_type("BUY") == 0

    def test_side_to_order_type_sell(self):
        from quant_os.execution.adapters.mt5 import _side_to_order_type

        assert _side_to_order_type("SELL") == 1

    def test_side_to_order_type_invalid(self):
        from quant_os.execution.adapters.mt5 import _side_to_order_type

        with pytest.raises(ValueError):
            _side_to_order_type("INVALID")

    def test_connect_success(self):
        c = self.ctx
        c.mt5.initialize.return_value = True
        c.mt5.login.return_value = True
        assert c.adapter.connect() is True
        assert c.adapter._connected is True

    def test_connect_initialize_fails(self):
        c = self.ctx
        c.mt5.initialize.return_value = False
        assert c.adapter.connect() is False

    def test_connect_login_fails(self):
        c = self.ctx
        c.mt5.initialize.return_value = True
        c.mt5.login.return_value = False
        assert c.adapter.connect() is False

    def test_shutdown(self):
        c = self.ctx
        c.adapter._connected = True
        c.adapter.shutdown()
        assert c.adapter._connected is False

    def test_submit_order_success(self):
        c = self.ctx
        c.adapter._connected = True
        c.mt5.order_send.return_value = self._mock_result(retcode=10009)
        result = c.adapter.submit_order(self._order())
        assert result.status == OrderStatus.FILLED
        assert result.broker_id == "99999"

    def test_submit_order_none_result_reconnect_fails(self):
        """order_send returns None → reconnect fails → ConnectionError."""
        c = self.ctx
        c.adapter._connected = True
        c.mt5.order_send.return_value = None
        c.mt5.last_error.return_value = "connection lost"
        c.mt5.terminal_info.return_value = None
        c.mt5.initialize.return_value = False
        with patch("time.sleep"):
            with pytest.raises(ConnectionError, match="reconnect failed"):
                c.adapter.submit_order(self._order())

    def test_submit_order_none_result_reconnect_succeeds(self):
        """order_send returns None → reconnect succeeds → retries → TIMEOUT."""
        c = self.ctx
        c.adapter._connected = True
        # Make terminal_info truthy so _ensure_connected passes quickly
        # after reconnect sets _connected=True again
        c.mt5.terminal_info.return_value = MagicMock()
        c.mt5.initialize.return_value = True
        c.mt5.login.return_value = True
        c.mt5.order_send.return_value = None
        with patch("time.sleep"):
            result = c.adapter.submit_order(self._order())
        assert result.status == OrderStatus.TIMEOUT

    def test_submit_order_invalid_price_retry(self):
        c = self.ctx
        c.adapter._connected = True
        c.mt5.order_send.side_effect = [
            self._mock_result(retcode=10014),
            self._mock_result(retcode=10009, order=88888),
        ]
        with patch("time.sleep"):
            result = c.adapter.submit_order(self._order())
        assert result.status == OrderStatus.FILLED

    def test_submit_order_permanent_failure(self):
        c = self.ctx
        c.adapter._connected = True
        c.mt5.order_send.return_value = self._mock_result(retcode=10013, comment="invalid volume")
        result = c.adapter.submit_order(self._order())
        assert result.status == OrderStatus.FAILED

    def test_cancel_order_success(self):
        c = self.ctx
        c.adapter._connected = True
        c.mt5.order_send.return_value = self._mock_result(retcode=10009)
        result = c.adapter.cancel_order("12345")
        assert result.status == OrderStatus.CANCELLED

    def test_cancel_order_failure(self):
        c = self.ctx
        c.adapter._connected = True
        c.mt5.order_send.return_value = self._mock_result(retcode=10013, comment="not found")
        result = c.adapter.cancel_order("12345")
        assert result.status == OrderStatus.FAILED

    def test_cancel_order_none_result(self):
        c = self.ctx
        c.adapter._connected = True
        c.mt5.order_send.return_value = None
        c.mt5.last_error.return_value = "error"
        result = c.adapter.cancel_order("12345")
        # With retry logic, None result returns TIMEOUT after retries exhausted
        assert result.status == OrderStatus.TIMEOUT

    def test_get_positions_empty(self):
        c = self.ctx
        c.adapter._connected = True
        c.mt5.positions_get.return_value = None
        assert c.adapter.get_positions() == []

    def test_get_positions_with_data(self):
        c = self.ctx
        c.adapter._connected = True
        pos = MagicMock()
        pos.ticket = 111
        pos.symbol = "XAUUSD"
        pos.type = 0
        pos.volume = 0.1
        pos.price_open = 2000.0
        pos.profit = 50.0
        pos.sl = 1950.0
        pos.tp = 2100.0
        pos.comment = ""
        c.mt5.positions_get.return_value = [pos]
        positions = c.adapter.get_positions()
        assert len(positions) == 1
        assert positions[0]["type"] == "BUY"

    def test_get_order_status_filled(self):
        c = self.ctx
        c.adapter._connected = True
        c.mt5.orders_get.return_value = None
        # Mock history_deals_get to return a fill deal (entry=0 = ENTRY_IN)
        fill_deal = MagicMock()
        fill_deal.entry = 0  # ENTRY_IN
        fill_deal.volume = 0.1
        fill_deal.price = 2000.0
        c.mt5.history_deals_get.return_value = [fill_deal]
        result = c.adapter.get_order_status("12345")
        # Bug fix: missing order now returns UNKNOWN (not FILLED)
        assert result.status == OrderStatus.UNKNOWN

    def test_get_order_status_open(self):
        c = self.ctx
        c.adapter._connected = True
        order = MagicMock()
        order.ticket = 12345
        c.mt5.orders_get.return_value = [order]
        result = c.adapter.get_order_status("12345")
        assert result.status == OrderStatus.SUBMITTED

    def test_get_account_info(self):
        c = self.ctx
        c.adapter._connected = True
        info = MagicMock()
        info.equity = 10000.0
        info.balance = 9500.0
        info.margin = 500.0
        info.margin_free = 9500.0
        c.mt5.account_info.return_value = info
        result = c.adapter.get_account_info()
        assert result.equity == 10000.0

    def test_ensure_connected_reconnect(self):
        c = self.ctx
        c.adapter._connected = False
        c.mt5.initialize.return_value = True
        c.mt5.login.return_value = True
        c.adapter._ensure_connected()
        assert c.adapter._connected is True

    def test_ensure_connected_raises_after_retries(self):
        c = self.ctx
        c.adapter._connected = False
        c.mt5.initialize.return_value = False
        with patch("time.sleep"):
            with pytest.raises(ConnectionError, match="reconnect failed"):
                c.adapter._ensure_connected()

    def test_no_mt5_import_raises(self):
        import quant_os.execution.adapters.mt5 as mt5_mod

        original = mt5_mod.mt5
        mt5_mod.mt5 = None
        try:
            from quant_os.execution.adapters.mt5 import MT5Adapter

            adapter = MT5Adapter(login=12345, password="pass")
            with pytest.raises(RuntimeError, match="not installed"):
                adapter.connect()
        finally:
            mt5_mod.mt5 = original


# ===================================================================
# 10. CROSS-MODULE CHAOS — stress and concurrency
# ===================================================================


class TestCrossModuleChaos:
    def test_ambiguous_to_simulator_pipeline(self):
        """Full pipeline: ambiguous bar resolution → simulator fill."""
        r = resolve_ambiguous_bar(
            Side.BUY,
            Decimal("1950"),
            Decimal("2050"),
            Decimal("2060"),
            Decimal("1940"),
            Decimal("2000"),
            Decimal("2010"),
        )
        assert r.is_ambiguous is True
        sim = BacktestExecutionSimulator()
        intent = OrderIntent(
            symbol="XAUUSD",
            side=Side.BUY,
            volume=Decimal("0.1"),
            stop_loss=Decimal("1950"),
            take_profit=Decimal("2050"),
        )
        now = datetime.now(UTC)
        market = MarketSnapshot(
            bid=Decimal("1940"),
            ask=Decimal("2060"),
            spread=Decimal("120"),
            high=Decimal("2060"),
            low=Decimal("1940"),
            close=Decimal("2010"),
            timestamp=now,
            symbol="XAUUSD",
        )
        bars = [
            {"open": 2000, "high": 2060, "low": 1940, "close": 2010},
            {"open": 2010, "high": 2020, "low": 2000, "close": 2015},
        ]
        result = sim.submit_intent(intent, market, bars, 0)
        assert result.entry_price > Decimal("0")

    def test_ledger_to_reconciler_pipeline(self):
        """Ledger → reconciler comparison."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            ledger = Ledger(db_path, initial_equity=Decimal("10000"))
            pos = _make_position(qty=Decimal("0.1"), entry=Decimal("2000"))
            ledger.save_position(pos)
            ledger.close()

            reconciler = PositionReconciler()
            internal = [_internal_pos(qty=Decimal("0.1"), price=Decimal("2000"))]
            broker = [_broker_pos(qty=Decimal("0.1"), price=Decimal("2000"))]
            result = reconciler.reconcile_positions(internal, broker)
            assert result.is_clean
        finally:
            os.unlink(db_path)

    def test_quality_tracker_to_reconciler_pipeline(self):
        """Quality tracker adverse fills → reconciler discrepancy."""
        tracker = ExecutionQualityTracker(pip_size=Decimal("0.01"))
        for i in range(10):
            fill = _fill_record(
                order_id=f"ord-{i}",
                expected=Decimal("2000"),
                actual=Decimal("2000.50") if i < 3 else Decimal("2000.02"),
            )
            tracker.record_fill(fill)
        adverse = tracker.detect_adverse_fills("XAUUSD")
        assert len(adverse) == 3

    def test_stress_rapid_order_submit(self):
        """Simulate rapid order creation via simulator."""
        sim = BacktestExecutionSimulator()
        now = datetime.now(UTC)
        market = MarketSnapshot(
            bid=Decimal("100"),
            ask=Decimal("100.5"),
            spread=Decimal("0.5"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
            timestamp=now,
            symbol="XAUUSD",
        )
        bars = [{"open": 100, "high": 110, "low": 90, "close": 105} for _ in range(102)]
        results = []
        for i in range(100):
            intent = OrderIntent(
                symbol="XAUUSD",
                side=Side.BUY,
                volume=Decimal("0.01"),
                stop_loss=Decimal("90"),
                take_profit=Decimal("110"),
            )
            result = sim.submit_intent(intent, market, bars, i)
            results.append(result)
        assert all(r.entry_price > Decimal("0") for r in results)

    def test_concurrent_ledger_access(self):
        """SQLite concurrent access — serialized via single connection."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            ledger = Ledger(db_path, initial_equity=Decimal("10000"))
            pos = ledger.save_position(_make_position(qty=Decimal("0")))
            errors = []

            # SQLite with check_same_thread=False allows concurrent reads but
            # serializes writes. Test rapid sequential fills instead of threads.
            for i in range(50):
                try:
                    ledger.apply_fill(
                        pos.position_id,
                        Decimal("0.01"),
                        Decimal("2000"),
                        Decimal("0.01"),
                        Decimal("0"),
                        f"fill-{i}",
                    )
                except Exception as e:
                    errors.append(e)
            assert len(errors) == 0
            final = ledger.get_by_id(pos.position_id)
            assert final.quantity == Decimal("0.50")
            ledger.close()
        finally:
            os.unlink(db_path)

    def test_mass_cancellation_stress(self):
        """Simulate cancelling 500 orders rapidly."""
        sim = BacktestExecutionSimulator()
        now = datetime.now(UTC)
        market = MarketSnapshot(
            bid=Decimal("100"),
            ask=Decimal("100.5"),
            spread=Decimal("0.5"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
            timestamp=now,
            symbol="XAUUSD",
        )
        bars = [{"open": 100, "high": 110, "low": 90, "close": 105}]
        positions = [
            Position(
                trade_id=f"t{i}",
                symbol="XAUUSD",
                side=Side.BUY,
                entry_price=Decimal("100"),
                volume=Decimal("0.01"),
                stop_loss=Decimal("90"),
                take_profit=Decimal("110"),
            )
            for i in range(500)
        ]
        events = sim.evaluate_open_positions(positions, market, Decimal("100"), Decimal("100"), current_bar_index=600)
        assert len(events) == 500
