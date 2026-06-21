"""
Backtest Engine - Core backtesting framework

Simulates strategy execution on historical data with:
- Realistic fill model (slippage, commission)
- Position tracking with SL/TP
- Equity curve generation
- Walk-forward support
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Dict, Any, List, Callable
from uuid import uuid4
import json

from ..core.enums import (
    OrderSide, OrderType, OrderStatus, PositionType, CloseReason, SignalType
)
from ..core.config import get_config
from ..core.lookahead_guard import LookaheadGuard, LookaheadViolation
from ..strategies.base import Strategy, Signal


@dataclass
class BacktestConfig:
    """Backtest configuration"""
    initial_capital: float = 10000.0
    slippage_pips: float = 0.5
    commission_per_lot: float = 3.5
    max_positions: int = 5
    risk_per_trade_pct: float = 1.0
    units_per_lot: float = 100000.0
    start_date: Optional[date] = None
    end_date: Optional[date] = None


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
        engine.load_data(ohlcv_data)
        results = engine.run()
    """
    
    def __init__(self, config: Optional[BacktestConfig] = None):
        self.config = config or BacktestConfig()
        
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
        
        # Metrics tracking
        self._daily_pnl: float = 0.0
        self._peak_equity_pct: float = 0.0
        self._current_drawdown_pct: float = 0.0
    
    def set_strategy(self, strategy: Strategy) -> None:
        """Set the strategy to backtest"""
        self.strategy = strategy
    
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
            
            # 1. Check stop loss / take profit on existing positions
            self._check_exits(high[i], low[i], close[i], current_time)
            
            # 2. Calculate indicators up to current bar
            indicators = self._calculate_indicators(i)
            
            # 3. Generate signal from strategy
            bar_data = guard.get_slice(self.ohlcv_data)
            
            signal = self.strategy.generate_signal(
                symbol="BACKTEST",
                ohlcv_data=bar_data,
                indicators=indicators,
                regime=None
            )
            
            # 4. Execute signal
            if signal and signal.signal_type in [SignalType.BUY, SignalType.SELL]:
                self._execute_signal(signal, close[i], current_time)
            
            # 5. Update equity
            self._update_equity(close[i], current_time)
        
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
    
    def _execute_signal(self, signal: Signal, current_price: float, current_time: datetime) -> None:
        """Execute a trading signal"""
        # Check max positions
        if len(self.positions) >= self.config.max_positions:
            return
        
        # Check if already have position in this symbol
        for pos in self.positions.values():
            if pos.symbol == signal.symbol:
                return
        
        # Calculate position size based on risk
        entry_price = Decimal(str(current_price))
        
        if signal.stop_loss:
            risk_per_unit = abs(entry_price - signal.stop_loss)
            # Safety net: reject SL too tight (ponytail: per-symbol minimum, not optimization)
            min_sl = Decimal("10.0") if "XAU" in signal.symbol else Decimal("0.0010")
            if risk_per_unit < min_sl:
                return
            if risk_per_unit <= 0:
                return
            risk_amount = self.balance * Decimal(str(self.config.risk_per_trade_pct)) / 100
            quantity = risk_amount / risk_per_unit
        else:
            # Default: risk 1% of balance with 50 pip stop
            pip_value = Decimal("0.01") if "JPY" in signal.symbol else Decimal("0.0001")
            risk_per_unit = pip_value * 50
            risk_amount = self.balance * Decimal(str(self.config.risk_per_trade_pct)) / 100
            quantity = risk_amount / risk_per_unit if risk_per_unit > 0 else Decimal("0")
        
        if quantity <= 0:
            return
        
        # Cap position size: max 50% of capital at risk (ponytail: sanity check, not optimization)
        max_notional = self.balance * Decimal("0.5")
        max_quantity = max_notional / entry_price if entry_price > 0 else Decimal("0")
        if quantity > max_quantity:
            quantity = max_quantity
        
        # Apply slippage
        slippage_pips = Decimal(str(self.config.slippage_pips))
        pip_value = Decimal("0.01") if "JPY" in signal.symbol else Decimal("0.0001")
        slippage = slippage_pips * pip_value
        
        if signal.signal_type == SignalType.BUY:
            fill_price = entry_price + slippage
            pos_side = PositionType.LONG
        else:
            fill_price = entry_price - slippage
            pos_side = PositionType.SHORT
        
        # Calculate commission
        lots = quantity / Decimal(str(self.config.units_per_lot))
        commission = lots * Decimal(str(self.config.commission_per_lot))
        self.balance -= commission
        
        # Create position
        pos_id = str(uuid4())[:8]
        self.positions[pos_id] = BacktestPosition(
            id=pos_id,
            symbol=signal.symbol,
            side=pos_side,
            entry_price=fill_price,
            quantity=quantity,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            entry_time=current_time,
            strategy_id=self.strategy.id if self.strategy else "",
        )
    
    def _check_exits(self, high: float, low: float, close: float, current_time: datetime) -> None:
        """Check stop loss and take profit on all open positions"""
        to_close = []
        
        for pos_id, pos in self.positions.items():
            high_dec = Decimal(str(high))
            low_dec = Decimal(str(low))
            
            # Check stop loss
            if pos.stop_loss:
                if pos.side == PositionType.LONG and low_dec <= pos.stop_loss:
                    to_close.append((pos_id, pos.stop_loss, CloseReason.STOP_LOSS))
                    continue
                elif pos.side == PositionType.SHORT and high_dec >= pos.stop_loss:
                    to_close.append((pos_id, pos.stop_loss, CloseReason.STOP_LOSS))
                    continue
            
            # Check take profit
            if pos.take_profit:
                if pos.side == PositionType.LONG and high_dec >= pos.take_profit:
                    to_close.append((pos_id, pos.take_profit, CloseReason.TAKE_PROFIT))
                    continue
                elif pos.side == PositionType.SHORT and low_dec <= pos.take_profit:
                    to_close.append((pos_id, pos.take_profit, CloseReason.TAKE_PROFIT))
                    continue
        
        # Execute closes
        for pos_id, exit_price, reason in to_close:
            self._close_position(pos_id, exit_price, current_time, reason)
    
    def _close_position(self, pos_id: str, exit_price: Decimal, exit_time: datetime, reason: CloseReason) -> None:
        """Close a position and record the trade"""
        pos = self.positions.pop(pos_id, None)
        if not pos:
            return
        
        # Calculate P&L
        if pos.side == PositionType.LONG:
            pnl = (exit_price - pos.entry_price) * pos.quantity
        else:
            pnl = (pos.entry_price - exit_price) * pos.quantity
        
        # Commission on exit
        lots = pos.quantity / Decimal(str(self.config.units_per_lot))
        exit_commission = lots * Decimal(str(self.config.commission_per_lot))
        pnl -= exit_commission
        
        # Update balance
        self.balance += pnl
        
        # Calculate return %
        notional = pos.entry_price * pos.quantity
        return_pct = (pnl / notional * 100) if notional > 0 else Decimal("0")
        
        # Record trade
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
            fees=exit_commission,
            close_reason=reason,
            strategy_id=pos.strategy_id,
            stop_loss=pos.stop_loss,
        ))
    
    def _close_all_positions(self, last_price: float, current_time: datetime) -> None:
        """Close all remaining positions"""
        for pos_id in list(self.positions.keys()):
            self._close_position(pos_id, Decimal(str(last_price)), current_time, CloseReason.MANUAL)
    
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
        
        return {
            "config": {
                "initial_capital": self.config.initial_capital,
                "slippage_pips": self.config.slippage_pips,
                "commission_per_lot": self.config.commission_per_lot,
                "risk_per_trade_pct": self.config.risk_per_trade_pct,
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
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat(),
                    "pnl": float(t.pnl),
                    "return_pct": float(t.return_pct),
                    "fees": float(t.fees),
                    "close_reason": t.close_reason.value,
                    "strategy_id": t.strategy_id,
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
        }
