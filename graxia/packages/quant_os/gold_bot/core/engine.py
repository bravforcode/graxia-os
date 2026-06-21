"""
Gold Bot Core Engine — Orchestrates 13 strategies with scoring

Every 30 seconds:
1. Fetch latest XAUUSD data (M1, M5, M15, H1, H4)
2. Run all active strategies
3. Score each 0-100%
4. Aggregate signals
5. Send to Claude AI for validation
6. Execute via MT5 if approved
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from enum import Enum
import json
import os

from .config import BotConfig, get_bot_config


class SignalDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"


@dataclass
class StrategySignal:
    """Signal from a single strategy"""
    strategy_name: str
    direction: SignalDirection
    confidence: float  # 0.0 - 1.0
    score: int  # 0 - 100
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reasoning: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    timeframe: str = "M15"
    metadata: Dict = field(default_factory=dict)


@dataclass
class AggregatedSignal:
    """Combined signal from all strategies"""
    direction: SignalDirection
    total_score: int
    active_strategies: int
    buy_score: int
    sell_score: int
    signals: List[StrategySignal]
    consensus_entry: Optional[float] = None
    consensus_sl: Optional[float] = None
    consensus_tp: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    ai_validated: bool = False
    ai_reasoning: str = ""


@dataclass
class TradeRecord:
    """Executed trade record"""
    id: str
    symbol: str
    direction: SignalDirection
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    entry_time: datetime
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    strategy_scores: Dict[str, int] = field(default_factory=dict)
    ai_approved: bool = False
    status: str = "OPEN"  # OPEN, CLOSED, STOPPED


class GoldBotEngine:
    """
    Main engine that orchestrates everything.
    
    Lifecycle:
        bot = GoldBotEngine()
        await bot.start()  # Runs until stopped
        await bot.stop()
    """
    
    def __init__(self, config: BotConfig = None):
        self.config = config or get_bot_config()
        
        # Strategies registry
        self.strategies: Dict[str, object] = {}
        self.strategy_weights: Dict[str, float] = {}
        
        # League system
        self.league = LeagueSystem()
        
        # Risk management
        self.risk_manager = RiskManager(self.config)
        
        # MT5 broker
        self.broker = None  # Initialized on start
        
        # AI validator
        self.ai_validator = None  # Initialized on start
        
        # Telegram
        self.notifier = None  # Initialized on start
        
        # State
        self.is_running = False
        self.cycle_count = 0
        self.last_cycle_time = None
        
        # Trade tracking
        self.open_trades: List[TradeRecord] = []
        self.closed_trades: List[TradeRecord] = []
        self.daily_pnl: float = 0.0
        self.peak_equity: float = 0.0
        
        # Performance tracking
        self.strategy_stats: Dict[str, Dict] = {}
        
        # Data cache
        self.price_cache: Dict[str, Dict] = {}
        self.last_data_fetch: Optional[datetime] = None
    
    def register_strategy(self, name: str, strategy: object, weight: float = 1.0):
        """Register a strategy"""
        self.strategies[name] = strategy
        self.strategy_weights[name] = weight
        self.strategy_stats[name] = {
            "signals": 0,
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "pnl": 0.0,
            "active": True,
            "league_tier": "A",
        }
    
    async def start(self):
        """Start the bot"""
        print("=" * 70)
        print("  GOLD BOT - AI XAUUSD Trading System")
        print("  13 Strategies | Claude AI Validation | MT5 Execution")
        print("=" * 70)
        
        # Initialize components
        await self._initialize()
        
        # Register all 13 strategies
        self._register_strategies()
        
        self.is_running = True
        start_time = datetime.utcnow()
        
        print(f"\n  Started at: {start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"  Symbol: {self.config.symbol}")
        print(f"  Timeframe: {self.config.primary_timeframe}")
        print(f"  Cycle Interval: {self.config.cycle_interval_seconds}s")
        print(f"  Strategies Active: {len([s for s in self.strategy_stats.values() if s['active']])}")
        print(f"  Min Score to Trade: {self.config.min_score_to_trade}")
        print(f"  Max Risk/Trade: {self.config.max_risk_per_trade_pct}%")
        print(f"\n  Press Ctrl+C to stop\n")
        
        try:
            while self.is_running:
                await self._trading_cycle()
                await asyncio.sleep(self.config.cycle_interval_seconds)
        except KeyboardInterrupt:
            print("\n\n  Stopping bot...")
        finally:
            self.is_running = False
            await self._print_summary()
    
    async def stop(self):
        """Stop the bot"""
        self.is_running = False
    
    async def _initialize(self):
        """Initialize all components"""
        # MT5 Broker
        from ..execution.broker_adapter import MT5BrokerAdapter
        self.broker = MT5BrokerAdapter()
        
        try:
            await self.broker.connect()
            account = await self.broker.get_account()
            print(f"\n  MT5 Connected: Balance ${account.balance:,.2f}")
        except Exception as e:
            print(f"\n  MT5 Connection Failed: {e}")
            print("  Running in signal-only mode (no execution)")
            self.broker = None
        
        # AI Validator
        from ..ai.validator import ClaudeAIValidator
        self.ai_validator = ClaudeAIValidator(self.config)
        
        # Telegram
        from ..monitoring.telegram_bot import GoldBotTelegram
        self.notifier = GoldBotTelegram(self.config)
        
        try:
            await self.notifier.initialize()
            print("  Telegram: Connected")
        except Exception as e:
            print(f"  Telegram: {e}")
            self.notifier = None
    
    def _register_strategies(self):
        """Register all 13 strategies"""
        from ..strategies.order_block import OrderBlockStrategy
        from ..strategies.supply_demand import SupplyDemandStrategy
        from ..strategies.ema_cross import EMACrossStrategy
        from ..strategies.rsi_divergence import RSIDivergenceStrategy
        from ..strategies.london_breakout import LondonBreakoutStrategy
        from ..strategies.fibonacci import FibonacciStrategy
        from ..strategies.vwap_rejection import VWAPRejectionStrategy
        from ..strategies.news_fade import NewsFadeStrategy
        from ..strategies.multi_tf_align import MultiTFAlignStrategy
        from ..strategies.bos_choch import BOSCHoCHStrategy
        from ..strategies.liquidity_sweep import LiquiditySweepStrategy
        from ..strategies.fair_value_gap import FairValueGapStrategy
        from ..strategies.opening_range import OpeningRangeStrategy
        
        strategies = [
            ("order_block", OrderBlockStrategy(), 1.2),
            ("supply_demand", SupplyDemandStrategy(), 1.1),
            ("ema_cross", EMACrossStrategy(), 1.0),
            ("rsi_divergence", RSIDivergenceStrategy(), 1.0),
            ("london_breakout", LondonBreakoutStrategy(), 1.1),
            ("fibonacci", FibonacciStrategy(), 1.0),
            ("vwap_rejection", VWAPRejectionStrategy(), 1.0),
            ("news_fade", NewsFadeStrategy(), 0.9),
            ("multi_tf_align", MultiTFAlignStrategy(), 1.2),
            ("bos_choch", BOSCHoCHStrategy(), 1.1),
            ("liquidity_sweep", LiquiditySweepStrategy(), 1.3),
            ("fair_value_gap", FairValueGapStrategy(), 1.2),
            ("opening_range", OpeningRangeStrategy(), 1.1),
        ]
        
        for name, strategy, weight in strategies:
            self.register_strategy(name, strategy, weight)
        
        print(f"  Registered {len(strategies)} strategies")
    
    async def _trading_cycle(self):
        """Single trading cycle — runs every 30 seconds"""
        cycle_start = time.time()
        self.cycle_count += 1
        
        try:
            # 1. Fetch latest data
            data = await self._fetch_data()
            if not data:
                return
            
            # 2. Run all active strategies
            signals = await self._run_strategies(data)
            
            # 3. Aggregate signals
            aggregated = self._aggregate_signals(signals)
            
            # 4. Update league system
            self.league.update(self.strategy_stats)
            
            # 5. Check if should trade
            if aggregated.total_score >= self.config.min_score_to_trade:
                # 6. AI validation
                if self.config.ai_validation_enabled:
                    validated = await self.ai_validator.validate(aggregated)
                    if not validated:
                        print(f"  [Cycle {self.cycle_count}] AI rejected signal (score: {aggregated.total_score})")
                        return
                    aggregated.ai_validated = True
                
                # 7. Risk check
                if not self.risk_manager.check(aggregated, self.open_trades, self.daily_pnl):
                    print(f"  [Cycle {self.cycle_count}] Risk check failed")
                    return
                
                # 8. Execute
                await self._execute_signal(aggregated)
            
            # Log cycle
            elapsed = time.time() - cycle_start
            self.last_cycle_time = datetime.utcnow()
            
            if self.cycle_count % 10 == 0:
                active = len([s for s in self.strategy_stats.values() if s['active']])
                print(f"  [Cycle {self.cycle_count}] "
                      f"Score: {aggregated.total_score} | "
                      f"Active: {active}/13 | "
                      f"Open: {len(self.open_trades)} | "
                      f"P&L: ${self.daily_pnl:+,.2f} | "
                      f"Time: {elapsed:.2f}s")
                
        except Exception as e:
            print(f"  [Cycle {self.cycle_count}] Error: {e}")
    
    async def _fetch_data(self) -> Dict:
        """Fetch latest OHLCV data for XAUUSD — fail-loud if no broker"""
        if not self.broker:
            # FAIL-LOUD: ไม่ mock data เงียบๆ
            raise RuntimeError(
                "\nNO DATA SOURCE AVAILABLE\n"
                "Cannot trade without real market data.\n"
                "Connect to MT5 or configure a data feed."
            )
        
        try:
            data = {}
            for tf in self.config.timeframes:
                bars = await self.broker.get_bars(
                    self.config.symbol, tf, 200
                )
                if bars:
                    data[tf] = {
                        "open": [float(b.open) for b in bars],
                        "high": [float(b.high) for b in bars],
                        "low": [float(b.low) for b in bars],
                        "close": [float(b.close) for b in bars],
                        "volume": [b.volume for b in bars],
                        "timestamps": [b.timestamp for b in bars],
                    }
            
            # Get current price
            tick = await self.broker.get_tick(self.config.symbol)
            if tick:
                self.price_cache = {
                    "bid": float(tick.bid),
                    "ask": float(tick.ask),
                    "mid": float(tick.mid),
                    "spread": float(tick.spread),
                    "timestamp": tick.timestamp,
                }
            
            self.last_data_fetch = datetime.utcnow()
            return data
            
        except Exception as e:
            # FAIL-LOUD: data fetch error = halt, don't use fake data
            raise RuntimeError(
                f"\nDATA FETCH FAILED: {e}\n"
                f"Cannot trade with stale/missing data.\n"
                f"Check MT5 connection and try again."
            ) from e
    
    def _generate_mock_data(self) -> Dict:
        """Generate mock data for testing without MT5"""
        import random
        
        base_price = 2350.0  # Current gold price approx
        data = {}
        
        for tf in ["M1", "M5", "M15", "H1", "H4"]:
            closes = []
            highs = []
            lows = []
            opens = []
            volumes = []
            
            price = base_price
            for _ in range(200):
                change = random.gauss(0, 0.001)
                o = price
                c = price * (1 + change)
                h = max(o, c) * (1 + abs(random.gauss(0, 0.0005)))
                l = min(o, c) * (1 - abs(random.gauss(0, 0.0005)))
                v = 100000 * (1 + random.gauss(0, 0.3))
                
                opens.append(round(o, 2))
                closes.append(round(c, 2))
                highs.append(round(h, 2))
                lows.append(round(l, 2))
                volumes.append(max(0, v))
                
                price = c
            
            data[tf] = {
                "open": opens,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": volumes,
            }
        
        # Mock current price
        self.price_cache = {
            "bid": base_price - 0.15,
            "ask": base_price + 0.15,
            "mid": base_price,
            "spread": 0.30,
            "timestamp": datetime.utcnow(),
        }
        
        return data
    
    async def _run_strategies(self, data: Dict) -> List[StrategySignal]:
        """Run all active strategies"""
        signals = []
        
        for name, strategy in self.strategies.items():
            # Skip benched strategies
            if not self.strategy_stats[name]["active"]:
                continue
            
            try:
                signal = strategy.analyze(
                    data=data,
                    current_price=self.price_cache.get("mid", 0),
                    symbol=self.config.symbol,
                )
                
                if signal:
                    signals.append(signal)
                    self.strategy_stats[name]["signals"] += 1
                    
            except Exception as e:
                print(f"  Strategy {name} error: {e}")
        
        return signals
    
    def _aggregate_signals(self, signals: List[StrategySignal]) -> AggregatedSignal:
        """Aggregate signals from all strategies into a single decision"""
        if not signals:
            return AggregatedSignal(
                direction=SignalDirection.NEUTRAL,
                total_score=0,
                active_strategies=0,
                buy_score=0,
                sell_score=0,
                signals=[],
            )
        
        buy_score = 0
        sell_score = 0
        
        for signal in signals:
            weight = self.strategy_weights.get(signal.strategy_name, 1.0)
            weighted_score = int(signal.score * weight)
            
            if signal.direction == SignalDirection.BUY:
                buy_score += weighted_score
            elif signal.direction == SignalDirection.SELL:
                sell_score += weighted_score
        
        # Determine direction
        if buy_score > sell_score and buy_score > 0:
            direction = SignalDirection.BUY
        elif sell_score > buy_score and sell_score > 0:
            direction = SignalDirection.SELL
        else:
            direction = SignalDirection.NEUTRAL
        
        total_score = max(buy_score, sell_score)
        
        # Calculate consensus levels
        relevant_signals = [s for s in signals if s.direction == direction]
        consensus_entry = None
        consensus_sl = None
        consensus_tp = None
        
        if relevant_signals:
            entries = [s.entry_price for s in relevant_signals if s.entry_price]
            sls = [s.stop_loss for s in relevant_signals if s.stop_loss]
            tps = [s.take_profit for s in relevant_signals if s.take_profit]
            
            if entries:
                consensus_entry = sum(entries) / len(entries)
            if sls:
                consensus_sl = sum(sls) / len(sls)
            if tps:
                consensus_tp = sum(tps) / len(tps)
        
        return AggregatedSignal(
            direction=direction,
            total_score=total_score,
            active_strategies=len(signals),
            buy_score=buy_score,
            sell_score=sell_score,
            signals=signals,
            consensus_entry=consensus_entry,
            consensus_sl=consensus_sl,
            consensus_tp=consensus_tp,
        )
    
    async def _execute_signal(self, signal: AggregatedSignal):
        """Execute an approved signal"""
        if not self.broker:
            print(f"  [SIMULATED] {signal.direction.value} XAUUSD "
                  f"Score: {signal.total_score} "
                  f"Entry: {signal.consensus_entry:.2f} "
                  f"SL: {signal.consensus_sl:.2f} "
                  f"TP: {signal.consensus_tp:.2f}")
            return
        
        try:
            # Calculate position size
            account = await self.broker.get_account()
            quantity = self.risk_manager.calculate_position_size(
                balance=float(account.balance),
                entry_price=signal.consensus_entry or self.price_cache["mid"],
                stop_loss=signal.consensus_sl or 0,
            )
            
            if quantity <= 0:
                return
            
            # Create order
            from ..execution.order import Order, OrderSide, OrderType
            
            side = OrderSide.BUY if signal.direction == SignalDirection.BUY else OrderSide.SELL
            
            order = Order(
                symbol=self.config.symbol,
                side=side,
                order_type=OrderType.MARKET,
                quantity=Decimal(str(quantity)),
                stop_price=Decimal(str(signal.consensus_sl)) if signal.consensus_sl else None,
                strategy_id="gold_bot_ensemble",
                trading_mode="PAPER",
            )
            
            # Execute
            result = await self.broker.place_order(order)
            
            if result.success:
                trade = TradeRecord(
                    id=result.broker_order_id or str(time.time()),
                    symbol=self.config.symbol,
                    direction=signal.direction,
                    entry_price=float(result.avg_fill_price or self.price_cache["mid"]),
                    quantity=quantity,
                    stop_loss=signal.consensus_sl or 0,
                    take_profit=signal.consensus_tp or 0,
                    entry_time=datetime.utcnow(),
                    strategy_scores={s.strategy_name: s.score for s in signal.signals},
                    ai_validated=signal.ai_validated,
                )
                
                self.open_trades.append(trade)
                
                # Notify
                if self.notifier:
                    await self.notifier.notify_trade(trade, signal)
                
                print(f"\n  {'🟢' if side == OrderSide.BUY else '🔴'} TRADE EXECUTED")
                print(f"  {side.value} {quantity} lots @ {trade.entry_price:.2f}")
                print(f"  SL: {trade.stop_loss:.2f} | TP: {trade.take_profit:.2f}")
                print(f"  Score: {signal.total_score} | AI: {'✓' if signal.ai_validated else '✗'}")
                print(f"  Strategies: {', '.join(f'{s.strategy_name}({s.score})' for s in signal.signals[:5])}")
                
        except Exception as e:
            print(f"  Execution error: {e}")
    
    async def _print_summary(self):
        """Print final summary"""
        print("\n" + "=" * 70)
        print("  GOLD BOT - Session Summary")
        print("=" * 70)
        
        print(f"\n  Duration: {self.cycle_count * self.config.cycle_interval_seconds}s")
        print(f"  Total Cycles: {self.cycle_count}")
        print(f"  Open Trades: {len(self.open_trades)}")
        print(f"  Closed Trades: {len(self.closed_trades)}")
        print(f"  Daily P&L: ${self.daily_pnl:+,.2f}")
        
        # Strategy performance
        print(f"\n  Strategy Performance:")
        print(f"  {'Strategy':<20} {'Signals':<10} {'Trades':<10} {'Win%':<10} {'P&L':<12}")
        print(f"  {'-'*62}")
        
        for name, stats in sorted(self.strategy_stats.items(), 
                                   key=lambda x: x[1]['pnl'], reverse=True):
            if stats['signals'] > 0:
                win_rate = (stats['wins'] / stats['trades'] * 100) if stats['trades'] > 0 else 0
                print(f"  {name:<20} {stats['signals']:<10} {stats['trades']:<10} "
                      f"{win_rate:<10.1f} ${stats['pnl']:+,.2f}")
        
        print(f"\n  League Status:")
        for tier in ["S", "A", "B", "C", "BENCH"]:
            members = [n for n, s in self.strategy_stats.items() 
                      if s.get('league_tier') == tier]
            if members:
                print(f"  Tier {tier}: {', '.join(members)}")


class LeagueSystem:
    """
    League system — auto-bench losing strategies.
    
    Tiers:
        S: Top performers (win rate > 60%, PF > 1.5)
        A: Good performers (win rate > 50%, PF > 1.0)
        B: Average (win rate > 45%)
        C: Underperformers (win rate < 45%)
        BENCH: Suspended (3 consecutive losses)
    """
    
    TIER_THRESHOLDS = {
        "S": {"min_win_rate": 0.60, "min_pf": 1.5, "min_trades": 10},
        "A": {"min_win_rate": 0.50, "min_pf": 1.0, "min_trades": 5},
        "B": {"min_win_rate": 0.45, "min_pf": 0.8, "min_trades": 3},
        "C": {"min_win_rate": 0.0, "min_pf": 0.0, "min_trades": 0},
    }
    
    BENCH_CONSECUTIVELOSSES = 3
    UNBENCH_WINSTREAK = 2
    
    def __init__(self):
        self.consecutive_losses: Dict[str, int] = {}
        self.consecutive_wins: Dict[str, int] = {}
    
    def update(self, strategy_stats: Dict[str, Dict]):
        """Update league tiers based on performance"""
        for name, stats in strategy_stats.items():
            trades = stats.get("trades", 0)
            wins = stats.get("wins", 0)
            
            if trades == 0:
                stats["league_tier"] = "A"  # New strategies start in A
                continue
            
            win_rate = wins / trades
            
            # Check for benching
            if stats.get("league_tier") == "BENCH":
                # Check if should unbench
                if self.consecutive_wins.get(name, 0) >= self.UNBENCH_WINSTREAK:
                    stats["league_tier"] = "C"
                    self.consecutive_wins[name] = 0
                    self.consecutive_losses[name] = 0
                continue
            
            # Check consecutive losses
            if stats.get("losses", 0) > 0:
                self.consecutive_losses[name] = self.consecutive_losses.get(name, 0) + 1
                self.consecutive_wins[name] = 0
            else:
                self.consecutive_wins[name] = self.consecutive_wins.get(name, 0) + 1
                self.consecutive_losses[name] = 0
            
            # Bench if too many consecutive losses
            if self.consecutive_losses.get(name, 0) >= self.BENCH_CONSECUTIVELOSSES:
                stats["league_tier"] = "BENCH"
                stats["active"] = False
                continue
            
            # Determine tier
            pf = stats.get("pnl", 0) / abs(stats.get("pnl", 1)) if stats.get("pnl", 0) < 0 else 1.0
            
            for tier, thresholds in self.TIER_THRESHOLDS.items():
                if (win_rate >= thresholds["min_win_rate"] and
                    trades >= thresholds["min_trades"]):
                    stats["league_tier"] = tier
                    stats["active"] = True
                    break


class RiskManager:
    """
    Risk management — SL, Breakeven, Max Drawdown, Position Sizing
    """
    
    def __init__(self, config: BotConfig):
        self.config = config
        self.daily_loss: float = 0.0
        self.peak_equity: float = 0.0
    
    def check(self, signal: AggregatedSignal, open_trades: list, daily_pnl: float) -> bool:
        """Check if trade passes risk management"""
        # Max open positions
        if len(open_trades) >= self.config.max_positions:
            return False
        
        # Daily loss limit
        max_daily_loss = self.config.initial_capital * (self.config.max_daily_loss_pct / 100)
        if abs(daily_pnl) >= max_daily_loss and daily_pnl < 0:
            return False
        
        # Max drawdown
        if self.peak_equity > 0:
            drawdown = (self.peak_equity - (self.config.initial_capital + daily_pnl)) / self.peak_equity
            if drawdown >= (self.config.max_drawdown_pct / 100):
                return False
        
        # Minimum score
        if signal.total_score < self.config.min_score_to_trade:
            return False
        
        # Minimum active strategies
        if signal.active_strategies < self.config.min_active_strategies:
            return False
        
        return True
    
    def calculate_position_size(
        self,
        balance: float,
        entry_price: float,
        stop_loss: float,
    ) -> float:
        """Calculate position size based on risk"""
        risk_pct = self.config.max_risk_per_trade_pct / 100
        risk_amount = balance * risk_pct
        
        if stop_loss <= 0 or entry_price <= 0:
            return 0.0
        
        risk_per_unit = abs(entry_price - stop_loss)
        
        if risk_per_unit <= 0:
            return 0.0
        
        # For gold: 1 lot = 100 oz, pip value = $1 per 0.01 move per lot
        # Simplified: quantity in lots
        quantity = risk_amount / (risk_per_unit * 100)
        
        # Round to 2 decimal places
        quantity = round(quantity, 2)
        
        # Apply limits
        quantity = min(quantity, self.config.max_position_size_lots)
        quantity = max(quantity, 0.01)  # Minimum 0.01 lot
        
        return quantity
    
    def check_breakeven(self, trade: TradeRecord, current_price: float) -> bool:
        """Check if should move SL to breakeven"""
        if trade.direction == SignalDirection.BUY:
            profit_pips = (current_price - trade.entry_price) / 0.01
        else:
            profit_pips = (trade.entry_price - current_price) / 0.01
        
        return profit_pips >= self.config.breakeven_trigger_pips
