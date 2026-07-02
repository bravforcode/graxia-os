"""Execution simulator — canonical protocol for order fill and position evaluation.

Bridges fill_model, conservative_bar_model, cost_model, and order_state_machine
into a single interface. The canonical engine may ONLY use this module for
execution logic — no direct close-price fills, no direct SL/TP outside this module.

Rules enforced:
  - Long entry  = ask + slippage
  - Short entry = bid - slippage
  - Long SL trigger  = bid <= stop_loss
  - Long TP trigger  = bid >= take_profit
  - Short SL trigger = ask >= stop_loss
  - Short TP trigger = ask <= take_profit
  - Ambiguous bar (both SL and TP) → resolve ADVERSE first, record ambiguous_bar=true
  - Signal timing: signal from closed bar N → fill on N+1 only
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol, runtime_checkable

from .conservative_bar_model import estimate_bid_ask_from_bar
from .cost_model import BASE as COST_BASE
from .cost_model import calculate_trade_costs
from .fill_model import (
    ExecutionQuality,
    FillRequest,
    Side,
    check_sl_tp_trigger,
    simulate_entry,
    simulate_exit,
)
from .order_state_machine import OrderState, OrderStateMachine
from .trade_ledger import TradeLedger, TradeRecord

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EventType(Enum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    AMBIGUOUS = "AMBIGUOUS"
    TIME_STOP = "TIME_STOP"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OrderIntent:
    """Proposed trade to be simulated."""

    symbol: str
    side: Side
    volume: Decimal
    stop_loss: Decimal
    take_profit: Decimal | None = None
    strategy_id: str = ""
    signal_id: str = ""
    execution_quality: ExecutionQuality = ExecutionQuality.BAR_ONLY


@dataclass(frozen=True)
class MarketSnapshot:
    """Current market state passed to the simulator."""

    bid: Decimal
    ask: Decimal
    spread: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    timestamp: datetime
    symbol: str = ""


@dataclass(frozen=True)
class ContractSpec:
    """Contract parameters for cost calculation."""

    contract_size: Decimal = Decimal("1")
    commission_per_lot: Decimal = Decimal("0")
    spread_points: Decimal = Decimal("0")


@dataclass(frozen=True)
class ExecutionResult:
    """Result of fill simulation from submit_intent."""

    entry_price: Decimal
    exit_price: Decimal
    sl_cost: Decimal
    slippage_cost: Decimal
    commission: Decimal
    spread_cost: Decimal
    execution_quality: ExecutionQuality
    is_ambiguous: bool
    ambiguous_path: str
    order_state: OrderState


@dataclass
class ExecutionEvent:
    """Result of position evaluation from evaluate_open_positions."""

    trade_id: str
    event_type: EventType
    exit_price: Decimal
    pnl: Decimal
    reason: str


@dataclass
class Position:
    """Open position tracked by the engine."""

    trade_id: str
    symbol: str
    side: Side
    entry_price: Decimal
    volume: Decimal
    stop_loss: Decimal
    take_profit: Decimal | None = None
    strategy_id: str = ""
    signal_bar_index: int = 0


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ExecutionSimulator(Protocol):
    """Canonical execution interface — the engine depends on NOTHING else."""

    def submit_intent(self, intent: OrderIntent, market: MarketSnapshot) -> ExecutionResult: ...

    def evaluate_open_positions(self, positions: list[Position], market: MarketSnapshot) -> list[ExecutionEvent]: ...


# ---------------------------------------------------------------------------
# Backtest implementation
# ---------------------------------------------------------------------------


class BacktestExecutionSimulator:
    """Backtest-mode simulator using conservative bar-based fills.

    Uses fill_model for entry/exit pricing and SL/TP trigger detection,
    conservative_bar_model for bid/ask estimation from OHLC bars,
    cost_model for commission/spread cost calculation,
    and order_state_machine for state transitions.
    """

    __slots__ = ("_ledger",)

    def __init__(self, ledger: TradeLedger | None = None) -> None:
        self._ledger = ledger

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def submit_intent(
        self,
        intent: OrderIntent,
        market: MarketSnapshot,
        bars: list[dict],
        bar_index: int,
        contract_spec: ContractSpec | None = None,
    ) -> ExecutionResult:
        """Simulate filling an OrderIntent on bar_index + 1.

        Signal timing: a signal from closed bar N is filled on bar N+1.
        Entry price follows the strict rules:
          BUY  → ask + slippage_entry
          SELL → bid − slippage_entry
        """
        fill_idx = bar_index + 1
        if fill_idx >= len(bars):
            return self._empty_result(intent.execution_quality)

        fill_bar = bars[fill_idx]
        bid, ask = estimate_bid_ask_from_bar(
            fill_bar["open"],
            fill_bar["high"],
            fill_bar["low"],
            fill_bar["close"],
            market.spread,
        )
        spread = ask - bid

        slippage_entry = market.spread / Decimal("2")
        slippage_exit = market.spread / Decimal("2")

        req = FillRequest(
            side=intent.side,
            entry_price=Decimal(str(fill_bar["open"])),
            stop_loss=intent.stop_loss,
            take_profit=intent.take_profit or Decimal("0"),
            slippage_entry=slippage_entry,
            slippage_exit=slippage_exit,
        )
        fill = simulate_entry(req, bid, ask, spread)

        sm = OrderStateMachine()
        sm.advance(OrderState.RISK_CHECKED, "risk pass")
        sm.advance(OrderState.ORDER_PRECHECKED, "precheck pass")
        sm.advance(OrderState.ORDER_SUBMITTED, "submitted")
        sm.advance(OrderState.ORDER_ACKNOWLEDGED, "acknowledged")
        sm.advance(OrderState.FILLED, "filled")

        commission = Decimal("0")
        spread_cost = Decimal("0")
        if contract_spec is not None:
            costs = calculate_trade_costs(
                entry_price=fill.entry_price,
                exit_price=Decimal("0"),
                volume=intent.volume,
                contract_size=contract_spec.contract_size,
                spread_points=contract_spec.spread_points,
                scenario=COST_BASE,
                commission_per_lot=contract_spec.commission_per_lot,
            )
            commission = costs.commission
            spread_cost = costs.spread_cost

        result = ExecutionResult(
            entry_price=fill.entry_price,
            exit_price=fill.exit_price,
            sl_cost=fill.sl_cost,
            slippage_cost=fill.slippage_cost,
            commission=commission,
            spread_cost=spread_cost,
            execution_quality=fill.execution_quality,
            is_ambiguous=fill.is_ambiguous,
            ambiguous_path=fill.ambiguous_path,
            order_state=sm.state,
        )

        if self._ledger is not None:
            record = TradeRecord(
                trade_id="",
                order_id="",
                symbol=intent.symbol,
                side=intent.side.value,
                entry_price=fill.entry_price,
                volume=intent.volume,
                execution_quality=intent.execution_quality.value,
                strategy_id=intent.strategy_id,
                fees=commission,
                spread_cost=spread_cost,
                slippage_cost=fill.slippage_cost,
            )
            self._ledger.record_trade(record)

        return result

    def evaluate_open_positions(
        self,
        positions: list[Position],
        market: MarketSnapshot,
        bar_high: Decimal,
        bar_low: Decimal,
        max_bars_open: int = 50,
    ) -> list[ExecutionEvent]:
        """Evaluate all open positions for SL/TP triggers on the current bar.

        Ambiguous bars (both SL and TP could hit) are resolved ADVERSE first:
          - BUY  → SL resolves first  (bid <= stop_loss)
          - SELL → SL resolves first  (ask >= stop_loss)

        Returns a list of ExecutionEvent for each position that triggered.
        """
        events: list[ExecutionEvent] = []

        for pos in positions:
            trigger = check_sl_tp_trigger(
                pos.side,
                pos.stop_loss,
                pos.take_profit or Decimal("0"),
                market.bid,
                market.ask,
            )

            if trigger == "SL" and pos.take_profit is not None:
                tp_hit = (pos.side == Side.BUY and market.bid >= pos.take_profit) or (
                    pos.side == Side.SELL and market.ask <= pos.take_profit
                )
                if tp_hit:
                    exit_price, pnl = self._resolve_adverse(pos, market)
                    event = ExecutionEvent(
                        trade_id=pos.trade_id,
                        event_type=EventType.AMBIGUOUS,
                        exit_price=exit_price,
                        pnl=pnl,
                        reason="ambiguous_bar_adverse_sl",
                    )
                    events.append(event)
                    self._record_event(pos, event)
                    continue

            if trigger == "SL":
                exit_price, pnl = self._resolve_exit(pos, market, "SL")
                event = ExecutionEvent(
                    trade_id=pos.trade_id,
                    event_type=EventType.STOP_LOSS,
                    exit_price=exit_price,
                    pnl=pnl,
                    reason="stop_loss_hit",
                )
                events.append(event)
                self._record_event(pos, event)

            elif trigger == "TP":
                exit_price, pnl = self._resolve_exit(pos, market, "TP")
                event = ExecutionEvent(
                    trade_id=pos.trade_id,
                    event_type=EventType.TAKE_PROFIT,
                    exit_price=exit_price,
                    pnl=pnl,
                    reason="take_profit_hit",
                )
                events.append(event)
                self._record_event(pos, event)

            elif max_bars_open > 0 and hasattr(pos, "signal_bar_index"):
                mid = (market.high + market.low) / Decimal("2")
                if pos.side == Side.BUY:
                    exit_price = mid - market.spread / Decimal("2")
                    pnl = (exit_price - pos.entry_price) * pos.volume
                else:
                    exit_price = mid + market.spread / Decimal("2")
                    pnl = (pos.entry_price - exit_price) * pos.volume

                event = ExecutionEvent(
                    trade_id=pos.trade_id,
                    event_type=EventType.TIME_STOP,
                    exit_price=exit_price,
                    pnl=pnl,
                    reason="time_stop_max_bars",
                )
                events.append(event)
                self._record_event(pos, event)

        return events

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_adverse(self, pos: Position, market: MarketSnapshot) -> tuple[Decimal, Decimal]:
        """Resolve ambiguous bar — adverse (SL) outcome first."""
        exit_price, slippage = simulate_exit(pos.side, market.bid, market.ask, market.spread / Decimal("2"))
        if pos.side == Side.BUY:
            exit_price = pos.stop_loss
            pnl = (exit_price - pos.entry_price) * pos.volume
        else:
            exit_price = pos.stop_loss
            pnl = (pos.entry_price - exit_price) * pos.volume
        return exit_price, pnl

    def _resolve_exit(self, pos: Position, market: MarketSnapshot, trigger: str) -> tuple[Decimal, Decimal]:
        """Resolve a clean SL or TP exit."""
        if trigger == "SL":
            exit_price = pos.stop_loss
        else:
            exit_price = pos.take_profit or Decimal("0")

        if pos.side == Side.BUY:
            pnl = (exit_price - pos.entry_price) * pos.volume
        else:
            pnl = (pos.entry_price - exit_price) * pos.volume
        return exit_price, pnl

    def _record_event(self, pos: Position, event: ExecutionEvent) -> None:
        """Record an execution event to the trade ledger if available."""
        if self._ledger is None:
            return
        record = TradeRecord(
            trade_id=pos.trade_id,
            order_id="",
            symbol=pos.symbol,
            side=pos.side.value,
            entry_price=pos.entry_price,
            exit_price=event.exit_price,
            volume=pos.volume,
            pnl=event.pnl,
            close_reason=event.event_type.value,
            strategy_id=pos.strategy_id,
        )
        self._ledger.record_trade(record)

    @staticmethod
    def _empty_result(q: ExecutionQuality) -> ExecutionResult:
        """Return a no-fill result when no next bar exists."""
        return ExecutionResult(
            entry_price=Decimal("0"),
            exit_price=Decimal("0"),
            sl_cost=Decimal("0"),
            slippage_cost=Decimal("0"),
            commission=Decimal("0"),
            spread_cost=Decimal("0"),
            execution_quality=q,
            is_ambiguous=False,
            ambiguous_path="no_next_bar",
            order_state=OrderState.REJECTED,
        )
