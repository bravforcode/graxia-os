"""Phase 3B — Run frozen strategy with cost scenarios.

R0: Base spread, base swap
R1: 1.5x spread, base swap
R2: 2.0x spread, 1.5x adverse swap
R3: 3.0x spread, 2.0x adverse swap

Spread multiplier patches the engine's hardcoded 2-pip spread
by overriding _execute_signal and _check_exits in a subclass.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Tuple, Dict, Any

from ..backtest.engine import (
    BacktestEngine, BacktestConfig, InlineContractSpec,
    _exec_side, _historical_size,
)
from ..execution.cost_model import BASE, STRESS_1, STRESS_2, STRESS_3, CostScenario
from ..execution.execution_simulator import (
    MarketSnapshot, ContractSpec, OrderIntent, ExecutionQuality,
    Position as ExecPosition,
)
from ..execution.fill_model import Side as FillSide, simulate_exit as fill_simulate_exit
from ..execution.conservative_bar_model import estimate_bid_ask_from_bar
from ..core.enums import SignalType, PositionType, CloseReason
from ..strategies.base import Signal


class SpreadPatchedEngine(BacktestEngine):
    """Engine that applies a spread multiplier to entry/exit costs."""

    def __init__(self, config: BacktestConfig, spread_multiplier: float = 1.0):
        super().__init__(config)
        self._spread_multiplier = spread_multiplier

    def _scaled_spread(self) -> Decimal:
        return Decimal("0.01") * Decimal("2") * Decimal(str(self._spread_multiplier))

    def _execute_signal(self, signal, bar_open, bar_high, bar_low, bar_close, current_time, bar_index):
        if len(self.positions) >= self.config.max_positions:
            return
        for pos in self.positions.values():
            if pos.symbol == signal.symbol:
                return
        if not signal.stop_loss or signal.stop_loss <= 0:
            self._log_critical_incident("MISSING_SL", signal)
            return

        side = _exec_side(signal.signal_type)
        entry_price = signal.entry_price or bar_close
        if signal.signal_type == SignalType.BUY and signal.stop_loss >= entry_price:
            self._log_critical_incident("INVALID_SL_DIRECTION", signal)
            return
        if signal.signal_type == SignalType.SELL and signal.stop_loss <= entry_price:
            self._log_critical_incident("INVALID_SL_DIRECTION", signal)
            return

        volume = _historical_size(
            equity=self.equity,
            risk_per_trade_bps=self.config.risk_per_trade_bps,
            entry_price=entry_price,
            stop_loss=signal.stop_loss,
            contract=InlineContractSpec.for_symbol(signal.symbol),
        )
        if volume <= 0:
            return

        spread = self._scaled_spread()
        bid, ask = estimate_bid_ask_from_bar(bar_open, bar_high, bar_low, bar_close, spread)
        snapshot = MarketSnapshot(
            bid=bid, ask=ask, spread=spread,
            high=bar_high, low=bar_low, close=bar_close,
            timestamp=current_time, symbol=signal.symbol,
        )
        contract_spec = ContractSpec(
            contract_size=InlineContractSpec.for_symbol(signal.symbol).trade_contract_size,
            commission_per_lot=self.config.commission_per_lot,
            spread_points=spread,
        )
        intent = OrderIntent(
            symbol=signal.symbol, side=side, volume=volume,
            stop_loss=signal.stop_loss, take_profit=signal.take_profit,
            strategy_id=self.strategy.id if self.strategy else "",
            signal_id=signal.id,
            execution_quality=ExecutionQuality.BAR_ONLY,
        )
        result = self._simulator.submit_intent(
            intent, snapshot, self._bar_dicts(), bar_index,
            contract_spec=contract_spec,
        )
        if result.entry_price <= 0 or volume <= 0:
            return

        from uuid import uuid4
        pos_id = str(uuid4())[:8]
        pos_side = PositionType.LONG if side == FillSide.BUY else PositionType.SHORT
        fill_time = self.timestamps[bar_index + 1] if bar_index + 1 < len(self.timestamps) else current_time
        self.positions[pos_id] = BacktestPosition(
            id=pos_id, symbol=signal.symbol, side=pos_side,
            entry_price=result.entry_price, quantity=volume,
            stop_loss=signal.stop_loss, take_profit=signal.take_profit,
            entry_time=fill_time,
            strategy_id=self.strategy.id if self.strategy else "",
            entry_spread_cost=result.spread_cost,
            entry_slippage_cost=result.slippage_cost,
            execution_quality=result.execution_quality.value,
            signal_bar_index=bar_index,
            contract_size=InlineContractSpec.for_symbol(signal.symbol).trade_contract_size,
        )
        self.balance -= result.commission

    def _check_exits(self, bar_high, bar_low, bar_close, current_time, bar_index):
        if not self.positions:
            return

        spread = self._scaled_spread()
        bid, ask = estimate_bid_ask_from_bar(
            Decimal("0"), bar_high, bar_low, bar_close, spread
        )
        snapshot = MarketSnapshot(
            bid=bid, ask=ask, spread=spread,
            high=bar_high, low=bar_low, close=bar_close,
            timestamp=current_time,
        )

        exec_positions = []
        pos_map = {}
        for pos_id, pos in self.positions.items():
            exec_side = FillSide.BUY if pos.side == PositionType.LONG else FillSide.SELL
            ep = ExecPosition(
                trade_id=pos_id, symbol=pos.symbol, side=exec_side,
                entry_price=pos.entry_price, volume=pos.quantity,
                stop_loss=pos.stop_loss or Decimal("0"),
                take_profit=pos.take_profit,
                strategy_id=pos.strategy_id,
                signal_bar_index=pos.signal_bar_index,
            )
            exec_positions.append(ep)
            pos_map[pos_id] = pos

        events = self._simulator.evaluate_open_positions(
            exec_positions, snapshot, bar_high, bar_low,
        )

        for event in events:
            pos = pos_map.get(event.trade_id)
            if not pos:
                continue
            if event.event_type.value == "STOP_LOSS":
                reason = CloseReason.STOP_LOSS
            elif event.event_type.value == "TAKE_PROFIT":
                reason = CloseReason.TAKE_PROFIT
            elif event.event_type.value == "AMBIGUOUS":
                reason = CloseReason.AMBIGUOUS
            elif event.event_type.value == "TIME_STOP":
                reason = CloseReason.MANUAL
            else:
                continue

            if event.exit_price and event.exit_price > 0:
                exit_price = event.exit_price
                exit_slip = Decimal("0")
            else:
                exit_slippage = Decimal(str(self.config.slippage_pips)) * Decimal("0.01")
                exec_side = FillSide.BUY if pos.side == PositionType.LONG else FillSide.SELL
                exit_price, exit_slip = fill_simulate_exit(exec_side, bid, ask, exit_slippage)
            self._close_position(event.trade_id, exit_price, current_time, reason, exit_slip)


# ponytail: needed import at module level for BacktestPosition reference
from ..backtest.engine import BacktestPosition  # noqa: E402


class SignalStrategy:
    """Replay pre-computed signals."""

    def __init__(self, signals: List[Tuple], strategy_id: str = "liquidity_sweep"):
        self.id = strategy_id
        self._signals = list(signals)
        self._idx = 0
        self.signals_generated = 0
        self.trades_taken = 0
        self.win_count = 0
        self.loss_count = 0

    def generate_signal(self, symbol, ohlcv_data, indicators, regime, current_time, **kwargs):
        if self._idx < len(self._signals):
            bar_idx, side, entry, sl, tp = self._signals[self._idx]
            self._idx += 1
            self.signals_generated += 1
            return Signal(
                id=f"liq_{self._idx}",
                strategy_id=self.id,
                symbol=symbol,
                signal_type=SignalType.BUY if side == "BUY" else SignalType.SELL,
                timestamp=current_time,
                entry_price=Decimal(str(entry)),
                stop_loss=Decimal(str(sl)),
                take_profit=Decimal(str(tp)) if tp > 0 else None,
            )
        return None

    def required_features(self):
        return []

    def is_valid_for_regime(self, regime):
        return True

    def record_outcome(self, pnl):
        self.trades_taken += 1
        if pnl > 0:
            self.win_count += 1
        elif pnl < 0:
            self.loss_count += 1


def run_scenario(
    config: BacktestConfig,
    data: Dict[str, List],
    timestamps: List[datetime],
    signals_raw: List[Tuple],
    cost_scenario: CostScenario = BASE,
    spread_multiplier: float = 1.0,
) -> Dict[str, Any]:
    """Run engine with given cost scenario and spread multiplier."""
    strategy = SignalStrategy(signals_raw)
    engine = SpreadPatchedEngine(config, spread_multiplier=spread_multiplier)
    engine.set_strategy(strategy)

    ohlcv = {
        "open": data["open"],
        "high": data["high"],
        "low": data["low"],
        "close": data["close"],
        "volume": data["volume"],
    }
    engine.load_data(ohlcv, timestamps)
    result = engine.run()
    result["cost_scenario"] = cost_scenario.name
    result["spread_multiplier"] = spread_multiplier
    return result


def run_all_scenarios() -> Dict[str, Dict[str, Any]]:
    """Run R0-R3 scenarios. R4-R6 BLOCKED/pending."""
    from .xauusd_liquidity_sweep_fixture import get_fixture

    config, data, ts, signals = get_fixture()
    results = {}
    results["R0"] = run_scenario(config, data, ts, signals, cost_scenario=BASE, spread_multiplier=1.0)
    results["R1"] = run_scenario(config, data, ts, signals, cost_scenario=STRESS_1, spread_multiplier=1.5)
    # R2: 2.0x spread, 1.5x adverse swap
    results["R2"] = run_scenario(config, data, ts, signals, cost_scenario=STRESS_2, spread_multiplier=2.0)
    # R3: 3.0x spread, 2.0x adverse swap
    results["R3"] = run_scenario(config, data, ts, signals, cost_scenario=STRESS_3, spread_multiplier=3.0)
    return results


if __name__ == "__main__":
    results = run_all_scenarios()
    for name, r in results.items():
        trades = r.get("trades", [])
        metrics = r.get("metrics")
        total_pnl = getattr(metrics, "total_pnl", 0) if metrics else 0
        win_rate = getattr(metrics, "win_rate", 0) if metrics else 0
        print(f"{name}: {len(trades)} trades, PnL={total_pnl:.2f}, win_rate={win_rate:.1%}")
