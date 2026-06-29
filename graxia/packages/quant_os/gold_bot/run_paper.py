"""
Gold Bot Paper Trading Runner — 1000 Cent test.

Uses PaperBroker (in-memory simulation) with live MT5 price feeds.
Reads real XAUUSD prices but executes everything locally.

Usage:
    python -m gold_bot.run_paper --duration 168  # 7 days
    python -m gold_bot.run_paper --duration 0    # Until stopped
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Ensure project root is on path (monorepo root)
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass


def _log(msg: str):
    """Print with guaranteed flush for pythonw background mode."""
    print(msg, flush=True)


@dataclass
class PaperConfig:
    """Paper trading configuration — conservative tuning."""
    symbol: str = "XAUUSD"
    timeframes: list[str] = field(default_factory=lambda: ["M1", "M5", "M15", "H1", "H4"])
    primary_timeframe: str = "M15"
    cycle_interval_seconds: int = 30
    
    # Capital: $49,911.92 (1000 Cent equivalent)
    initial_capital: float = 49911.92
    
    # Risk: ultra-conservative for first 3 days
    max_risk_per_trade_pct: float = 0.25   # 0.25% per trade (halved)
    max_daily_loss_pct: float = 2.0        # 2% daily limit
    max_drawdown_pct: float = 8.0          # 8% max drawdown
    max_positions: int = 1                 # Only 1 position at a time
    max_position_size_lots: float = 0.05   # 0.05 lot (5 oz) — halved
    units_per_lot: float = 100.0
    
    # Dynamic SL/TP — 1:2 RR
    sl_distance_points: float = 37.0   # SL: 35-40 points from entry
    risk_reward_ratio: float = 2.0     # TP: 2x SL distance
    
    # Scoring — high conviction only
    min_score_to_trade: int = 350      # Only high-conviction signals (up from 280)
    min_active_strategies: int = 3
    
    # AI validation — enabled
    ai_validation_enabled: bool = True
    
    # Breakeven
    breakeven_trigger_pips: float = 30.0
    
    # Cooldown — 5 minutes between trades
    cooldown_cycles: int = 10          # 10 * 30s = 5 min (up from 4 cycles / 2 min)
    
    # Logging
    log_dir: str = "logs"
    report_interval_cycles: int = 480  # Every 4 hours


class PaperTrader:
    """
    Paper trading engine for gold_bot.
    
    Flow:
        1. Connect to MT5 for live price feeds
        2. Run 13 strategies every 30 seconds
        3. Execute on PaperBroker (in-memory)
        4. Log all trades to CSV + JSON
        5. Send Telegram reports every 4 hours
    """
    
    def __init__(self, config: PaperConfig):
        self.config = config
        self.broker = None  # PaperBroker
        self.mt5_connected = False
        self.engine = None  # GoldBotEngine
        
        # State
        self.is_running = False
        self.cycle_count = 0
        self.start_time = None
        self.trades: list[dict] = []
        self.daily_pnl: float = 0.0
        self.peak_equity: float = config.initial_capital
        self._last_signal_key: str = ""  # Cooldown: prevent duplicate signals
        self._last_trade_cycle: int = 0  # Cycle when last trade was executed
        self._cooldown_cycles: int = config.cooldown_cycles  # Default 10 cycles (5 min)
        
        # Logging
        self.log_dir = Path(config.log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.csv_file = None
        self.csv_writer = None
    
    async def start(self):
        """Start paper trading."""
        _log("=" * 70)
        _log("  GOLD BOT — Paper Trading (1000 Cent)")
        _log("  Live Prices from MT5 | Execution on PaperBroker")
        _log("=" * 70)
        
        # Initialize MT5 connection for price feeds
        await self._init_mt5()
        
        # Initialize PaperBroker
        await self._init_paper_broker()
        
        # Initialize gold_bot engine
        await self._init_engine()
        
        # Setup CSV logging
        self._setup_logging()
        
        self.is_running = True
        self.start_time = datetime.now(timezone.utc)
        
        _log(f"\n  Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        _log(f"  Symbol: {self.config.symbol}")
        _log(f"  Capital: ${self.config.initial_capital:,.2f}")
        _log(f"  Risk/Trade: {self.config.max_risk_per_trade_pct}%")
        _log(f"  Max DD: {self.config.max_drawdown_pct}%")
        _log(f"  Max Positions: {self.config.max_positions}")
        _log(f"  Lot Size: {self.config.max_position_size_lots}")
        _log(f"  SL Distance: {self.config.sl_distance_points} pts")
        _log(f"  RR Ratio: 1:{self.config.risk_reward_ratio}")
        _log(f"  AI Validation: {'ON' if self.config.ai_validation_enabled else 'OFF'}")
        _log(f"  Cooldown: {self.config.cooldown_cycles * self.config.cycle_interval_seconds}s")
        _log(f"  Cycle: {self.config.cycle_interval_seconds}s")
        _log(f"  Min Score: {self.config.min_score_to_trade}")
        _log(f"\n  Press Ctrl+C to stop\n")
        
        try:
            while self.is_running:
                await self._trading_cycle()
                await asyncio.sleep(self.config.cycle_interval_seconds)
        except KeyboardInterrupt:
            _log("\n\n  Stopping paper trader...")
        finally:
            self.is_running = False
            await self._print_summary()
            self._save_summary()
    
    async def _init_mt5(self):
        """Connect to MT5 for live price feeds with retry logic."""
        try:
            import MetaTrader5 as mt5
            
            path = os.getenv("MT5_PATH", r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe")
            login = int(os.getenv("MT5_LOGIN", "0"))
            password = os.getenv("MT5_PASSWORD", "")
            server = os.getenv("MT5_SERVER", "Pepperstone-Demo")
            timeout = int(os.getenv("MT5_TIMEOUT_MS", "60000"))
            
            # Retry up to 3 times with 10s delay
            for attempt in range(1, 4):
                if login > 0 and password:
                    ok = mt5.initialize(path=path, login=login, password=password,
                                        server=server, timeout=timeout)
                else:
                    ok = mt5.initialize(path=path, timeout=timeout)
                
                if ok:
                    info = mt5.account_info()
                    if info:
                        _log(f"  MT5 Connected: {info.server} | Balance: ${info.balance:,.2f}")
                        self.mt5_connected = True
                        return
                    else:
                        _log(f"  MT5 init OK but no account info (attempt {attempt})")
                else:
                    err = mt5.last_error()
                    _log(f"  MT5 init failed (attempt {attempt}): {err}")
                
                if attempt < 3:
                    _log(f"  Retrying in 10s...")
                    await asyncio.sleep(10)
            
            _log("  MT5: All connection attempts failed — running without MT5")
        
        except ImportError:
            _log("  MT5 Python package not installed")
        except Exception as e:
            _log(f"  MT5 connection error: {e}")
    
    async def _init_paper_broker(self):
        """Initialize PaperBroker."""
        from graxia.packages.quant_os.execution.broker_adapter import PaperBroker
        
        self.broker = PaperBroker()
        await self.broker.connect()
        
        # Override initial capital
        from decimal import Decimal
        self.broker.account.balance = Decimal(str(self.config.initial_capital))
        self.broker.account.equity = Decimal(str(self.config.initial_capital))
        self.broker.account.free_margin = Decimal(str(self.config.initial_capital))
        
        _log(f"  PaperBroker: ${self.config.initial_capital:,.2f} initial capital")
    
    async def _init_engine(self):
        """Initialize gold_bot engine with PaperBroker."""
        from graxia.packages.quant_os.gold_bot.core.engine import GoldBotEngine
        from graxia.packages.quant_os.gold_bot.core.config import BotConfig
        
        bot_config = BotConfig(
            symbol=self.config.symbol,
            primary_timeframe=self.config.primary_timeframe,
            timeframes=self.config.timeframes,
            cycle_interval_seconds=self.config.cycle_interval_seconds,
            min_score_to_trade=self.config.min_score_to_trade,
            min_active_strategies=self.config.min_active_strategies,
            initial_capital=self.config.initial_capital,
            max_risk_per_trade_pct=self.config.max_risk_per_trade_pct,
            max_daily_loss_pct=self.config.max_daily_loss_pct,
            max_drawdown_pct=self.config.max_drawdown_pct,
            max_positions=self.config.max_positions,
            max_position_size_lots=self.config.max_position_size_lots,
            units_per_lot=self.config.units_per_lot,
            breakeven_trigger_pips=self.config.breakeven_trigger_pips,
            ai_validation_enabled=self.config.ai_validation_enabled,
            sl_distance_points=self.config.sl_distance_points,
            risk_reward_ratio=self.config.risk_reward_ratio,
        )
        
        self.engine = GoldBotEngine(bot_config)
        
        # Inject PaperBroker instead of MT5BrokerAdapter
        self.engine.broker = self.broker
        
        # Register strategies
        self.engine._register_strategies()
        
        _log(f"  Engine: {len(self.engine.strategies)} strategies loaded")
    
    def _setup_logging(self):
        """Setup CSV and JSON logging."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = self.log_dir / f"paper_trades_{timestamp}.csv"
        
        self.csv_file = open(csv_path, "w", newline="")
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow([
            "timestamp", "direction", "entry", "exit", "sl", "tp",
            "quantity", "pnl", "pnl_pct", "score", "strategies", "status"
        ])
        
        _log(f"  Logging to: {csv_path}")
    
    async def _trading_cycle(self):
        """Single trading cycle."""
        cycle_start = time.time()
        self.cycle_count += 1
        
        try:
            # MT5 health check — attempt reconnect if disconnected
            if not self.mt5_connected:
                try:
                    import MetaTrader5 as mt5
                    info = mt5.account_info()
                    if info:
                        self.mt5_connected = True
                        _log(f"  [RECONNECT] MT5 restored: {info.server}")
                except Exception:
                    pass
            
            if not self.mt5_connected:
                _log(f"  [Cycle {self.cycle_count}] MT5 disconnected, skipping")
                return
            
            # Sync live MT5 prices to PaperBroker
            await self._sync_prices()
            
            # Check open trades using MT5 tick directly (PaperBroker has no get_tick)
            self._check_open_trades_mt5()
            
            # Fetch data directly from MT5 (PaperBroker has no get_bars)
            data = self._fetch_mt5_data()
            if not data:
                return
            
            signals = await self.engine._run_strategies(data)
            aggregated = self.engine._aggregate_signals(signals)
            
            # Update league
            self.engine.league.update(self.engine.strategy_stats)
            
            # Check score threshold
            if aggregated.total_score >= self.config.min_score_to_trade:
                # Cooldown: skip if too soon since last trade
                if (self.cycle_count - self._last_trade_cycle) < self._cooldown_cycles:
                    return
                
                # Risk check
                risk_result = self.engine.risk_bridge.check(
                    signal=aggregated,
                    open_trades=self.engine.open_trades,
                    daily_pnl=self.daily_pnl,
                    balance=self.config.initial_capital + self.daily_pnl,
                    equity=self.config.initial_capital + self.daily_pnl,
                )
                
                if risk_result.approved:
                    await self.engine._execute_signal(aggregated)
                    self._last_trade_cycle = self.cycle_count
                    self._log_last_trade(aggregated)
            
            # Heartbeat every 10 cycles (5 min) — shows bot is alive
            if self.cycle_count % 10 == 0:
                _log(f"  [Heartbeat] Cycle {self.cycle_count} | "
                     f"MT5: {'ON' if self.mt5_connected else 'OFF'} | "
                     f"Open: {len(self.engine.open_trades)} | "
                     f"Closed: {len(self.engine.closed_trades)}")
            
            # Periodic report
            if self.cycle_count % self.config.report_interval_cycles == 0:
                self._print_status()
        
        except Exception as e:
            _log(f"  [Cycle {self.cycle_count}] Error: {e}")
    
    async def _sync_prices(self):
        """Sync live MT5 prices to PaperBroker."""
        if not self.mt5_connected:
            return
        
        try:
            import MetaTrader5 as mt5
            
            tick = mt5.symbol_info_tick(self.config.symbol)
            if tick:
                from decimal import Decimal
                self.broker.prices[self.config.symbol] = {
                    "bid": Decimal(str(tick.bid)),
                    "ask": Decimal(str(tick.ask)),
                    "mid": Decimal(str((tick.bid + tick.ask) / 2)),
                }
        except Exception:
            pass
    
    def _fetch_mt5_data(self) -> dict:
        """Fetch OHLCV data directly from MT5 for all timeframes."""
        if not self.mt5_connected:
            return None
        
        try:
            import MetaTrader5 as mt5
            
            data = {}
            for tf in self.config.timeframes:
                # MT5 timeframe mapping
                tf_map = {
                    "M1": mt5.TIMEFRAME_M1,
                    "M5": mt5.TIMEFRAME_M5,
                    "M15": mt5.TIMEFRAME_M15,
                    "H1": mt5.TIMEFRAME_H1,
                    "H4": mt5.TIMEFRAME_H4,
                }
                mt5_tf = tf_map.get(tf)
                if not mt5_tf:
                    continue
                
                rates = mt5.copy_rates_from_pos(self.config.symbol, mt5_tf, 0, 200)
                if rates is not None and len(rates) > 0:
                    data[tf] = {
                        "open": [float(r["open"]) for r in rates],
                        "high": [float(r["high"]) for r in rates],
                        "low": [float(r["low"]) for r in rates],
                        "close": [float(r["close"]) for r in rates],
                        "volume": [float(r["tick_volume"]) for r in rates],
                        "timestamps": [r["time"] for r in rates],
                    }
            
            # Update price cache
            tick = mt5.symbol_info_tick(self.config.symbol)
            if tick:
                self.engine.price_cache = {
                    "bid": float(tick.bid),
                    "ask": float(tick.ask),
                    "mid": float((tick.bid + tick.ask) / 2),
                    "spread": float(tick.ask - tick.bid),
                }
            
            return data if data else None
        
        except Exception as e:
            _log(f"  MT5 data fetch error: {e}")
            return None
    
    def _check_open_trades_mt5(self):
        """Check open trades for SL/TP hits using MT5 tick data."""
        if not self.engine.open_trades:
            return
        
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return
        
        if not self.mt5_connected:
            return
        
        try:
            tick = mt5.symbol_info_tick(self.config.symbol)
            if not tick:
                return
        except Exception:
            return
        
        try:
            from graxia.packages.quant_os.gold_bot.core.engine import SignalDirection
            current_price = float((tick.bid + tick.ask) / 2)
            to_close = []
            
            for trade in self.engine.open_trades:
                try:
                    if trade.direction == SignalDirection.BUY and current_price <= trade.stop_loss:
                        to_close.append((trade, current_price, "SL"))
                    elif trade.direction == SignalDirection.SELL and current_price >= trade.stop_loss:
                        to_close.append((trade, current_price, "SL"))
                    elif trade.direction == SignalDirection.BUY and current_price >= trade.take_profit:
                        to_close.append((trade, current_price, "TP"))
                    elif trade.direction == SignalDirection.SELL and current_price <= trade.take_profit:
                        to_close.append((trade, current_price, "TP"))
                except Exception:
                    continue
            
            for trade, exit_price, reason in to_close:
                try:
                    if trade.direction == SignalDirection.BUY:
                        pnl_pips = (exit_price - trade.entry_price) / 0.01
                    else:
                        pnl_pips = (trade.entry_price - exit_price) / 0.01
                    pnl_dollars = pnl_pips * trade.quantity * (self.config.units_per_lot / 100)
                    
                    trade.exit_price = exit_price
                    trade.pnl = pnl_dollars
                    trade.status = "CLOSED"
                    self.engine.open_trades.remove(trade)
                    self.engine.closed_trades.append(trade)
                    self.daily_pnl += pnl_dollars
                    
                    is_win = pnl_dollars > 0
                    emoji = "[WIN]" if is_win else "[LOSS]"
                    _log(f"  {emoji} CLOSED ({reason}): {trade.entry_price:.2f} -> {exit_price:.2f} P&L=${pnl_dollars:+.2f}")
                    self.csv_writer.writerow([
                        trade.entry_time.isoformat(),
                        trade.direction.value,
                        f"{trade.entry_price:.2f}",
                        f"{exit_price:.2f}",
                        f"{trade.stop_loss:.2f}",
                        f"{trade.take_profit:.2f}",
                        f"{trade.quantity:.2f}",
                        f"{pnl_dollars:+.2f}",
                        "",
                        "",
                        ",".join(trade.strategy_scores.keys()),
                        reason
                    ])
                    self.csv_file.flush()
                except Exception as e:
                    _log(f"  [CLOSE] Error closing trade: {e}")
        except Exception as e:
            _log(f"  [CHECK] Error checking trades: {e}")
    
    def _update_pnl_tracking(self):
        """Update daily P&L and peak equity."""
        unrealized = sum(
            float(p.unrealized_pnl) 
            for p in self.broker.positions.values()
        )
        current_equity = self.config.initial_capital + self.daily_pnl + unrealized
        
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
    
    def _log_last_trade(self, signal):
        """Log the last executed trade to CSV."""
        if not self.engine.open_trades:
            return
        
        trade = self.engine.open_trades[-1]
        self.csv_writer.writerow([
            trade.entry_time.isoformat(),
            trade.direction.value,
            f"{trade.entry_price:.2f}",
            "",  # Exit price (filled later)
            f"{trade.stop_loss:.2f}",
            f"{trade.take_profit:.2f}",
            f"{trade.quantity:.2f}",
            "",  # PnL (filled later)
            "",
            signal.total_score,
            ",".join(trade.strategy_scores.keys()),
            "OPEN"
        ])
        self.csv_file.flush()
    
    def _print_status(self):
        """Print periodic status."""
        elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds() / 3600
        wins = sum(1 for t in self.engine.closed_trades if t.pnl > 0)
        total = len(self.engine.closed_trades)
        win_rate = (wins / total * 100) if total > 0 else 0
        total_pnl = sum(t.pnl for t in self.engine.closed_trades)
        
        active = sum(1 for s in self.engine.strategy_stats.values() if s['active'])
        benched = [n for n, s in self.engine.strategy_stats.items() if s.get('league_tier') == 'BENCH']
        
        _log(f"\n  [{elapsed:.1f}h] Cycle {self.cycle_count} | "
              f"Trades: {total} | Win: {win_rate:.0f}% | "
              f"P&L: ${total_pnl:+,.2f} | "
              f"Active: {active}/13 | "
              f"Benched: {','.join(benched) if benched else 'none'}")
    
    async def _print_summary(self):
        """Print final summary."""
        elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds() / 3600
        
        _log("\n" + "=" * 70)
        _log("  GOLD BOT — Paper Trading Summary")
        _log("=" * 70)
        
        _log(f"\n  Duration: {elapsed:.1f} hours")
        _log(f"  Total Cycles: {self.cycle_count}")
        _log(f"  Open Trades: {len(self.engine.open_trades)}")
        _log(f"  Closed Trades: {len(self.engine.closed_trades)}")
        
        if self.engine.closed_trades:
            wins = sum(1 for t in self.engine.closed_trades if t.pnl > 0)
            losses = len(self.engine.closed_trades) - wins
            total_pnl = sum(t.pnl for t in self.engine.closed_trades)
            win_rate = wins / len(self.engine.closed_trades) * 100
            
            _log(f"\n  Performance:")
            _log(f"  Win Rate: {win_rate:.1f}% ({wins}W / {losses}L)")
            _log(f"  Total P&L: ${total_pnl:+,.2f}")
            _log(f"  Avg P&L/Trade: ${total_pnl / len(self.engine.closed_trades):+,.2f}")
        
        _log(f"\n  League Status:")
        for tier in ["S", "A", "B", "C", "BENCH"]:
            members = [n for n, s in self.engine.strategy_stats.items() 
                      if s.get('league_tier') == tier]
            if members:
                _log(f"  Tier {tier}: {', '.join(members)}")
        
        _log(f"\n  Strategy Performance:")
        _log(f"  {'Strategy':<20} {'Signals':<10} {'Trades':<10} {'Win%':<10} {'P&L':<12} {'Tier':<6}")
        _log(f"  {'-'*68}")
        
        for name, stats in sorted(self.engine.strategy_stats.items(), 
                                   key=lambda x: x[1]['pnl'], reverse=True):
            if stats['signals'] > 0:
                win_rate = (stats['wins'] / stats['trades'] * 100) if stats['trades'] > 0 else 0
                tier = stats.get('league_tier', '?')
                _log(f"  {name:<20} {stats['signals']:<10} {stats['trades']:<10} "
                      f"{win_rate:<10.1f} ${stats['pnl']:+,.2f} {tier:<6}")
    
    def _save_summary(self):
        """Save summary to JSON."""
        summary = {
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": datetime.now(timezone.utc).isoformat(),
            "cycles": self.cycle_count,
            "config": {
                "initial_capital": self.config.initial_capital,
                "max_risk_per_trade_pct": self.config.max_risk_per_trade_pct,
                "max_daily_loss_pct": self.config.max_daily_loss_pct,
                "max_drawdown_pct": self.config.max_drawdown_pct,
            },
            "results": {
                "total_trades": len(self.engine.closed_trades),
                "open_trades": len(self.engine.open_trades),
                "wins": sum(1 for t in self.engine.closed_trades if t.pnl > 0),
                "total_pnl": sum(t.pnl for t in self.engine.closed_trades),
            },
            "strategy_stats": {
                name: {
                    "trades": s["trades"],
                    "wins": s["wins"],
                    "losses": s["losses"],
                    "pnl": s["pnl"],
                    "tier": s.get("league_tier", "?"),
                    "active": s["active"],
                }
                for name, s in self.engine.strategy_stats.items()
                if s["signals"] > 0
            },
        }
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.log_dir / f"paper_summary_{timestamp}.json"
        
        with open(path, "w") as f:
            json.dump(summary, f, indent=2)
        
        _log(f"\n  Summary saved: {path}")


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Gold Bot Paper Trading")
    parser.add_argument("--duration", type=int, default=168, 
                       help="Duration in hours (0 = unlimited)")
    parser.add_argument("--capital", type=float, default=1000.0,
                       help="Initial capital in Cent")
    parser.add_argument("--risk", type=float, default=0.5,
                       help="Max risk per trade %%")
    parser.add_argument("--symbol", type=str, default="XAUUSD",
                       help="Trading symbol")
    args = parser.parse_args()
    
    config = PaperConfig(
        symbol=args.symbol,
        initial_capital=args.capital,
        max_risk_per_trade_pct=args.risk,
    )
    
    trader = PaperTrader(config)
    
    if args.duration > 0:
        # Run for specified duration
        async def _run_with_timeout():
            await trader.start()
        
        try:
            await asyncio.wait_for(_run_with_timeout(), timeout=args.duration * 3600)
        except asyncio.TimeoutError:
            _log(f"\n  Duration reached ({args.duration}h)")
            trader.is_running = False
    else:
        await trader.start()


if __name__ == "__main__":
    asyncio.run(main())
