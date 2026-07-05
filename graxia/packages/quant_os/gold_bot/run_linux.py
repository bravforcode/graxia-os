"""
Gold Bot Paper Trading for Linux VPS.
Standalone version using yfinance for prices.
"""
import sys
import os
import time
import signal
import json
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum

sys.path.insert(0, '/opt/goldbot')

from gold_bot.core.engine import GoldBotEngine, SignalDirection
from gold_bot.core.config import BotConfig
from gold_bot.mt5_adapter import MT5Connection, TIMEFRAME_M15
from gold_bot.core.risk_bridge import RiskBridge

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

LOG_DIR = Path('/opt/goldbot/logs')
LOG_DIR.mkdir(parents=True, exist_ok=True)
TRADE_CSV = LOG_DIR / 'linux_trades.csv'
PID_FILE = LOG_DIR / 'linux_paper.pid'
LOG_FILE = LOG_DIR / 'linux_paper.log'
HEALTH_FILE = LOG_DIR / 'health_report_latest.json'
ERROR_LOG = LOG_DIR / 'linux_paper_err.log'


@dataclass
class Trade:
    symbol: str
    direction: SignalDirection
    entry_price: float
    sl: float
    tp: float
    score: float
    strategies: set = field(default_factory=set)
    entry_time: datetime = field(default_factory=datetime.now)
    stop_loss: float = 0
    take_profit: float = 0
    pnl: float = 0
    status: str = "OPEN"

    def __post_init__(self):
        self.stop_loss = self.sl
        self.take_profit = self.tp


def _log(msg):
    print(msg, flush=True)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8', errors='replace') as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {msg}\n")
    except Exception:
        pass


def _log_err(msg):
    try:
        with open(ERROR_LOG, 'a', encoding='utf-8', errors='replace') as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {msg}\n")
    except Exception:
        pass


def _send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception:
        pass


def _write_csv_header(f):
    f.write("timestamp,direction,entry,exit,sl,tp,score,strategies,pnl,status\n")


