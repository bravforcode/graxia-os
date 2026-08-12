"""
Gold Bot Multi-Symbol Paper Trading Runner.

Runs XAUUSD, EURUSD, and BTCUSD simultaneously via shared PaperBroker
with separate position tracking per symbol.

Usage:
    python -m gold_bot.run_multi --duration 168  # 7 days
    python -m gold_bot.run_multi --duration 0    # Until stopped
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
from typing import Dict, List, Optional

# Ensure project root is on path (monorepo root)
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

PID_DIR = Path(__file__).resolve().parents[2] / "logs"


def _log(msg: str):
    """Print with guaranteed flush for pythonw background mode."""
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# Per-symbol configuration
# ---------------------------------------------------------------------------

SYMBOL_CONFIGS = {
    "XAUUSD": {
        "primary_timeframe": "M15",
        "timeframes": ["M1", "M5", "M15", "H1", "H4"],
        "sl_distance_points": 37.0,
        "units_per_lot": 100.0,
        "max_position_size_lots": 0.05,
    },
    "EURUSD": {
        "primary_timeframe": "M15",
        "timeframes": ["M1", "M5", "M15", "H1", "H4"],
        "sl_distance_points": 0.0037,
        "units_per_lot": 100000.0,
        "max_position_size_lots": 0.1,
    },
    "BTCUSD": {
        "primary_timeframe": "M15",
        "timeframes": ["M1", "M5", "M15", "H1", "H4"],
        "sl_distance_points": 250.0,
        "units_per_lot": 1.0,
        "max_position_size_lots": 0.05,
    },
}


@dataclass
class MultiConfig:
    """Multi-symbol paper trading configuration."""
    symbols: list = field(default_factory=lambda: ["XAUUSD", "EURUSD", "BTCUSD"])
    cycle_interval_seconds: int = 30
    initial_capital: float = 49911.92
    max_risk_per_trade_pct: float = 0.25
    max_daily_loss_pct: float = 2.0
    max_drawdown_pct: float = 8.0
    max_positions_per_symbol: int = 1
    max_positions_total: int = 3
    risk_reward_ratio: float = 2.0
    min_score_to_trade: int = 350
    min_active_strategies: int = 3
    ai_validation_enabled: bool = False  # Disable AI for multi-symbol paper
    breakeven_trigger_pips: float = 30.0
    cooldown_cycles: int = 10
    log_dir: str = "logs"
    report_interval_cycles: int = 480


# ---------------------------------------------------------------------------
# Per-symbol state tracker
# ---------------------------------------------------------------------------

@dataclass
class SymbolState:
    """Tracks per-symbol open/closed trades and cooldown."""
    symbol: str
    engine: object = None  # GoldBotEngine
    open_trades: list = field(default_factory=list)
    closed_trades: list = field(default_factory=list)
    daily_pnl: float = 0.0
    last_trade_cycle: int = 0
    cycles_without_trade: int = 0
    cooldown_cycles: int = 10
    min_score: int = 350
    min_score_floor: int = 280


# ---------------------------------------------------------------------------
# Multi-symbol trader
# ---------------------------------------------------------------------------

class MultiSymbolTrader:
    """
    Paper trading engine for XAUUSD, EURUSD, BTCUSD simultaneously.

    Flow:
        1. Connect to MT5 for live price feeds
        2. For each symbol, run 13 strategies every 30 seconds
        3. Execute on shared PaperBroker (separate position tracking)
        4. Log all trades to CSV
        5. Send Telegram reports every 4 hours
    """

    def __init__(self, config: MultiConfig):
        self.config = config
        self.broker = None
        self.mt5_connected = False
        self.symbol_states: Dict[str, SymbolState] = {}

        # Global state
        self.is_running = False
        self.cycle_count = 0
        self.start_time = None
        self.daily_pnl: float = 0.0
        self.peak_equity: float = config.initial_capital

        # Telegram
        self.telegram = None

        # Logging
        self.log_dir = Path(config.log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.csv_file = None
        self.csv_writer = None

        # Daily report
        self._last_daily_report_cycle: int = 0
        self._daily_report_interval: int = 2880

    async def start(self):
        """Start multi-symbol paper trading."""
        _log("=" * 70)
        _log("  GOLD BOT -- Multi-Symbol Paper Trading")
        _log("  XAUUSD + EURUSD + BTCUSD | Live MT5 Prices | PaperBroker")
        _log("=" * 70)

        await self._init_mt5()
        await self._init_paper_broker()
        await self._init_engines()
        await self._init_telegram()
        self._setup_logging()
        self._write_pid()

        self.is_running = True
        self.start_time = datetime.now(timezone.utc)

        _log(f"\n  Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        _log(f"  Symbols: {', '.join(self.config.symbols)}")
        _log(f"  Capital: ${self.config.initial_capital:,.2f}")
        _log(f"  Risk/Trade: {self.config.max_risk_per_trade_pct}%")
        _log(f"  Max DD: {self.config.max_drawdown_pct}%")
        _log(f"  Max Positions: {self.config.max_positions_per_symbol}/symbol, {self.config.max_positions_total} total")
        _log(f"  RR Ratio: 1:{self.config.risk_reward_ratio}")
        _log(f"  Cycle: {self.config.cycle_interval_seconds}s")
        _log(f"  Cooldown: {self.config.cooldown_cycles * self.config.cycle_interval_seconds}s")
        _log(f"\n  Press Ctrl+C to stop\n")

        try:
            while self.is_running:
                await self._trading_cycle()
                await asyncio.sleep(self.config.cycle_interval_seconds)
        except KeyboardInterrupt:
            _log("\n\n  Stopping multi-symbol trader...")
        finally:
            self.is_running = False
            self._remove_pid()
            await self._print_summary()
            self._save_summary()

    # ----- Initialization -----

    async def _init_mt5(self):
        """Connect to MT5 for live price feeds with retry logic."""
        try:
            import MetaTrader5 as mt5

            path = os.getenv("MT5_PATH", r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe")
            login = int(os.getenv("MT5_LOGIN", "0"))
            password = os.getenv("MT5_PASSWORD", "")
            server = os.getenv("MT5_SERVER", "Pepperstone-Demo")
            timeout = int(os.getenv("MT5_TIMEOUT_MS", "60000"))

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

                        # Enable symbols that are not visible by default
                        for sym in self.config.symbols:
                            si = mt5.symbol_info(sym)
                            if si and not si.visible:
                                mt5.symbol_select(sym, True)
                                _log(f"  Enabled symbol: {sym}")
                        return
                    else:
                        _log(f"  MT5 init OK but no account info (attempt {attempt})")
                else:
                    err = mt5.last_error()
                    _log(f"  MT5 init failed (attempt {attempt}): {err}")

                if attempt < 3:
                    _log(f"  Retrying in 10s...")
                    await asyncio.sleep(10)

            _log("  MT5: All connection attempts failed -- running without MT5")

        except ImportError:
            _log("  MT5 Python package not installed")
        except Exception as e:
            _log(f"  MT5 connection error: {e}")

    async def _init_paper_broker(self):
        """Initialize shared PaperBroker."""
        from graxia.packages.quant_os.execution.broker_adapter import PaperBroker

        self.broker = PaperBroker()
        await self.broker.connect()

        from decimal import Decimal
        self.broker.account.balance = Decimal(str(self.config.initial_capital))
        self.broker.account.equity = Decimal(str(self.config.initial_capital))
        self.broker.account.free_margin = Decimal(str(self.config.initial_capital))

        _log(f"  PaperBroker: ${self.config.initial_capital:,.2f} initial capital")

    async def _init_engines(self):
        """Initialize a GoldBotEngine per symbol, sharing the PaperBroker."""
        from graxia.packages.quant_os.gold_bot.core.engine import GoldBotEngine
        from graxia.packages.quant_os.gold_bot.core.config import BotConfig

        for sym in self.config.symbols:
            cfg = SYMBOL_CONFIGS.get(sym, SYMBOL_CONFIGS["XAUUSD"])
            bot_config = BotConfig(
                symbol=sym,
                primary_timeframe=cfg["primary_timeframe"],
                timeframes=cfg["timeframes"],
                cycle_interval_seconds=self.config.cycle_interval_seconds,
                min_score_to_trade=self.config.min_score_to_trade,
                min_active_strategies=self.config.min_active_strategies,
                initial_capital=self.config.initial_capital / len(self.config.symbols),
                max_risk_per_trade_pct=self.config.max_risk_per_trade_pct,
                max_daily_loss_pct=self.config.max_daily_loss_pct,
                max_drawdown_pct=self.config.max_drawdown_pct,
                max_positions=self.config.max_positions_per_symbol,
                max_position_size_lots=cfg["max_position_size_lots"],
                units_per_lot=cfg["units_per_lot"],
                breakeven_trigger_pips=self.config.breakeven_trigger_pips,
                ai_validation_enabled=self.config.ai_validation_enabled,
                sl_distance_points=cfg["sl_distance_points"],
                risk_reward_ratio=self.config.risk_reward_ratio,
            )

            engine = GoldBotEngine(bot_config)
            engine.broker = self.broker
            engine._register_strategies()

            state = SymbolState(
                symbol=sym,
                engine=engine,
                cooldown_cycles=self.config.cooldown_cycles,
                min_score=self.config.min_score_to_trade,
            )
            self.symbol_states[sym] = state

            _log(f"  Engine [{sym}]: {len(engine.strategies)} strategies loaded")

    async def _init_telegram(self):
        """Initialize Telegram notifications."""
        try:
            from graxia.packages.quant_os.gold_bot.monitoring.telegram_bot import GoldBotTelegram
            from graxia.packages.quant_os.gold_bot.core.config import BotConfig
            tg_config = BotConfig(
                telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
                telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            )
            self.telegram = GoldBotTelegram(tg_config)
            await self.telegram.initialize()
            _log("  Telegram: Connected")
            await self.telegram.send_message(
                "Multi-Symbol Bot Started\n"
                f"Symbols: {', '.join(self.config.symbols)}\n"
                f"Capital: ${self.config.initial_capital:,.2f}\n"
                f"Settings: Score>={self.config.min_score_to_trade}, "
                f"{self.config.max_risk_per_trade_pct}% risk, "
                f"1:{self.config.risk_reward_ratio} RR"
            )
        except Exception as e:
            _log(f"  Telegram: Not available ({e})")
            self.telegram = None

    def _setup_logging(self):
        """Setup CSV logging with symbol column."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = self.log_dir / f"multi_trades_{timestamp}.csv"

        self.csv_file = open(csv_path, "w", newline="")
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow([
            "timestamp", "symbol", "direction", "entry", "exit", "sl", "tp",
            "quantity", "pnl", "pnl_pct", "score", "strategies", "status"
        ])

        _log(f"  Logging to: {csv_path}")

    def _write_pid(self):
        """Write PID file for health check compatibility."""
        PID_DIR.mkdir(parents=True, exist_ok=True)
        pid_file = PID_DIR / "multi_paper.pid"
        pid_file.write_text(str(os.getpid()))
        _log(f"  PID file: {pid_file}")

    def _remove_pid(self):
        """Remove PID file on shutdown."""
        pid_file = PID_DIR / "multi_paper.pid"
        if pid_file.exists():
            pid_file.unlink()

    # ----- Core trading loop -----

    async def _trading_cycle(self):
        """Single trading cycle across all symbols."""
        cycle_start = time.time()
        self.cycle_count += 1

        try:
            # MT5 health check
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

            # Sync live prices for all symbols
            self._sync_all_prices()

            # Check open trades for SL/TP hits across all symbols
            self._check_open_trades_all()

            # Run strategies per symbol
            for sym in self.config.symbols:
                state = self.symbol_states[sym]
                if not state.engine:
                    continue
                await self._process_symbol(state)

            # Heartbeat every 10 cycles
            if self.cycle_count % 10 == 0:
                open_total = sum(len(s.open_trades) for s in self.symbol_states.values())
                closed_total = sum(len(s.closed_trades) for s in self.symbol_states.values())
                per_sym = ", ".join(
                    f"{s.symbol}:{len(s.open_trades)}o/{len(s.closed_trades)}c"
                    for s in self.symbol_states.values()
                )
                _log(f"  [Heartbeat] Cycle {self.cycle_count} | "
                     f"MT5: {'ON' if self.mt5_connected else 'OFF'} | "
                     f"Total: {open_total}o/{closed_total}c | {per_sym}")

            # Daily report
            if (self.cycle_count - self._last_daily_report_cycle) >= self._daily_report_interval:
                self._last_daily_report_cycle = self.cycle_count
                await self._send_daily_report()

            # Periodic status
            if self.cycle_count % self.config.report_interval_cycles == 0:
                self._print_status()

        except Exception as e:
            _log(f"  [Cycle {self.cycle_count}] Error: {e}")

    async def _process_symbol(self, state: SymbolState):
        """Run strategy evaluation for one symbol."""
        sym = state.symbol
        engine = state.engine

        # Fetch MT5 data for this symbol
        data = self._fetch_mt5_data(sym)
        if not data:
            return

        # Run strategies
        signals = await engine._run_strategies(data)
        aggregated = engine._aggregate_signals(signals)

        # Update league
        engine.league.update(engine.strategy_stats)

        # Check score threshold
        if aggregated.total_score >= state.min_score:
            # Cooldown check
            if (self.cycle_count - state.last_trade_cycle) < state.cooldown_cycles:
                return

            # Global position limit
            open_total = sum(len(s.open_trades) for s in self.symbol_states.values())
            if open_total >= self.config.max_positions_total:
                return

            # Per-symbol position limit
            if len(state.open_trades) >= self.config.max_positions_per_symbol:
                return

            # Risk check
            risk_result = engine.risk_bridge.check(
                signal=aggregated,
                open_trades=state.open_trades,
                daily_pnl=state.daily_pnl,
                balance=self.config.initial_capital / len(self.config.symbols) + state.daily_pnl,
                equity=self.config.initial_capital / len(self.config.symbols) + state.daily_pnl,
            )

            if risk_result.approved:
                await self._execute_signal(state, aggregated)
                state.last_trade_cycle = self.cycle_count
                state.cycles_without_trade = 0
            else:
                state.cycles_without_trade += 1
        else:
            state.cycles_without_trade += 1

        # Auto-adjust threshold
        adjust_after = 360
        if (state.cycles_without_trade >= adjust_after
                and state.min_score > state.min_score_floor):
            old = state.min_score
            state.min_score = max(state.min_score - 10, state.min_score_floor)
            state.cycles_without_trade = 0
            _log(f"  [AUTO-ADJUST] {sym} min_score: {old} -> {state.min_score}")

    # ----- Price syncing -----

    def _sync_all_prices(self):
        """Sync live MT5 prices to PaperBroker for all symbols."""
        if not self.mt5_connected:
            return

        try:
            import MetaTrader5 as mt5
            from decimal import Decimal

            for sym in self.config.symbols:
                try:
                    tick = mt5.symbol_info_tick(sym)
                    if tick:
                        self.broker.prices[sym] = {
                            "bid": Decimal(str(tick.bid)),
                            "ask": Decimal(str(tick.ask)),
                            "mid": Decimal(str((tick.bid + tick.ask) / 2)),
                        }
                except Exception:
                    pass
        except Exception:
            pass

    def _fetch_mt5_data(self, symbol: str) -> Optional[dict]:
        """Fetch OHLCV data directly from MT5 for a symbol."""
        if not self.mt5_connected:
            return None

        try:
            import MetaTrader5 as mt5

            state = self.symbol_states[symbol]
            cfg = SYMBOL_CONFIGS.get(symbol, SYMBOL_CONFIGS["XAUUSD"])

            data = {}
            tf_map = {
                "M1": mt5.TIMEFRAME_M1,
                "M5": mt5.TIMEFRAME_M5,
                "M15": mt5.TIMEFRAME_M15,
                "H1": mt5.TIMEFRAME_H1,
                "H4": mt5.TIMEFRAME_H4,
            }

            for tf in cfg["timeframes"]:
                mt5_tf = tf_map.get(tf)
                if not mt5_tf:
                    continue

                rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, 200)
                if rates is not None and len(rates) > 0:
                    data[tf] = {
                        "open": [float(r["open"]) for r in rates],
                        "high": [float(r["high"]) for r in rates],
                        "low": [float(r["low"]) for r in rates],
                        "close": [float(r["close"]) for r in rates],
                        "volume": [float(r["tick_volume"]) for r in rates],
                        "timestamps": [r["time"] for r in rates],
                    }

            # Update engine price cache
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                state.engine.price_cache = {
                    "bid": float(tick.bid),
                    "ask": float(tick.ask),
                    "mid": float((tick.bid + tick.ask) / 2),
                    "spread": float(tick.ask - tick.bid),
                }

            return data if data else None

        except Exception as e:
            _log(f"  MT5 data fetch error [{symbol}]: {e}")
            return None

    # ----- Trade execution -----

    async def _execute_signal(self, state: SymbolState, signal):
        """Execute an approved signal for a specific symbol."""
        sym = state.symbol
        engine = state.engine

        entry_price = signal.consensus_entry or engine.price_cache.get("mid", 0)
        if entry_price <= 0:
            return

        # Dynamic SL/TP with 1:2 RR
        sl_dist = getattr(engine.config, "sl_distance_points", 37.0)
        rr_ratio = getattr(engine.config, "risk_reward_ratio", 2.0)
        tp_dist = sl_dist * rr_ratio

        if signal.direction.value == "BUY":
            dynamic_sl = entry_price - sl_dist
            dynamic_tp = entry_price + tp_dist
        else:
            dynamic_sl = entry_price + sl_dist
            dynamic_tp = entry_price - tp_dist

        signal.consensus_sl = dynamic_sl
        signal.consensus_tp = dynamic_tp

        # Risk check
        risk_result = engine.risk_bridge.check(
            signal=signal,
            open_trades=state.open_trades,
            daily_pnl=state.daily_pnl,
            balance=self.config.initial_capital / len(self.config.symbols) + state.daily_pnl,
            equity=self.config.initial_capital / len(self.config.symbols) + state.daily_pnl,
        )

        if not risk_result.approved or risk_result.quantity <= 0:
            return

        quantity = risk_result.quantity

        # Create order
        from graxia.packages.quant_os.execution.order import Order, OrderSide, OrderType
        from decimal import Decimal

        side = OrderSide.BUY if signal.direction.value == "BUY" else OrderSide.SELL

        order = Order(
            symbol=sym,
            side=side,
            order_type=OrderType.MARKET,
            quantity=Decimal(str(quantity)),
            stop_price=Decimal(str(dynamic_sl)) if dynamic_sl else None,
            strategy_id=f"multi_bot_{sym}",
            trading_mode="PAPER",
        )

        result = await self.broker.place_order(order)

        if result.success:
            trade = engine.TradeRecord(
                id=result.broker_order_id or str(time.time()),
                symbol=sym,
                direction=signal.direction,
                entry_price=float(result.avg_fill_price or engine.price_cache.get("mid", 0)),
                quantity=quantity,
                stop_loss=dynamic_sl or 0,
                take_profit=dynamic_tp or 0,
                entry_time=datetime.now(timezone.utc),
                strategy_scores={s.strategy_name: s.score for s in signal.signals},
                ai_approved=signal.ai_validated,
            )

            state.open_trades.append(trade)

            # Update strategy trade counts
            for s in signal.signals:
                if s.strategy_name in engine.strategy_stats:
                    engine.strategy_stats[s.strategy_name]["trades"] += 1

            # Log to CSV
            self._log_trade_open(sym, trade, signal)

            # Telegram notify
            if self.telegram:
                try:
                    emoji = "[BUY]" if side == OrderSide.BUY else "[SELL]"
                    await self.telegram.send_message(
                        f"{emoji} <b>{sym} Trade Opened</b>\n"
                        f"Direction: {trade.direction.value}\n"
                        f"Entry: {trade.entry_price:.2f}\n"
                        f"SL: {trade.stop_loss:.2f} | TP: {trade.take_profit:.2f}\n"
                        f"Qty: {trade.quantity:.2f} lots\n"
                        f"Score: {signal.total_score}"
                    )
                except Exception:
                    pass

            _log(f"  [{sym}] {side.value} {quantity} lots @ {trade.entry_price:.2f} "
                 f"SL:{trade.stop_loss:.2f} TP:{trade.take_profit:.2f} Score:{signal.total_score}")

    # ----- Trade monitoring -----

    def _check_open_trades_all(self):
        """Check open trades for SL/TP hits across all symbols."""
        if not self.mt5_connected:
            return

        try:
            import MetaTrader5 as mt5
            from graxia.packages.quant_os.gold_bot.core.engine import SignalDirection
        except ImportError:
            return

        for state in self.symbol_states.values():
            if not state.open_trades:
                continue

            try:
                tick = mt5.symbol_info_tick(state.symbol)
                if not tick:
                    continue

                current_price = float((tick.bid + tick.ask) / 2)
                to_close = []

                for trade in state.open_trades:
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

                        cfg = SYMBOL_CONFIGS.get(state.symbol, SYMBOL_CONFIGS["XAUUSD"])
                        pnl_dollars = pnl_pips * trade.quantity * (cfg["units_per_lot"] / 100)

                        trade.exit_price = exit_price
                        trade.pnl = pnl_dollars
                        trade.status = "CLOSED"
                        state.open_trades.remove(trade)
                        state.closed_trades.append(trade)
                        state.daily_pnl += pnl_dollars
                        self.daily_pnl += pnl_dollars

                        is_win = pnl_dollars > 0
                        tag = "[WIN]" if is_win else "[LOSS]"
                        _log(f"  {tag} [{state.symbol}] CLOSED ({reason}): "
                             f"{trade.entry_price:.2f} -> {exit_price:.2f} P&L=${pnl_dollars:+.2f}")

                        self._log_trade_close(state.symbol, trade, exit_price, pnl_dollars, reason)

                        if self.telegram:
                            try:
                                emoji = "WIN" if is_win else "LOSS"
                                asyncio.ensure_future(self.telegram.send_message(
                                    f"[{emoji}] <b>{state.symbol} Trade Closed ({reason})</b>\n"
                                    f"Entry: {trade.entry_price:.2f} -> Exit: {exit_price:.2f}\n"
                                    f"P&L: ${pnl_dollars:+.2f}\n"
                                    f"Score: {trade.strategy_scores.get('total', '?')}"
                                ))
                            except Exception:
                                pass
                    except Exception as e:
                        _log(f"  [CLOSE] Error closing trade [{state.symbol}]: {e}")

            except Exception:
                pass

    # ----- Logging -----

    def _log_trade_open(self, symbol: str, trade, signal):
        """Log trade open to CSV."""
        self.csv_writer.writerow([
            trade.entry_time.isoformat(),
            symbol,
            trade.direction.value,
            f"{trade.entry_price:.2f}",
            "",
            f"{trade.stop_loss:.2f}",
            f"{trade.take_profit:.2f}",
            f"{trade.quantity:.2f}",
            "",
            "",
            signal.total_score,
            ",".join(trade.strategy_scores.keys()),
            "OPEN"
        ])
        self.csv_file.flush()

    def _log_trade_close(self, symbol: str, trade, exit_price: float, pnl: float, reason: str):
        """Log trade close to CSV."""
        self.csv_writer.writerow([
            datetime.now(timezone.utc).isoformat(),
            symbol,
            trade.direction.value,
            f"{trade.entry_price:.2f}",
            f"{exit_price:.2f}",
            f"{trade.stop_loss:.2f}",
            f"{trade.take_profit:.2f}",
            f"{trade.quantity:.2f}",
            f"{pnl:+.2f}",
            "",
            "",
            ",".join(trade.strategy_scores.keys()),
            reason
        ])
        self.csv_file.flush()

    # ----- Reporting -----

    def _print_status(self):
        """Print periodic status for all symbols."""
        elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds() / 3600
        _log(f"\n  [{elapsed:.1f}h] Cycle {self.cycle_count}")

        for state in self.symbol_states.values():
            wins = sum(1 for t in state.closed_trades if t.pnl > 0)
            total = len(state.closed_trades)
            win_rate = (wins / total * 100) if total > 0 else 0
            total_pnl = sum(t.pnl for t in state.closed_trades)
            _log(f"  {state.symbol}: {total} trades | Win {win_rate:.0f}% | "
                 f"P&L ${total_pnl:+,.2f} | Open {len(state.open_trades)}")

    async def _print_summary(self):
        """Print final summary."""
        elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds() / 3600

        _log("\n" + "=" * 70)
        _log("  GOLD BOT -- Multi-Symbol Paper Trading Summary")
        _log("=" * 70)
        _log(f"\n  Duration: {elapsed:.1f} hours")
        _log(f"  Total Cycles: {self.cycle_count}")

        for state in self.symbol_states.values():
            engine = state.engine
            _log(f"\n  [{state.symbol}]")
            _log(f"  Open: {len(state.open_trades)} | Closed: {len(state.closed_trades)}")

            if state.closed_trades:
                wins = sum(1 for t in state.closed_trades if t.pnl > 0)
                losses = len(state.closed_trades) - wins
                total_pnl = sum(t.pnl for t in state.closed_trades)
                win_rate = wins / len(state.closed_trades) * 100

                _log(f"  Win Rate: {win_rate:.1f}% ({wins}W / {losses}L)")
                _log(f"  Total P&L: ${total_pnl:+,.2f}")

            _log(f"  League Status:")
            for tier in ["S", "A", "B", "C", "BENCH"]:
                members = [n for n, s in engine.strategy_stats.items()
                           if s.get("league_tier") == tier]
                if members:
                    _log(f"    Tier {tier}: {', '.join(members)}")

    async def _send_daily_report(self):
        """Send daily report via Telegram."""
        if not self.telegram:
            return

        try:
            lines = ["Daily Report\n"]
            total_trades = 0
            total_pnl = 0.0
            total_wins = 0

            for state in self.symbol_states.values():
                wins = sum(1 for t in state.closed_trades if t.pnl > 0)
                n = len(state.closed_trades)
                pnl = sum(t.pnl for t in state.closed_trades)
                wr = (wins / n * 100) if n > 0 else 0
                total_trades += n
                total_pnl += pnl
                total_wins += wins
                lines.append(f"{state.symbol}: {n} trades, WR {wr:.0f}%, P&L ${pnl:+,.2f}")

            wr_all = (total_wins / total_trades * 100) if total_trades > 0 else 0
            lines.insert(1, f"Total: {total_trades} trades, WR {wr_all:.0f}%, P&L ${total_pnl:+,.2f}")

            await self.telegram.send_message("\n".join(lines))
            _log(f"  [DAILY REPORT] Sent via Telegram")
        except Exception as e:
            _log(f"  [DAILY REPORT] Error: {e}")

    def _save_summary(self):
        """Save summary to JSON."""
        summary = {
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": datetime.now(timezone.utc).isoformat(),
            "cycles": self.cycle_count,
            "symbols": {},
        }

        for state in self.symbol_states.values():
            summary["symbols"][state.symbol] = {
                "open_trades": len(state.open_trades),
                "closed_trades": len(state.closed_trades),
                "wins": sum(1 for t in state.closed_trades if t.pnl > 0),
                "total_pnl": sum(t.pnl for t in state.closed_trades),
            }

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.log_dir / f"multi_summary_{timestamp}.json"

        with open(path, "w") as f:
            json.dump(summary, f, indent=2)

        _log(f"\n  Summary saved: {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Gold Bot Multi-Symbol Paper Trading")
    parser.add_argument("--duration", type=int, default=168,
                        help="Duration in hours (0 = unlimited)")
    parser.add_argument("--capital", type=float, default=49911.92,
                        help="Initial capital")
    parser.add_argument("--risk", type=float, default=0.25,
                        help="Max risk per trade %%")
    parser.add_argument("--symbols", type=str, nargs="+",
                        default=["XAUUSD", "EURUSD", "BTCUSD"],
                        help="Symbols to trade")
    args = parser.parse_args()

    config = MultiConfig(
        symbols=args.symbols,
        initial_capital=args.capital,
        max_risk_per_trade_pct=args.risk,
    )

    trader = MultiSymbolTrader(config)

    if args.duration > 0:
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
