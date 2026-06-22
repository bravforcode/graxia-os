"""
Backtest Engine - Core backtesting framework

Simulates strategy execution on historical data with:
- Realistic fill model (slippage, commission) via ExecutionSimulator
- Position tracking with SL/TP
- Equity curve generation
- Walk-forward support
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Dict, Any, List, Callable
from uuid import uuid4
import json

from ..core.enums import (
    OrderSide, OrderType, OrderStatus, PositionType, CloseReason, SignalType
)
from ..core.config import get_config
from ..core.exceptions import StrictMTFViolation
from ..core.lookahead_guard import LookaheadGuard, LookaheadViolation
from ..strategies.base import Strategy, Signal
from ..execution.execution_simulator import (
    BacktestExecutionSimulator,
    OrderIntent,
    MarketSnapshot,
    Position as ExecPosition,
    ExecutionResult,
    ContractSpec,
)
from ..execution.fill_model import ExecutionQuality, Side as FillSide, simulate_exit as fill_simulate_exit
from ..execution.conservative_bar_model import estimate_bid_ask_from_bar


@dataclass(frozen=True)
class InlineContractSpec:
    """Deterministic contract spec for backtest sizing."""
    symbol: str = ""
    trade_contract_size: Decimal = Decimal("100")
    trade_tick_size: Decimal = Decimal("0.01")
    trade_tick_value: Decimal = Decimal("1.0")
    volume_step: Decimal = Decimal("0.01")
    volume_min: Decimal = Decimal("0.01")
    volume_max: Decimal = Decimal("100")
    stops_level_points: Decimal = Decimal("0")
    snapshot_hash: str = "inline"


def _historical_size(
    equity: Decimal,
    risk_per_trade_bps: int,
    entry_price: Decimal,
    stop_loss: Decimal,
    contract: InlineContractSpec,
) -> Decimal:
    """Deterministic sizing. No MT5. No live broker."""
    if stop_loss == 0 or entry_price == 0:
        return Decimal("0")
    risk_budget = equity * Decimal(str(risk_per_trade_bps)) / Decimal("10000")
    stop_distance = abs(entry_price - stop_loss)
    if stop_distance <= 0:
        return Decimal("0")
    ticks = stop_distance / contract.trade_tick_size
    one_lot_loss = ticks * contract.trade_tick_value
    if one_lot_loss <= 0:
        return Decimal("0")
    raw_volume = risk_budget / one_lot_loss
    # ponytail: round DOWN to volume_step
    if contract.volume_step > 0:
        rounded = (raw_volume / contract.volume_step).to_integral_value(rounding=ROUND_DOWN) * contract.volume_step
    else:
        rounded = raw_volume
    if rounded < contract.volume_min:
        return Decimal("0")
    return rounded


def _exec_side(signal_type: SignalType) -> FillSide:
    """Map SignalType to fill_model Side."""
    if signal_type == SignalType.BUY:
        return FillSide.BUY
    return FillSide.SELL


@dataclass
class BacktestConfig:
    """Backtest configuration"""
    initial_capital: Decimal = Decimal("10000")
    slippage_pips: float = 0.5
    commission_per_lot: Decimal = Decimal("3.5")
    max_positions: int = 5
    risk_per_trade_bps: int = 10
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    strict_mtf: bool = True
    cost_scenario: str = "base"
    enable_swap: bool = True


@dataclass
class BacktestPosition:
    """Open position during backtest"""
    id: str
    symbol: str
    side: PositionType
    entry_price: Decimal
    quantity: Decimal
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    entry_time: Optional[datetime] = None
    strategy_id: str = ""
    unrealized_pnl: Decimal = Decimal("0")
    entry_spread_cost: Decimal = Decimal("0")
    entry_slippage_cost: Decimal = Decimal("0")
    execution_quality: str = ""
    signal_bar_index: int = -1


@dataclass
class BacktestTrade:
    """Completed trade"""
    id: str
    symbol: str
    side: PositionType
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    entry_time: datetime
    exit_time: datetime
    pnl: Decimal
    return_pct: Decimal
    fees: Decimal
    close_reason: CloseReason
    strategy_id: str = ""
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    execution_quality: str = ""
    entry_spread_cost: Decimal = Decimal("0")
    entry_slippage_cost: Decimal = Decimal("0")
    exit_slippage_cost: Decimal = Decimal("0")
    ambiguous_bar: bool = False
    signal_id: str = ""
    order_intent_id: str = ""


@dataclass
class EquityPoint:
    """Point on equity curve"""
    timestamp: datetime
    equity: float
    balance: float
    drawdown_pct: float
    open_positions: int


class BacktestEngine:
    """
    Event-driven backtesting engine.
    
    Usage:
        engine = BacktestEngine(config)
        engine.set_strategy(my_strategy)
        engine.load_data(ohlcv_data, timestamps)
        engine.set_multi_timeframe(h1_data, h1_ts, m15_data, m15_ts)  # optional
        results = engine.run()
    """
    
    def __init__(self, config: Optional[BacktestConfig] = None):
        self.config = config or BacktestConfig()
        
        # Execution simulator
        self._simulator = BacktestExecutionSimulator()
        
        # State
        self.balance = Decimal(str(self.config.initial_capital))
        self.equity = Decimal(str(self.config.initial_capital))
        self.peak_equity = Decimal(str(self.config.initial_capital))
        self.positions: Dict[str, BacktestPosition] = {}
        self.trades: List[BacktestTrade] = []
        self.equity_curve: List[EquityPoint] = []
        
        # Strategy
        self.strategy: Optional[Strategy] = None
        
        # Data
        self.ohlcv_data: Dict[str, List] = {}
        self.timestamps: List[datetime] = []
        self.current_index: int = 0
        
        # Multi-TF cursor (ponytail: set via set_multi_timeframe)
        self._mtf_cursor = None
        
        # Metrics tracking
        self._daily_pnl: float = 0.0
        self._peak_equity_pct: float = 0.0
        self._current_drawdown_pct: float = 0.0
    
    def set_strategy(self, strategy: Strategy) -> None:
        """Set the strategy to backtest"""
        self.strategy = strategy
    
    def set_multi_timeframe(
        self,
        h1_data: Dict[str, List], h1_ts: List[datetime],
        m15_data: Dict[str, List], m15_ts: List[datetime],
    ) -> None:
        """
        Set multi-timeframe data for point-in-time slicing.
        
        MUST be called before run() when strategy needs multi-TF data.
        Creates a cursor that slices lower TFs to timestamp <= current bar.
        """
        from .mtf_cursor import MultiTimeframeCursor
        self._mtf_cursor = MultiTimeframeCursor(
            d1_data=self.ohlcv_data,
            d1_ts=self.timestamps,
            h1_data=h1_data, h1_ts=h1_ts,
            m15_data=m15_data, m15_ts=m15_ts,
        )
    
    def load_data(self, data: Dict[str, List], timestamps: Optional[List[datetime]] = None) -> None:
        """
        Load OHLCV data for backtesting.
        
        Args:
            data: Dict with 'open', 'high', 'low', 'close', 'volume' lists
            timestamps: Optional list of timestamps for each bar
        """
        self.ohlcv_data = data
        self.timestamps = timestamps or []
        
        # Validate data
        required_keys = ["open", "high", "low", "close"]
        for key in required_keys:
            if key not in data:
                raise ValueError(f"Missing required data key: {key}")
        
        if not all(len(data["close"]) == len(data[k]) for k in required_keys):
            raise ValueError("All OHLCV arrays must have same length")
    
    def run(self) -> Dict[str, Any]:
        """
        Run the backtest.
        
        Returns:
            Dictionary with backtest results and metrics
        """
        if self.strategy is None:
            raise ValueError("No strategy set. Call set_strategy() first.")
        
        if not self.ohlcv_data:
            raise ValueError("No data loaded. Call load_data() first.")
        
        # Strict MTF: block static fallback if no cursor set
        if self.config.strict_mtf and self._mtf_cursor is None:
            raise StrictMTFViolation(
                "strict_mtf=True but no MTF cursor set. "
                "Call set_multi_timeframe() before run(), or set strict_mtf=False."
            )
        
        # Reset state
        self._reset()
        
        close = self.ohlcv_data["close"]
        high = self.ohlcv_data.get("high", close)
        low = self.ohlcv_data.get("low", close)
        open_price = self.ohlcv_data.get("open", close)
        volume = self.ohlcv_data.get("volume", [0] * len(close))
        
        total_bars = len(close)
        
        guard = LookaheadGuard(strict=True)
        guard.initialize(total_bars)
        
        # Main loop - iterate through each bar
        for i in range(1, total_bars):
            self.current_index = i
            guard.advance()
            current_time = self.timestamps[i] if i < len(self.timestamps) else datetime.utcnow()
            
            # Current bar OHLCV
            bar_open = Decimal(str(open_price[i]))
            bar_high = Decimal(str(high[i]))
            bar_low = Decimal(str(low[i]))
            bar_close = Decimal(str(close[i]))
            
            # 1. Check stop loss / take profit on existing positions
            self._check_exits(bar_high, bar_low, bar_close, current_time, i)
            
            # 2. Calculate indicators up to current bar
            indicators = self._calculate_indicators(i)
            
            # 3. Generate signal from strategy
            bar_data = guard.get_slice(self.ohlcv_data)
            
            # If adapter has cursor, inject sliced multi-TF data
            if self._mtf_cursor and hasattr(self.strategy, '_set_mtf_cursor'):
                sliced = self._mtf_cursor.slice_as_of(current_time)
                self.strategy._set_mtf_cursor(sliced)
            
            signal = self.strategy.generate_signal(
                symbol="BACKTEST",
                ohlcv_data=bar_data,
                indicators=indicators,
                regime=None,
                current_time=current_time,
            )
            
            # 4. Execute signal (fills on NEXT bar)
            if signal and signal.signal_type in [SignalType.BUY, SignalType.SELL]:
                self._execute_signal(signal, bar_open, bar_high, bar_low, bar_close, current_time, i)
            
            # 5. Update equity
            self._update_equity(float(bar_close), current_time)
        
        # Close any remaining positions at last price
        self._close_all_positions(close[-1], self.timestamps[-1] if self.timestamps else datetime.utcnow())
        
        return self._build_results()
    
    def _reset(self) -> None:
        """Reset engine state for a new run"""
        self.balance = Decimal(str(self.config.initial_capital))
        self.equity = Decimal(str(self.config.initial_capital))
        self.peak_equity = Decimal(str(self.config.initial_capital))
        self.positions = {}
        self.trades = []
        self.equity_curve = []
        self.current_index = 0
        self._daily_pnl = 0.0
        self._current_drawdown_pct = 0.0
    
    def _calculate_indicators(self, up_to_index: int) -> Dict[str, Any]:
        """Calculate indicators using pandas_ta if available"""
        try:
            import pandas as pd
            import pandas_ta as ta
            
            close = self.ohlcv_data["close"][:up_to_index+1]
            high = self.ohlcv_data.get("high", close)[:up_to_index+1]
            low = self.ohlcv_data.get("low", close)[:up_to_index+1]
            volume = self.ohlcv_data.get("volume", [0]*len(close))[:up_to_index+1]
            
            if len(close) < 200:
                return {}
            
            df = pd.DataFrame({
                "open": self.ohlcv_data.get("open", close)[:up_to_index+1],
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            })
            
            # EMAs
            df["ema_9"] = ta.ema(df["close"], length=9)
            df["ema_20"] = ta.ema(df["close"], length=20)
            df["ema_50"] = ta.ema(df["close"], length=50)
            df["ema_200"] = ta.ema(df["close"], length=200)
            
            # RSI and ATR
            df["rsi_14"] = ta.rsi(df["close"], length=14)
            df["atr_14"] = ta.atr(df["high"], df["low"], df["close"], length=14)
            
            # Bollinger Bands
            bb = ta.bbands(df["close"], length=20, std=2)
            if bb is not None and len(bb.columns) >= 3:
                df["bb_upper"] = bb.iloc[:, 2]  # Upper band
                df["bb_lower"] = bb.iloc[:, 0]  # Lower band
                df["bb_mid"] = bb.iloc[:, 1]    # Middle band
            
            # Volume
            df["volume_sma_20"] = df["volume"].rolling(window=20).mean()
            
            # ADX
            adx = ta.adx(df["high"], df["low"], df["close"], length=14)
            if adx is not None and len(adx.columns) >= 1:
                df["adx"] = adx.iloc[:, 0]
            
            return {col: df[col].tolist() for col in df.columns if col != "open"}
            
        except ImportError:
            return {}
        except Exception as e:
            print(f"Indicator calculation error: {e}")
            return {}
    
    def _execute_signal(
        self,
        signal: Signal,
        bar_open: Decimal,
        bar_high: Decimal,
        bar_low: Decimal,
        bar_close: Decimal,
        current_time: datetime,
        bar_index: int,
    ) -> None:
        """Execute a trading signal via ExecutionSimulator with next-bar fill."""
        if len(self.positions) >= self.config.max_positions:
            return

        for pos in self.positions.values():
            if pos.symbol == signal.symbol:
                return

        # CRITICAL: reject if no stop loss
        if not signal.stop_loss or signal.stop_loss <= 0:
            self._log_critical_incident("MISSING_SL", signal)
            return

        side = _exec_side(signal.signal_type)

        # Historical sizing — deterministic, no MT5
        entry_price = signal.entry_price or bar_close
        volume = _historical_size(
            equity=self.equity,
            risk_per_trade_bps=self.config.risk_per_trade_bps,
            entry_price=entry_price,
            stop_loss=signal.stop_loss,
            contract=InlineContractSpec(symbol=signal.symbol),
        )
        if volume <= 0:
            return

        # Build snapshot from current bar
        spread = Decimal("0.01") * Decimal("2")  # 2 pips default
        bid, ask = estimate_bid_ask_from_bar(bar_open, bar_high, bar_low, bar_close, spread)
        snapshot = MarketSnapshot(
            bid=bid, ask=ask, spread=spread,
            high=bar_high, low=bar_low, close=bar_close,
            timestamp=current_time, symbol=signal.symbol,
        )

        contract_spec = ContractSpec(
            contract_size=Decimal("100"),
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

        pos_id = str(uuid4())[:8]
        pos_side = PositionType.LONG if side == FillSide.BUY else PositionType.SHORT

        self.positions[pos_id] = BacktestPosition(
            id=pos_id, symbol=signal.symbol, side=pos_side,
            entry_price=result.entry_price, quantity=volume,
            stop_loss=signal.stop_loss, take_profit=signal.take_profit,
            entry_time=current_time,
            strategy_id=self.strategy.id if self.strategy else "",
            entry_spread_cost=result.spread_cost,
            entry_slippage_cost=result.slippage_cost,
            execution_quality=result.execution_quality.value,
            signal_bar_index=bar_index,
        )
        self.balance -= result.commission
    
    def _check_exits(
        self,
        bar_high: Decimal,
        bar_low: Decimal,
        bar_close: Decimal,
        current_time: datetime,
        bar_index: int,
    ) -> None:
        """Check stop loss and take profit on all open positions using fill_model."""
        if not self.positions:
            return

        spread = Decimal("0.01") * Decimal("2")
        bid, ask = estimate_bid_ask_from_bar(
            Decimal("0"), bar_high, bar_low, bar_close, spread
        )
        snapshot = MarketSnapshot(
            bid=bid,
            ask=ask,
            spread=spread,
            high=bar_high,
            low=bar_low,
            close=bar_close,
            timestamp=current_time,
        )

        exec_positions = []
        pos_map = {}
        for pos_id, pos in self.positions.items():
            exec_side = FillSide.BUY if pos.side == PositionType.LONG else FillSide.SELL
            ep = ExecPosition(
                trade_id=pos_id,
                symbol=pos.symbol,
                side=exec_side,
                entry_price=pos.entry_price,
                volume=pos.quantity,
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
            pos_id = event.trade_id
            pos = pos_map.get(pos_id)
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

            exit_slippage = Decimal(str(self.config.slippage_pips)) * Decimal("0.01")
            exec_side = FillSide.BUY if pos.side == PositionType.LONG else FillSide.SELL
            exit_price, exit_slip = fill_simulate_exit(exec_side, bid, ask, exit_slippage)

            self._close_position(pos_id, exit_price, current_time, reason, exit_slip)
    
    def _close_position(
        self,
        pos_id: str,
        exit_price: Decimal,
        exit_time: datetime,
        reason: CloseReason,
        exit_slippage_cost: Decimal = Decimal("0"),
    ) -> None:
        """Close a position and record the trade with full execution quality info."""
        pos = self.positions.pop(pos_id, None)
        if not pos:
            return

        # Calculate P&L
        if pos.side == PositionType.LONG:
            pnl = (exit_price - pos.entry_price) * pos.quantity
        else:
            pnl = (pos.entry_price - exit_price) * pos.quantity

        # Commission on exit
        lots = pos.quantity / Decimal("100")
        exit_commission = lots * Decimal(str(self.config.commission_per_lot))
        total_fees = exit_commission

        pnl -= total_fees
        self.balance += pnl

        notional = pos.entry_price * pos.quantity
        return_pct = (pnl / notional * 100) if notional > 0 else Decimal("0")

        is_ambiguous = reason == CloseReason.AMBIGUOUS

        self.trades.append(BacktestTrade(
            id=pos.id,
            symbol=pos.symbol,
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            quantity=pos.quantity,
            entry_time=pos.entry_time or datetime.utcnow(),
            exit_time=exit_time,
            pnl=pnl,
            return_pct=return_pct,
            fees=total_fees,
            close_reason=reason,
            strategy_id=pos.strategy_id,
            stop_loss=pos.stop_loss,
            take_profit=pos.take_profit,
            execution_quality=pos.execution_quality,
            entry_spread_cost=pos.entry_spread_cost,
            entry_slippage_cost=pos.entry_slippage_cost,
            exit_slippage_cost=exit_slippage_cost,
            ambiguous_bar=is_ambiguous,
        ))
    
    def _close_all_positions(self, last_price: float, current_time: datetime) -> None:
        """Close all remaining positions at last price"""
        last_dec = Decimal(str(last_price))
        for pos_id in list(self.positions.keys()):
            self._close_position(pos_id, last_dec, current_time, CloseReason.MANUAL)

    def _log_critical_incident(self, incident_type: str, signal=None):
        """Log critical incident. No silent fallback."""
        import logging
        logging.critical(f"CRITICAL_INCIDENT: {incident_type} signal={signal}")

    def _bar_dicts(self) -> List[dict]:
        """Convert loaded OHLCV arrays to list-of-dicts for the simulator."""
        n = len(self.ohlcv_data["close"])
        bars = []
        for i in range(n):
            bars.append({
                "open": Decimal(str(self.ohlcv_data["open"][i])),
                "high": Decimal(str(self.ohlcv_data["high"][i])),
                "low": Decimal(str(self.ohlcv_data["low"][i])),
                "close": Decimal(str(self.ohlcv_data["close"][i])),
            })
        return bars
    
    def _update_equity(self, current_price: float, current_time: datetime) -> None:
        """Update equity curve point"""
        # Calculate unrealized P&L
        unrealized = Decimal("0")
        for pos in self.positions.values():
            current = Decimal(str(current_price))
            if pos.side == PositionType.LONG:
                unrealized += (current - pos.entry_price) * pos.quantity
            else:
                unrealized += (pos.entry_price - current) * pos.quantity
        
        self.equity = self.balance + unrealized
        
        # Update peak and drawdown
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity
        
        if self.peak_equity > 0:
            drawdown = (self.peak_equity - self.equity) / self.peak_equity * 100
            self._current_drawdown_pct = float(drawdown)
        
        self.equity_curve.append(EquityPoint(
            timestamp=current_time,
            equity=float(self.equity),
            balance=float(self.balance),
            drawdown_pct=self._current_drawdown_pct,
            open_positions=len(self.positions),
        ))
    
    def _build_results(self) -> Dict[str, Any]:
        """Build final results dictionary"""
        from .metrics import calculate_metrics
        
        metrics = calculate_metrics(
            trades=self.trades,
            initial_capital=self.config.initial_capital,
            equity_curve=self.equity_curve,
        )
        
        # Execution quality breakdown
        total_spread_cost = sum(t.entry_spread_cost for t in self.trades)
        total_slippage_cost = sum(
            t.entry_slippage_cost + t.exit_slippage_cost for t in self.trades
        )
        quality_counts: Dict[str, int] = {}
        for t in self.trades:
            q = t.execution_quality or "unknown"
            quality_counts[q] = quality_counts.get(q, 0) + 1
        
        result = {
            "config": {
                "initial_capital": float(self.config.initial_capital),
                "slippage_pips": self.config.slippage_pips,
                "commission_per_lot": float(self.config.commission_per_lot),
                "risk_per_trade_bps": self.config.risk_per_trade_bps,
                "strategy": self.strategy.id if self.strategy else "unknown",
            },
            "metrics": metrics,
            "trades": [
                {
                    "id": t.id,
                    "symbol": t.symbol,
                    "side": t.side.value,
                    "entry_price": float(t.entry_price),
                    "exit_price": float(t.exit_price),
                    "quantity": float(t.quantity),
                    "stop_loss": float(t.stop_loss) if t.stop_loss else None,
                    "take_profit": float(t.take_profit) if t.take_profit else None,
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat(),
                    "pnl": float(t.pnl),
                    "return_pct": float(t.return_pct),
                    "fees": float(t.fees),
                    "close_reason": t.close_reason.value,
                    "strategy_id": t.strategy_id,
                    "execution_quality": t.execution_quality,
                    "entry_spread_cost": float(t.entry_spread_cost),
                    "entry_slippage_cost": float(t.entry_slippage_cost),
                    "exit_slippage_cost": float(t.exit_slippage_cost),
                    "ambiguous_bar": t.ambiguous_bar,
                }
                for t in self.trades
            ],
            "equity_curve": [
                {
                    "timestamp": p.timestamp.isoformat(),
                    "equity": p.equity,
                    "balance": p.balance,
                    "drawdown_pct": p.drawdown_pct,
                    "open_positions": p.open_positions,
                }
                for p in self.equity_curve[::max(1, len(self.equity_curve)//500)]  # Downsample
            ],
            "execution": {
                "total_spread_cost": float(total_spread_cost),
                "total_slippage_cost": float(total_slippage_cost),
                "quality_breakdown": quality_counts,
            },
        }
        
        return result