def main():
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    _log("=" * 60)
    _log("GOLD BOT LINUX PAPER TRADING")
    _log(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    _log(f"PID: {os.getpid()}")
    _log("=" * 60)

    config = BotConfig()
    config.sl_distance_points = 100
    config.tp_distance_points = 200
    config.risk_reward_ratio = 2.0
    config.min_score_to_trade = 280
    config.max_open_trades = 3
    config.risk_per_trade_pct = 0.0025

    _log("Connecting to MT5 adapter (yfinance)...")
    mt5 = MT5Connection()
    if not mt5.initialize():
        _log("FATAL: MT5 adapter failed")
        return
    _log("MT5 adapter connected (using yfinance)")

    engine = GoldBotEngine(config)
    engine._register_strategies()
    strategies = engine.strategies
    _log(f"Loaded {len(strategies)} strategies")

    risk_bridge = RiskBridge(config)

    try:
        from gold_bot.ai.validator import ClaudeAIValidator
        ai_validator = ClaudeAIValidator(config)
        has_ai = True
        _log("AI Validator: available")
    except Exception as e:
        has_ai = False
        _log(f"AI Validator: not available ({e}), using score fallback")

    open_trades: List[Trade] = []
    closed_trades: List[Trade] = []
    total_pnl = 0.0
    last_trade_time = None
    last_daily_report = datetime.now()
    min_score = config.min_score_to_trade
    cycles = 0
    last_price = 0.0
    symbol = "XAUUSD"
    point = 0.01

    _log(f"Symbol: {symbol}")
    _log(f"Max open trades: {config.max_open_trades}")
    _log(f"Risk per trade: {config.risk_per_trade_pct*100:.2f}%")
    _log(f"Min score: {min_score}")
    _log("-" * 60)

    csv_file = open(TRADE_CSV, "w", encoding="utf-8")
    _write_csv_header(csv_file)

    running = True

    def signal_handler(sig, frame):
        nonlocal running
        _log("Shutdown signal received...")
        running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    while running:
        try:
            cycles += 1
            cycle_start = time.time()

            rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME_M15, 0, 100)
            if not rates or len(rates) < 20:
                time.sleep(15)
                continue

            current_price = rates[-1].close

            # SL/TP monitoring — always runs (even when price is stale)
            for trade in list(open_trades):
                hit_sl = False
                hit_tp = False
                exit_price = 0

                if trade.direction == SignalDirection.BUY:
                    if rates[-1].low <= trade.stop_loss:
                        hit_sl = True
                        exit_price = trade.stop_loss
                    elif rates[-1].high >= trade.take_profit:
                        hit_tp = True
                        exit_price = trade.take_profit
                else:
                    if rates[-1].high >= trade.stop_loss:
                        hit_sl = True
                        exit_price = trade.stop_loss
                    elif rates[-1].low <= trade.take_profit:
                        hit_tp = True
                        exit_price = trade.take_profit

                if hit_sl or hit_tp:
                    if trade.direction == SignalDirection.BUY:
                        pnl_pips = (exit_price - trade.entry_price) / point
                    else:
                        pnl_pips = (trade.entry_price - exit_price) / point
                    pnl = pnl_pips * 0.10  # $0.10 per pip for 0.01 lot XAUUSD cent account

                    trade.pnl = pnl
                    trade.status = "CLOSED"
                    total_pnl += pnl

                    reason = "SL" if hit_sl else "TP"
                    _log(f"CLOSE ({reason}): {symbol} {trade.direction.value} @ {exit_price:.2f} | PnL: ${pnl:.2f}")
                    _send_telegram(f"{reason}: {symbol} {trade.direction.value} @ {exit_price:.2f} | PnL: ${pnl:.2f}")

                    csv_file.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')},{trade.direction.value},{trade.entry_price:.2f},{exit_price:.2f},{trade.stop_loss:.2f},{trade.take_profit:.2f},{trade.score},{'+'.join(trade.strategies)},{pnl:.2f},CLOSED\n")
                    csv_file.flush()

                    open_trades.remove(trade)
                    closed_trades.append(trade)

            # Trailing stop — always runs
            for trade in list(open_trades):
                if trade.direction == SignalDirection.BUY:
                    profit_pips = (current_price - trade.entry_price) / point
                else:
                    profit_pips = (trade.entry_price - current_price) / point
                if profit_pips <= 0:
                    continue
                # Breakeven at 30 pips profit
                if profit_pips >= 30:
                    if trade.direction == SignalDirection.BUY:
                        new_sl = trade.entry_price + point
                        if trade.stop_loss < new_sl:
                            trade.stop_loss = new_sl
                            _log(f"  [BE] BUY SL->{new_sl:.2f} (profit={profit_pips:.0f}p)")
                    else:
                        new_sl = trade.entry_price - point
                        if trade.stop_loss > new_sl:
                            trade.stop_loss = new_sl
                            _log(f"  [BE] SELL SL->{new_sl:.2f} (profit={profit_pips:.0f}p)")
                # Trail at 50 pips profit
                if profit_pips >= 50:
                    if trade.direction == SignalDirection.BUY:
                        new_sl = current_price - (50 * point)
                        if trade.stop_loss < new_sl:
                            trade.stop_loss = new_sl
                            _log(f"  [TRAIL] BUY SL->{new_sl:.2f} (profit={profit_pips:.0f}p)")
                    else:
                        new_sl = current_price + (50 * point)
                        if trade.stop_loss > new_sl:
                            trade.stop_loss = new_sl
                            _log(f"  [TRAIL] SELL SL->{new_sl:.2f} (profit={profit_pips:.0f}p)")

            # Stale price — skip new entry only (SL/TP + trail already ran)
            price_stale = (current_price == last_price and last_price != 0)
            if not price_stale:
                last_price = current_price

            if price_stale:
                time.sleep(15)
                continue

            if len(open_trades) >= config.max_open_trades:
                time.sleep(15)
                continue

            if last_trade_time and (datetime.now() - last_trade_time).total_seconds() < 300:
                time.sleep(15)
                continue

            data = {"M15": {
                "close": [r.close for r in rates],
                "high": [r.high for r in rates],
                "low": [r.low for r in rates],
                "volume": [r.tick_volume for r in rates],
            }}
            engine.price_cache = {"mid": current_price}

            signals = []
            for name, strategy in engine.strategies.items():
                if not engine.strategy_stats[name]["active"]:
                    continue
                try:
                    sig = strategy.analyze(data=data, current_price=current_price, symbol=symbol)
                    if sig:
                        signals.append(sig)
                        engine.strategy_stats[name]["signals"] += 1
                except Exception:
                    pass

            if not signals:
                time.sleep(15)
                continue

            aggregated = engine._aggregate_signals(signals)
            if aggregated.total_score < min_score:
                time.sleep(15)
                continue

            ai_ok = True
            if has_ai:
                try:
                    ai_ok = ai_validator.validate(aggregated)
                except Exception:
                    ai_ok = aggregated.total_score >= (min_score * 1.2)
            if not ai_ok:
                time.sleep(15)
                continue

            risk_result = risk_bridge.check(
                signal=aggregated,
                open_trades=open_trades,
                daily_pnl=total_pnl,
                balance=config.initial_capital + total_pnl,
                equity=config.initial_capital + total_pnl,
            )
            if not risk_result.approved:
                _log(f"[RISK] Rejected: {risk_result.reason}")
                time.sleep(15)
                continue

            sl_points = config.sl_distance_points
            tp_points = config.tp_distance_points

            if aggregated.direction == SignalDirection.BUY:
                sl = current_price - (sl_points * point)
                tp = current_price + (tp_points * point)
            else:
                sl = current_price + (sl_points * point)
                tp = current_price - (tp_points * point)

            trade = Trade(
                symbol=symbol,
                direction=aggregated.direction,
                entry_price=current_price,
                sl=sl,
                tp=tp,
                score=aggregated.total_score,
                strategies=set(s.strategy_name for s in aggregated.signals),
            )

            open_trades.append(trade)
            last_trade_time = datetime.now()

            _log(f"OPEN: {symbol} {aggregated.direction.value} @ {current_price:.2f} | SL: {sl:.2f} | TP: {tp:.2f} | Score: {aggregated.total_score}")
            _send_telegram(f"OPEN: {symbol} {aggregated.direction.value} @ {current_price:.2f} | Score: {aggregated.total_score}")

            csv_file.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')},{aggregated.direction.value},{current_price:.2f},,{sl:.2f},{tp:.2f},{aggregated.total_score},{'+'.join(s.strategy_name for s in aggregated.signals)},,OPEN\n")
            csv_file.flush()

            if last_trade_time and (datetime.now() - last_trade_time).total_seconds() > 3600 and min_score > 250:
                min_score = max(250, min_score - 10)
                _log(f"[AUTO-ADJUST] min_score lowered to {min_score}")

            if (datetime.now() - last_daily_report).total_seconds() > 86400:
                report = f"DAILY REPORT\nCycles: {cycles}\nOpen: {len(open_trades)}\nClosed: {len(closed_trades)}\nTotal PnL: ${total_pnl:.2f}"
                _send_telegram(report)
                last_daily_report = datetime.now()
                _log(f"DAILY REPORT sent | PnL: ${total_pnl:.2f}")

            if cycles % 10 == 0:
                _log(f"Heartbeat: cycle={cycles} open={len(open_trades)} closed={len(closed_trades)} pnl=${total_pnl:.2f} min_score={min_score}")

            try:
                health = {
                    "timestamp": datetime.now().isoformat(),
                    "bot_running": True,
                    "pid": os.getpid(),
                    "cycles": cycles,
                    "open_trades": len(open_trades),
                    "closed_trades": len(closed_trades),
                    "total_pnl": total_pnl,
                    "min_score": min_score,
                }
                HEALTH_FILE.write_text(json.dumps(health, indent=2), encoding="utf-8")
            except Exception:
                pass

            time.sleep(15)

        except KeyboardInterrupt:
            _log("KeyboardInterrupt received")
            running = False
        except Exception as e:
            _log_err(f"Cycle error: {e}\n{traceback.format_exc()}")
            time.sleep(5)

    _log("Shutting down...")
    _log(f"FINAL: cycles={cycles} open={len(open_trades)} closed={len(closed_trades)} pnl=${total_pnl:.2f}")
    _send_telegram(f"BOT STOPPED | Total PnL: ${total_pnl:.2f}")
    csv_file.close()
    mt5.shutdown()
    PID_FILE.unlink(missing_ok=True)
    _log("Shutdown complete")


if __name__ == "__main__":
    main()
