"""
Paper Trading Script - Run strategies in paper mode with MT5

Usage:
    cd "graxia os" directory
    python graxia/packages/quant_os/run_paper_trading.py

Requirements:
    - MT5 terminal running with demo account
    - MetaTrader5 package installed
"""

import sys
import os
import asyncio
import json
from datetime import datetime, timedelta
from decimal import Decimal

# Add graxia os root to path
sys.path.insert(0, os.getcwd())

from graxia.packages.quant_os.core.config import QuantConfig, get_config
from graxia.packages.quant_os.core.enums import TradingMode, SignalType
from graxia.packages.quant_os.execution.broker_adapter import PaperBroker, MT5BrokerAdapter
from graxia.packages.quant_os.strategies.mtm import MultiTimeframeMomentum
from graxia.packages.quant_os.strategies.ensemble import EnsembleStrategy
from graxia.packages.quant_os.risk.engine import RiskEngine
from graxia.packages.quant_os.risk.kill_switch import KillSwitch
from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker
from graxia.packages.quant_os.monitoring.telegram import TelegramNotifier


class PaperTrader:
    """
    Paper trading engine that runs strategies on live data.
    """
    
    def __init__(self, config: QuantConfig = None):
        self.config = config or get_config()
        
        # Broker
        self.broker = PaperBroker()
        
        # Strategy
        self.strategy = MultiTimeframeMomentum()
        
        # Risk management
        self.kill_switch = KillSwitch()
        self.circuit_breaker = CircuitBreaker()
        self.risk_engine = RiskEngine(
            kill_switch=self.kill_switch,
            circuit_breaker=self.circuit_breaker,
        )
        
        # State
        self.is_running = False
        self.last_signal_time = None
        self.signal_cooldown = timedelta(minutes=15)
        
        # Stats
        self.total_signals = 0
        self.total_trades = 0
        self.start_time = None
    
    async def start(self, duration_minutes: int = 60):
        """Start paper trading for specified duration"""
        print("=" * 60)
        print("Quant OS - Paper Trading")
        print("=" * 60)
        
        # Connect broker
        print("\nConnecting to paper broker...")
        await self.broker.connect()
        account = await self.broker.get_account()
        print(f"Account Balance: ${account.balance:,.2f}")
        
        # Check kill switch
        if self.kill_switch.is_triggered:
            print("❌ Kill switch is triggered. Cannot start trading.")
            return
        
        self.is_running = True
        self.start_time = datetime.utcnow()
        end_time = self.start_time + timedelta(minutes=duration_minutes)
        
        print(f"\nStarting paper trading for {duration_minutes} minutes...")
        print(f"Strategy: {self.strategy.id}")
        print(f"Symbols: {self.config.symbols}")
        print(f"Max Risk/Trade: {self.config.max_risk_per_trade_pct}%")
        print(f"Press Ctrl+C to stop\n")
        
        try:
            while self.is_running and datetime.utcnow() < end_time:
                await self._trading_cycle()
                await asyncio.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            print("\n\nStopping paper trading...")
        finally:
            self.is_running = False
            await self._print_summary()
    
    async def _trading_cycle(self):
        """Single trading cycle"""
        try:
            # Check risk limits
            daily_pnl = await self.risk_engine._get_daily_pnl()
            drawdown = await self.risk_engine._get_current_drawdown()
            
            # Check kill switch auto-triggers
            self.kill_switch.check_auto_triggers(
                daily_pnl_pct=(daily_pnl / 10000) * 100,  # Simplified
                weekly_pnl_pct=0,  # Would need to calculate
                drawdown_pct=drawdown,
            )
            
            if self.kill_switch.is_triggered:
                print(f"🚨 Kill switch triggered: {self.kill_switch.state.reason}")
                return
            
            # Check circuit breaker
            if self.circuit_breaker.is_blocked:
                print(f"⚡ Circuit breaker active: {self.circuit_breaker.reason}")
                return
            
            # Check cooldown
            if self.last_signal_time:
                elapsed = datetime.utcnow() - self.last_signal_time
                if elapsed < self.signal_cooldown:
                    return
            
            # Get current prices and generate signals
            for symbol in self.config.symbols:
                await self._check_symbol(symbol)
                
        except Exception as e:
            print(f"Error in trading cycle: {e}")
    
    async def _check_symbol(self, symbol: str):
        """Check a symbol for trading signals"""
        try:
            # Get price
            price_data = await self.broker.get_price(symbol)
            if not price_data:
                return
            
            # For paper trading, we'd need historical data to generate signals
            # In a real implementation, this would fetch from MT5 or data feed
            # For now, we'll simulate with random signals for demo
            
            # Generate mock OHLCV data for signal generation
            import random
            base_price = float(price_data["mid"])
            
            # Create synthetic data for strategy
            mock_close = [base_price * (1 + random.gauss(0, 0.001)) for _ in range(250)]
            mock_high = [p * (1 + abs(random.gauss(0, 0.0005))) for p in mock_close]
            mock_low = [p * (1 - abs(random.gauss(0, 0.0005))) for p in mock_close]
            mock_volume = [1000000 * (1 + random.gauss(0, 0.3)) for _ in range(250)]
            
            ohlcv = {
                "open": mock_close,
                "high": mock_high,
                "low": mock_low,
                "close": mock_close,
                "volume": mock_volume,
            }
            
            # Generate signal
            signal = self.strategy.generate_signal(
                symbol=symbol,
                ohlcv_data=ohlcv,
                indicators=None,
                regime=None,
            )
            
            if signal and signal.signal_type in [SignalType.BUY, SignalType.SELL]:
                self.total_signals += 1
                self.last_signal_time = datetime.utcnow()
                
                # Create order
                from graxia.packages.quant_os.execution.order import Order, OrderSide, OrderType
                
                side = OrderSide.BUY if signal.signal_type == SignalType.BUY else OrderSide.SELL
                
                # Calculate position size (simplified)
                account = await self.broker.get_account()
                risk_amount = float(account.balance) * (self.config.max_risk_per_trade_pct / 100)
                
                if signal.stop_loss:
                    risk_per_unit = abs(float(signal.entry_price) - float(signal.stop_loss))
                    quantity = Decimal(str(risk_amount / risk_per_unit)) if risk_per_unit > 0 else Decimal("0.01")
                else:
                    quantity = Decimal("0.01")  # Mini lot
                
                order = Order(
                    symbol=symbol,
                    side=side,
                    order_type=OrderType.MARKET,
                    quantity=quantity,
                    stop_price=signal.stop_loss,
                    strategy_id=self.strategy.id,
                    trading_mode="PAPER",
                )
                
                # Execute
                result = await self.broker.place_order(order)
                
                if result.success:
                    self.total_trades += 1
                    print(f"✅ {side.value} {symbol} @ {result.avg_fill_price} "
                          f"(SL: {signal.stop_loss}, TP: {signal.take_profit}) "
                          f"Confidence: {signal.confidence:.2%}")
                else:
                    print(f"❌ Order rejected: {result.error_message}")
                    
        except Exception as e:
            print(f"Error checking {symbol}: {e}")
    
    async def _print_summary(self):
        """Print trading summary"""
        print("\n" + "=" * 60)
        print("PAPER TRADING SUMMARY")
        print("=" * 60)
        
        account = await self.broker.get_account()
        duration = datetime.utcnow() - self.start_time if self.start_time else timedelta(0)
        
        print(f"Duration: {duration}")
        print(f"Total Signals: {self.total_signals}")
        print(f"Total Trades: {self.total_trades}")
        print(f"Final Balance: ${account.balance:,.2f}")
        print(f"Equity: ${account.equity:,.2f}")
        print(f"P&L: ${float(account.equity - account.balance):+,.2f}")
        
        # Get positions
        positions = await self.broker.get_positions()
        print(f"Open Positions: {len(positions)}")
        
        for pos in positions:
            print(f"  {pos.symbol} {pos.position_type.value} {pos.quantity} @ {pos.avg_price} "
                  f"P&L: ${pos.unrealized_pnl:+,.2f}")
        
        print(f"\nKill Switch: {'🔴 Triggered' if self.kill_switch.is_triggered else '🟢 Armed'}")
        print(f"Circuit Breaker: {'🔴 Active' if self.circuit_breaker.is_blocked else '🟢 Closed'}")


async def main():
    """Main entry point"""
    # Configure for paper trading
    config = QuantConfig(
        trading_mode=TradingMode.PAPER,
        live_trading_enabled=False,
        max_risk_per_trade_pct=1.0,
        max_daily_loss_pct=2.0,
        max_drawdown_pct=10.0,
        paper_initial_capital=10000.0,
    )
    
    # Create trader
    trader = PaperTrader(config)
    
    # Run for 5 minutes (short demo)
    await trader.start(duration_minutes=5)


if __name__ == "__main__":
    asyncio.run(main())
