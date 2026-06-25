"""
Paper Trading Script — Liquidity Sweep Architecture (Phases 1-6 wired).

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
import csv
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional, Dict

sys.path.insert(0, os.getcwd())

from graxia.packages.quant_os.core.config import QuantConfig, get_config
from graxia.packages.quant_os.core.enums import TradingMode, OrderSide, OrderType
from graxia.packages.quant_os.execution.broker_adapter import PaperBroker
from graxia.packages.quant_os.execution.order import Order
from graxia.packages.quant_os.monitoring.telegram import TelegramNotifier
from graxia.packages.quant_os.regime import RegimeDetector
from graxia.packages.quant_os.regime.liquidity_map import LiquidityMap, get_session
from graxia.packages.quant_os.regime.sweep_classifier import SweepClassifier
from graxia.packages.quant_os.regime.entry_executor import EntryExecutor
from graxia.packages.quant_os.regime.risk_overlay import RiskOverlay
from graxia.packages.quant_os.regime.monitor import Monitor, OrderReport as MonOrderReport, FillReport as MonFillReport


class PaperTrader:
    """Paper trading engine — Liquidity Sweep pipeline on live MT5 data."""

    def __init__(self, config: QuantConfig = None, telegram_token: str = None, telegram_chat: str = None, verbose: bool = True):
        self.config = config or get_config()
        self.broker = PaperBroker()
        self.telegram = TelegramNotifier(bot_token=telegram_token or os.getenv("TELEGRAM_BOT_TOKEN", ""),
                                          chat_id=telegram_chat or os.getenv("TELEGRAM_CHAT_ID", "")) if (telegram_token or telegram_chat or os.getenv("TELEGRAM_BOT_TOKEN")) else None

        self.verbose = verbose

        # Phase components (reusable)
        self.regime_detector = RegimeDetector()
        self.risk_overlay = RiskOverlay(initial_balance=float(self.config.paper_initial_capital))
        self.monitor = Monitor(initial_balance=float(self.config.paper_initial_capital))

        # State
        self.is_running = False
        self.last_signal_time: Optional[datetime] = None
        self.signal_cooldown = timedelta(seconds=1)  # per-symbol 300s handles real cooldown
        self._cycle_count = 0
        self._market_cache: Dict[str, list] = {}
        self._open_trades: Dict[str, dict] = {}  # symbol -> entry tracking
        self._closing_positions: set = set()  # symbols being closed (prevent double-close)

        # Per-symbol cooldown (prevents same-signal spam)
        self._entry_cooldowns: Dict[str, datetime] = {}

        # Stats
        self.total_signals = 0
        self.total_trades = 0
        self.start_time: Optional[datetime] = None
        self._trades = []
        self._log_dir = Path("logs")
        self._log_dir.mkdir(exist_ok=True)

    async def start(self, duration_minutes: int = 60):
        """Start paper trading for specified duration"""
        import MetaTrader5 as mt5
        if not mt5.initialize():
            mt5.initialize(path=r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe")

        # Pre-fetch market data (keep as numpy array for named access)
        self._market_cache = {}
        for sym in self.config.symbols:
            rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 300)
            if rates is not None and len(rates) > 0:
                self._market_cache[sym] = rates

        print("=" * 60)
        print("Quant OS - Paper Trading (Liquidity Sweep Architecture)")
        print("=" * 60)

        print("\nConnecting to paper broker...")
        await self.broker.connect()
        account = await self.broker.get_account()
        print(f"Account Balance: ${account.balance:,.2f}")

        self.is_running = True
        self.start_time = datetime.utcnow()
        end_time = self.start_time + timedelta(minutes=duration_minutes)

        print(f"\nStarting paper trading for {duration_minutes} minutes...")
        print(f"Pipeline: Regime -> Liquidity Map -> Sweep Classifier -> Entry Executor -> Risk Overlay -> Monitor")
        print(f"Symbols: {self.config.symbols}")
        print(f"Risk/Trade: {self.config.max_risk_per_trade_pct}%")
        print(f"Daily Loss Limit: {self.config.max_daily_loss_pct}%")
        print(f"Press Ctrl+C to stop\n")

        try:
            while self.is_running and datetime.utcnow() < end_time:
                await self._trading_cycle()
                await asyncio.sleep(10)
        except KeyboardInterrupt:
            print("\n\nStopping paper trading...")
        finally:
            self.is_running = False
            await self._print_summary()
            if self.telegram:
                await self.telegram.close()
            mt5.shutdown()

    async def _trading_cycle(self):
        """Single trading cycle — refresh data, manage positions, check signals."""
        self._cycle_count += 1
        try:
            import MetaTrader5 as mt5
            # Refresh market data (keep as numpy array)
            for sym in self.config.symbols:
                rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 300)
                if rates is not None and len(rates) > 0:
                    self._market_cache[sym] = rates

            # Sync PaperBroker prices with MT5 for realistic fills and P&L
            for sym in self.config.symbols:
                tick = mt5.symbol_info_tick(sym)
                if tick:
                    self.broker.set_price(sym, Decimal(str(tick.bid)), Decimal(str(tick.ask)))

            # Refresh unrealized PnL on all positions with current MT5 prices
            await self.broker.refresh_pnl()

            # Manage open positions (SL/TP checks)
            await self._manage_positions()

            # Signal cooldown
            if self.last_signal_time:
                if datetime.utcnow() - self.last_signal_time < self.signal_cooldown:
                    return

            for symbol in self.config.symbols:
                await self._check_symbol(symbol)

        except Exception as e:
            print(f"Error in cycle: {e}")

    async def _manage_positions(self):
        """Check SL/TP for open trades, close if hit, report results."""
        import MetaTrader5 as mt5
        try:
            positions = await self.broker.get_positions()
            for pos in positions:
                sym = pos.symbol
                tick = mt5.symbol_info_tick(sym)
                if tick is None:
                    continue

                current_price = tick.ask if pos.position_type.value == "LONG" else tick.bid
                entry = float(pos.avg_price)
                side = pos.position_type.value

                # Check if we have trade tracking data
                trade_info = self._open_trades.get(sym)
                sl = trade_info.get("stop_price") if trade_info else None
                tp = trade_info.get("take_profit") if trade_info else None

                # P&L percent
                if side == "LONG":
                    pnl_pct = (current_price - entry) / entry * 100
                else:
                    pnl_pct = (entry - current_price) / entry * 100

                # Check Take Profit
                if tp and ((side == "LONG" and current_price >= tp) or (side == "SELL" and current_price <= tp)):
                    await self._close_position(pos, "TP", pnl_pct)
                    continue

                # Check Stop Loss
                if sl and ((side == "LONG" and current_price <= sl) or (side == "SELL" and current_price >= sl)):
                    await self._close_position(pos, "SL", pnl_pct)
                    continue

                # Hard loss limit (fallback if no SL)
                if pnl_pct < -1.0:
                    await self._close_position(pos, "HARD_SL", pnl_pct)
                    continue

                # Hard take profit (fallback if no TP)
                if pnl_pct > 0.5:
                    await self._close_position(pos, "HARD_TP", pnl_pct)
                    continue

        except Exception:
            pass

    async def _close_position(self, pos, reason: str, pnl_pct: float):
        """Close a position and report to risk/monitor. Idempotent per symbol."""
        if pos.symbol in self._closing_positions:
            return  # already being closed
        self._closing_positions.add(pos.symbol)

        side = OrderSide.SELL if pos.position_type.value == "LONG" else OrderSide.BUY
        order = Order(
            symbol=pos.symbol, side=side, order_type=OrderType.MARKET,
            quantity=pos.quantity, strategy_id="close_" + reason.lower(),
            trading_mode="PAPER",
        )
        result = await self.broker.place_order(order)
        if result.success:
            pnl_usd = float(pos.unrealized_pnl)
            print(f"[{reason}] {pos.symbol} P&L={pnl_usd:+,.2f} USD")
            self.risk_overlay.report_trade_result(pnl_usd)
            self._open_trades.pop(pos.symbol, None)
            self._closing_positions.discard(pos.symbol)

    async def _check_symbol(self, symbol: str):
        """Full Liquidity Sweep pipeline for one symbol."""
        try:
            # Per-symbol cooldown: 300s between entries on same symbol
            last_entry = self._entry_cooldowns.get(symbol)
            if last_entry and (datetime.utcnow() - last_entry).total_seconds() < 300:
                return

            rates = self._market_cache.get(symbol)
            if rates is None or len(rates) < 50:
                return

            # Convert MT5 rates (numpy structured array) to dict list
            has_vol = "tick_volume" in rates.dtype.names
            bars = []
            for r in rates:
                bars.append({
                    "time": datetime.fromtimestamp(int(r["time"])),
                    "open": float(r["open"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "close": float(r["close"]),
                    "volume": int(r["tick_volume"]) if has_vol else 0,
                })

            closes = [b["close"] for b in bars]
            highs = [b["high"] for b in bars]
            lows = [b["low"] for b in bars]
            current_price = closes[-1]

            # Skip if already have position
            existing = [p for p in await self.broker.get_positions() if p.symbol == symbol]
            if existing:
                return

            # Phase 1: Regime Detector
            regime = self.regime_detector.detect(closes, highs, lows)
            if self.verbose:
                print(f"  {symbol}: Phase1={regime.regime} c={regime.confidence:.2f} [{regime.reason_code}]")
            if regime.regime == "UNCLEAR":
                return  # no trade in unclear regime

            # Phase 2: Liquidity Map
            liq_map = LiquidityMap(bars)
            levels = liq_map.build()
            if self.verbose:
                print(f"  {symbol}: Phase2={len(levels)} levels")
            if not levels:
                return

            # Phase 3: Sweep Classifier
            classifier = SweepClassifier(bars, levels, regime.regime, regime.spread_state)
            signals = classifier.classify()
            if self.verbose:
                print(f"  {symbol}: Phase3={len(signals)} signals")
            if not signals:
                return

            # Get current spread
            import MetaTrader5 as mt5
            tick = mt5.symbol_info_tick(symbol)
            spread = (tick.ask - tick.bid) if tick else 0.0
            # Average spread estimate from recent data
            avg_spread = spread * 1.5 if spread > 0 else 0.0002  # ponytail: fallback if no data

            # Session
            session = get_session(datetime.utcnow())
            account = await self.broker.get_account()

            # Phase 4: Entry Executor
            if self.verbose:
                for sig in signals[:3]:
                    print(f"  {symbol}:   signal={sig.signal} side={sig.side} c={sig.confidence:.2f}")
            for signal in signals[:3]:  # max 3 signals per cycle
                executor = EntryExecutor(
                    bars,
                    balance=float(account.balance),
                    spread=spread,
                    avg_spread=avg_spread,
                    session=session,
                )
                entry = executor.evaluate(signal, symbol, current_price)
                if self.verbose:
                    print(f"  {symbol}:   Phase4={entry.reason_code} enter={entry.should_enter}")
                if not entry.should_enter:
                    continue

                stop_distance = abs(entry.entry_price - entry.stop_price)

                # Phase 5: Risk Overlay
                risk_result = self.risk_overlay.approve(
                    risk_amount=entry.risk_amount,
                    stop_distance=stop_distance,
                    current_balance=float(account.balance),
                )
                if self.verbose:
                    print(f"  {symbol}:   Phase5={risk_result.reason_code} size={risk_result.position_size:.2f}")
                if not risk_result.approved:
                    continue

                # Phase 6: Monitor — report order
                order_ts = datetime.utcnow()
                order_report = MonOrderReport(
                    symbol=symbol,
                    side=entry.side,
                    signal_type=signal.signal,
                    session=session,
                    expected_price=entry.entry_price,
                    stop_loss=entry.stop_price,
                    take_profit=entry.take_profit,
                    risk_usd=entry.risk_amount,
                    timestamp_signal=order_ts,
                )
                self.monitor.report_order(order_report)

                # Send order to broker
                order_side = OrderSide.BUY if entry.side == "BUY" else OrderSide.SELL
                order = Order(
                    symbol=symbol,
                    side=order_side,
                    order_type=OrderType.MARKET,
                    quantity=Decimal(str(entry.position_size)),
                    stop_price=Decimal(str(entry.stop_price)),
                    strategy_id="liquidity_sweep",
                    trading_mode="PAPER",
                )
                result = await self.broker.place_order(order)

                if result.success:
                    fill_ts = datetime.utcnow()
                    latency_ms = (fill_ts - order_ts).total_seconds() * 1000
                    fill_price = float(result.avg_fill_price) if result.avg_fill_price else entry.entry_price

                    # Monitor — report fill
                    fill_report = MonFillReport(
                        symbol=symbol,
                        side=entry.side,
                        fill_price=fill_price,
                        fill_quantity=float(result.filled_quantity) if result.filled_quantity else entry.position_size,
                        latency_ms=latency_ms,
                        spread_at_fill=spread,
                    )
                    self.monitor.report_fill(fill_report)

                    # Track trade for position management
                    self._open_trades[symbol] = {
                        "stop_price": entry.stop_price,
                        "take_profit": entry.take_profit,
                        "entry_price": entry.entry_price,
                        "side": entry.side,
                    }

                    self.total_signals += 1
                    self.total_trades += 1
                    self.last_signal_time = datetime.utcnow()
                    self._entry_cooldowns[symbol] = datetime.utcnow()

                    trade = {
                        "time": order_ts.isoformat(),
                        "symbol": symbol,
                        "side": entry.side,
                        "signal": signal.signal,
                        "confidence": signal.confidence,
                        "regime": regime.regime,
                        "session": session,
                        "entry": entry.entry_price,
                        "sl": entry.stop_price,
                        "tp": entry.take_profit,
                        "risk_usd": entry.risk_amount,
                        "fill_price": fill_price,
                        "position_size": entry.position_size,
                        "latency_ms": round(latency_ms, 1),
                    }
                    self._trades.append(trade)

                    print(f"[OK] {entry.side} {symbol} @ {fill_price:.5f} "
                          f"(SL: {entry.stop_price:.5f}, TP: {entry.take_profit:.5f}) "
                          f"[{signal.signal} c={signal.confidence:.2f}]")

                    if self.telegram:
                        await self.telegram.notify_trade(
                            symbol=symbol, side=order_side,
                            quantity=entry.position_size,
                            entry_price=fill_price,
                            stop_loss=entry.stop_price,
                            take_profit=entry.take_profit,
                            strategy=f"liquidity_sweep_{signal.signal}",
                        )
                else:
                    print(f"[X] {symbol}: order failed ({result.error_message})")

                # One trade per symbol per cycle
                break

        except Exception as e:
            print(f"Error {symbol}: {e}")

    async def _print_summary(self):
        """Print trading summary with risk/monitor status."""
        print("\n" + "=" * 60)
        print("PAPER TRADING SUMMARY")
        print("=" * 60)

        account = await self.broker.get_account()
        duration = datetime.utcnow() - self.start_time if self.start_time else timedelta(0)
        pnl = float(account.equity) - self.config.paper_initial_capital

        print(f"Duration: {duration}")
        print(f"Total Signals: {self.total_signals}")
        print(f"Total Trades: {self.total_trades}")
        print(f"Balance: ${account.balance:,.2f}")
        print(f"Equity: ${account.equity:,.2f}")
        print(f"P&L: ${pnl:+,.2f}")

        # Monitor status
        mon = self.monitor.get_status()
        print(f"\n--- Monitor Health: {mon.health_status.value} ---")
        print(f"  Fill rate: {mon.fill_stats.fill_rate:.1%} ({mon.fill_stats.total_fills}/{mon.fill_stats.total_attempts})")
        print(f"  Avg slippage: {mon.slippage_stats.total_bps.mean:.2f} bps")
        print(f"  Avg anomaly:  {mon.slippage_stats.total_anomaly_bps.mean:.2f} bps (spread-exclusive)")
        print(f"  Avg latency: {mon.latency_stats.ms.mean:.0f} ms")
        print(f"  Drawdown: {mon.drawdown_pct:.1f}%")
        if mon.alerts:
            print(f"  Alerts ({len(mon.alerts)}):")
            for a in mon.alerts[:5]:
                print(f"    [{a.level.value}] {a.message}")

        # Risk status
        risk_status = self.risk_overlay.get_status()
        print(f"\n--- Risk Status ---")
        print(f"  Kill switch: {'[R] ACTIVE' if risk_status['kill_switch'] else '[G] Armed'}")
        print(f"  Daily loss used: {risk_status['daily_used_pct']:.1f}%")
        print(f"  Weekly loss used: {risk_status['weekly_used_pct']:.1f}%")
        print(f"  Consecutive losses: {risk_status['consecutive_losses']}")
        print(f"  Trades today: {risk_status['trades_today']}")

        # Positions
        positions = await self.broker.get_positions()
        print(f"\nOpen Positions: {len(positions)}")
        for pos in positions:
            print(f"  {pos.symbol} {pos.position_type.value} {pos.quantity} @ {pos.avg_price} "
                  f"P&L: ${pos.unrealized_pnl:+,.2f}")

        # Telegram
        if self.telegram:
            pnl_emoji = "[G]" if pnl >= 0 else "[R]"
            await self.telegram.send_message(
                f"Paper Trading Complete\n\n"
                f"Duration: {duration}\n"
                f"Signals: {self.total_signals} | Trades: {self.total_trades}\n"
                f"P&L: {pnl_emoji} ${pnl:+,.2f}\n"
                f"Balance: ${account.balance:,.2f}\n"
                f"Equity: ${account.equity:,.2f}\n"
                f"Monitor: {mon.health_status.value}\n"
                f"Kill Switch: {'ACTIVE' if risk_status['kill_switch'] else 'Armed'}\n"
                f"Open Positions: {len(positions)}"
            )

        # Save trades to CSV
        if self._trades:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_path = self._log_dir / f"trades_{ts}.csv"
            with open(csv_path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=self._trades[0].keys())
                w.writeheader()
                w.writerows(self._trades)
            print(f"\nTrades saved: {csv_path}")

            json_path = self._log_dir / f"summary_{ts}.json"
            summary = {
                "duration": str(duration),
                "signals": self.total_signals,
                "trades": self.total_trades,
                "balance": float(account.balance),
                "equity": float(account.equity),
                "pnl": pnl,
                "health": mon.health_status.value,
                "fill_rate": mon.fill_stats.fill_rate,
                "avg_slippage_bps": mon.slippage_stats.total_bps.mean,
                "avg_anomaly_bps": mon.slippage_stats.total_anomaly_bps.mean,
                "avg_latency_ms": mon.latency_stats.ms.mean,
                "kill_switch": risk_status["kill_switch"],
                "positions": len(positions),
            }
            json_path.write_text(json.dumps(summary, indent=2))
            print(f"Summary saved: {json_path}")


async def main():
    """Main entry point"""
    import argparse
    parser = argparse.ArgumentParser(description="Paper Trading — Liquidity Sweep Pipeline")
    parser.add_argument("--duration", type=int, default=60,
                        help="Run duration in minutes (default: 60, 0 = forever)")
    parser.add_argument("--symbols", type=str, nargs="+",
                        default=["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "XAUUSD"],
                        help="Symbols to trade (space-separated)")
    args = parser.parse_args()

    from graxia.packages.quant_os.core.config import reset_config
    reset_config()

    config = get_config()
    config.trading_mode = TradingMode.PAPER
    config.live_trading_enabled = False
    config.max_risk_per_trade_pct = 0.5
    config.max_daily_loss_pct = 2.0
    config.max_drawdown_pct = 15.0
    config.paper_initial_capital = 50000.0
    config.paper_slippage_pips = 0.5
    config.paper_commission_per_lot = 3.5
    config.max_positions = 8
    config.symbols = args.symbols
    config.mt5_path = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"
    config.mt5_server = os.getenv("MT5_SERVER", "Pepperstone-Demo")
    config.mt5_login = int(os.getenv("MT5_LOGIN", "0"))
    config.mt5_password = os.getenv("MT5_PASSWORD", "")
    config.mt5_timeout_ms = int(os.getenv("MT5_TIMEOUT_MS", "15000"))

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "")

    trader = PaperTrader(config, telegram_token=token, telegram_chat=chat)
    duration = args.duration if args.duration > 0 else 365 * 24 * 60  # 0 = ~1 year
    await trader.start(duration_minutes=duration)


if __name__ == "__main__":
    asyncio.run(main())
