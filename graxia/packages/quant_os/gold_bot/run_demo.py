"""
Gold Bot — Demo Trading Script
เทรดเดโม่จริงผ่าน MT5

วิธีใช้:
    1. เปิด MT5 terminal แล้ว login demo account
    2. รันสคริปต์นี้
    3. Bot จะเทรด XAUUSD อัตโนมัติทุก 30 วินาที

Usage:
    cd "graxia os"
    python graxia/packages/quant_os/gold_bot/run_demo.py
"""

import sys
import os
import asyncio
import time
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, os.getcwd())

from graxia.packages.quant_os.gold_bot.core.engine import GoldBotEngine, SignalDirection
from graxia.packages.quant_os.gold_bot.core.config import BotConfig


class DemoTrader:
    """
    Demo trading engine — เชื่อมต่อ MT5 จริงแล้วเทรดเดโม่
    """
    
    def __init__(self):
        self.config = BotConfig(
            symbol="XAUUSD",
            primary_timeframe="M15",
            cycle_interval_seconds=30,
            min_score_to_trade=250,  # ลด threshold สำหรับ demo
            ai_validation_enabled=False,  # ปิด AI validation สำหรับ demo
            max_risk_per_trade_pct=0.5,
            max_daily_loss_pct=2.0,
            max_drawdown_pct=8.0,
            max_positions=2,
        )
        
        self.engine = GoldBotEngine(self.config)
        self.mt5 = None
        self.is_running = False
        self.trade_count = 0
        self.start_balance = 0
    
    async def start(self):
        """เริ่ม demo trading"""
        self._print_header()
        
        # เชื่อมต่อ MT5
        if not self._connect_mt5():
            print("\n  ❌ ไม่สามารถเชื่อมต่อ MT5 ได้")
            print("  กรุณาเปิด MT5 terminal แล้ว login demo account")
            print("  แล้วลองใหม่อีกครั้ง")
            return
        
        # แสดง account info
        self._show_account_info()
        
        # ลงทะเบียน strategies
        self.engine._register_strategies()
        
        self.is_running = True
        print(f"\n  🟢 เริ่ม demo trading...")
        print(f"  กด Ctrl+C เพื่อหยุด\n")
        
        try:
            cycle = 0
            while self.is_running:
                cycle += 1
                await self._trading_cycle(cycle)
                await asyncio.sleep(self.config.cycle_interval_seconds)
        except KeyboardInterrupt:
            print("\n\n  ⏹️  หยุด demo trading...")
        finally:
            self.is_running = False
            self._show_summary()
            self._disconnect_mt5()
    
    def _print_header(self):
        print("\n" + "=" * 60)
        print("  🏆 GOLD BOT — Demo Trading Mode")
        print("  เชื่อมต่อ MT5 จริง · เทรดเดโม่ · ไม่เสียเงินจริง")
        print("=" * 60)
    
    def _connect_mt5(self) -> bool:
        """เชื่อมต่อ MT5 terminal"""
        print("\n  📡 เชื่อมต่อ MT5...")
        
        try:
            import MetaTrader5 as mt5
            self.mt5 = mt5
            
            # ลอง initialize
            if not mt5.initialize():
                print(f"  ❌ MT5 initialize failed: {mt5.last_error()}")
                return False
            
            # ดึง account info
            account = mt5.account_info()
            if account is None:
                print(f"  ❌ ไม่สามารถดึง account info ได้")
                return False
            
            self.start_balance = account.balance
            
            print(f"  ✅ เชื่อมต่อสำเร็จ!")
            print(f"     Account: {account.login}")
            print(f"     Server: {account.server}")
            print(f"     Balance: ${account.balance:,.2f}")
            print(f"     Leverage: 1:{account.leverage}")
            
            return True
            
        except ImportError:
            print("  ❌ ไม่พบ MetaTrader5 package")
            print("  กรุณาติดตั้ง: pip install MetaTrader5")
            return False
        except Exception as e:
            print(f"  ❌ Error: {e}")
            return False
    
    def _show_account_info(self):
        """แสดง account information"""
        if not self.mt5:
            return
        
        account = self.mt5.account_info()
        if account:
            print(f"\n  📊 Account Summary:")
            print(f"     Balance:    ${account.balance:,.2f}")
            print(f"     Equity:     ${account.equity:,.2f}")
            print(f"     Free Margin: ${account.margin_free:,.2f}")
    
    async def _trading_cycle(self, cycle: int):
        """Single trading cycle"""
        try:
            # ดึงราคาปัจจุบัน
            tick = self.mt5.symbol_info_tick(self.config.symbol)
            if tick is None:
                return
            
            current_price = (tick.bid + tick.ask) / 2
            spread = tick.ask - tick.bid
            
            # สร้าง mock data จาก MT5 real data
            data = self._fetch_mt5_data()
            if not data:
                return
            
            # อัพเดท price cache
            self.engine.price_cache = {
                "bid": float(tick.bid),
                "ask": float(tick.ask),
                "mid": current_price,
                "spread": spread,
                "timestamp": datetime.utcnow(),
            }
            
            # รัน strategies
            signals = await self.engine._run_strategies(data)
            
            # Aggregate signals
            aggregated = self.engine._aggregate_signals(signals)
            
            # ตรวจสอบว่าควรเทรดหรือไม่
            if aggregated.total_score >= self.config.min_score_to_trade:
                # Risk check
                open_positions = self.mt5.positions_get(symbol=self.config.symbol)
                n_positions = len(open_positions) if open_positions else 0
                
                if n_positions >= self.config.max_positions:
                    if cycle % 10 == 0:
                        print(f"  [Cycle {cycle}] Max positions reached ({n_positions})")
                    return
                
                # สร้าง order
                await self._execute_trade(aggregated, current_price)
            
            # แสดงสถานะทุก 10 cycles
            if cycle % 10 == 0:
                account = self.mt5.account_info()
                pnl = account.equity - self.start_balance if account else 0
                active = len([s for s in self.engine.strategy_stats.values() if s['active']])
                
                print(f"  [Cycle {cycle}] "
                      f"Price: {current_price:.2f} | "
                      f"Score: {aggregated.total_score} | "
                      f"Active: {active}/13 | "
                      f"Spread: {spread:.2f} | "
                      f"P&L: ${pnl:+,.2f}")
                
        except Exception as e:
            print(f"  [Cycle {cycle}] Error: {e}")
    
    def _fetch_mt5_data(self):
        """ดึงข้อมูล OHLCV จาก MT5"""
        try:
            data = {}
            tf_map = {
                "M1": self.mt5.TIMEFRAME_M1,
                "M5": self.mt5.TIMEFRAME_M5,
                "M15": self.mt5.TIMEFRAME_M15,
                "H1": self.mt5.TIMEFRAME_H1,
                "H4": self.mt5.TIMEFRAME_H4,
            }
            
            for tf_name, tf_const in tf_map.items():
                rates = self.mt5.copy_rates_from_pos(
                    self.config.symbol, tf_const, 0, 200
                )
                
                if rates is not None and len(rates) > 0:
                    data[tf_name] = {
                        "open": [float(r["open"]) for r in rates],
                        "high": [float(r["high"]) for r in rates],
                        "low": [float(r["low"]) for r in rates],
                        "close": [float(r["close"]) for r in rates],
                        "volume": [float(r["tick_volume"]) for r in rates],
                    }
            
            return data if data else None
            
        except Exception as e:
            print(f"  Data fetch error: {e}")
            return None
    
    async def _execute_trade(self, signal, current_price):
        """Execute trade via MT5"""
        try:
            # คำนวณ position size
            account = self.mt5.account_info()
            if not account:
                return
            
            risk_amount = account.balance * (self.config.max_risk_per_trade_pct / 100)
            
            if signal.consensus_sl:
                risk_per_unit = abs(current_price - signal.consensus_sl)
                if risk_per_unit > 0:
                    lots = risk_amount / (risk_per_unit * 100)
                    lots = max(0.01, min(round(lots, 2), 1.0))
                else:
                    lots = 0.01
            else:
                lots = 0.01
            
            # สร้าง order request
            if signal.direction == SignalDirection.BUY:
                order_type = self.mt5.ORDER_TYPE_BUY
                price = self.mt5.symbol_info_tick(self.config.symbol).ask
            else:
                order_type = self.mt5.ORDER_TYPE_SELL
                price = self.mt5.symbol_info_tick(self.config.symbol).bid
            
            request = {
                "action": self.mt5.TRADE_ACTION_DEAL,
                "symbol": self.config.symbol,
                "volume": lots,
                "type": order_type,
                "price": price,
                "sl": float(signal.consensus_sl) if signal.consensus_sl else 0,
                "tp": float(signal.consensus_tp) if signal.consensus_tp else 0,
                "deviation": 20,
                "magic": 234000,
                "comment": f"GoldBot Score:{signal.total_score}",
                "type_time": self.mt5.ORDER_TIME_GTC,
                "type_filling": self.mt5.ORDER_FILLING_IOC,
            }
            
            # ส่ง order
            result = self.mt5.order_send(request)
            
            if result and result.retcode == self.mt5.TRADE_RETCODE_DONE:
                self.trade_count += 1
                side = "BUY" if signal.direction == SignalDirection.BUY else "SELL"
                print(f"\n  {'🟢' if side == 'BUY' else '🔴'} TRADE #{self.trade_count}")
                print(f"  {side} {lots} lots @ {price:.2f}")
                print(f"  SL: {signal.consensus_sl:.2f} | TP: {signal.consensus_tp:.2f}")
                print(f"  Score: {signal.total_score}")
                print(f"  Strategies: {', '.join(f'{s.strategy_name}({s.score})' for s in signal.signals[:3])}")
            else:
                error = result.comment if result else "Unknown error"
                print(f"  ❌ Order failed: {error}")
                
        except Exception as e:
            print(f"  ❌ Execution error: {e}")
    
    def _show_summary(self):
        """แสดงสรุปผล"""
        print("\n" + "=" * 60)
        print("  📊 DEMO TRADING SUMMARY")
        print("=" * 60)
        
        if self.mt5:
            account = self.mt5.account_info()
            if account:
                pnl = account.equity - self.start_balance
                pnl_pct = (pnl / self.start_balance * 100) if self.start_balance > 0 else 0
                
                print(f"\n  Balance:    ${account.balance:,.2f}")
                print(f"  Equity:     ${account.equity:,.2f}")
                print(f"  P&L:        ${pnl:+,.2f} ({pnl_pct:+.2f}%)")
                print(f"  Trades:     {self.trade_count}")
        
        # Strategy stats
        print(f"\n  Strategy Performance:")
        for name, stats in sorted(self.engine.strategy_stats.items(),
                                   key=lambda x: x[1]['signals'], reverse=True):
            if stats['signals'] > 0:
                print(f"    {name:<18} Signals: {stats['signals']}")
        
        print(f"\n  เทรดเดโม่เสร็จสิ้น")
        print(f"  ถ้าต้องการเทรดจริง ต้อง:")
        print(f"    1. ผ่าน paper trading อย่างน้อย 60 วัน")
        print(f"    2. มี trades อย่างน้อย 100 trades")
        print(f"    3. Win rate > 50% และ Profit Factor > 1.3")
        print("=" * 60)
    
    def _disconnect_mt5(self):
        """ยกเลิกการเชื่อมต่อ MT5"""
        if self.mt5:
            self.mt5.shutdown()
            print("\n  🔌 MT5 disconnected")


async def main():
    """Main entry point"""
    trader = DemoTrader()
    await trader.start()


if __name__ == "__main__":
    asyncio.run(main())
