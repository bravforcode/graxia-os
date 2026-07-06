
"""
Gold Bot Multi-Symbol Paper Trading for Linux VPS.
Uses yfinance adapter. Supports XAUUSD, EURUSD, BTCUSD simultaneously.
"""
import sys
import os
import time
import signal
import json
import csv
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict

sys.path.insert(0, '/opt/goldbot')

from gold_bot.core.engine import GoldBotEngine, SignalDirection
from gold_bot.core.config import BotConfig
from gold_bot.mt5_adapter import MT5Connection, TIMEFRAME_M15, POINT_MAP
from gold_bot.core.risk_bridge import RiskBridge

# ---------------------------------------------------------------------------
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

LOG_DIR = Path('/opt/goldbot/logs')
LOG_DIR.mkdir(parents=True, exist_ok=True)
PID_FILE = LOG_DIR / 'multi_linux_paper.pid'
LOG_FILE = LOG_DIR / 'multi_linux_paper.log'
HEALTH_FILE = LOG_DIR / 'health_report_multi_latest.json'
ERROR_LOG = LOG_DIR / 'multi_linux_paper_err.log'

SYMBOLS = ["XAUUSD", "EURUSD", "BTCUSD"]

SYMBOL_CONFIGS = {
    "XAUUSD": {
        "sl_distance_points": 100,
        "tp_distance_points": 200,
    },
    "EURUSD": {
        "sl_distance_points": 0.0010,
        "tp_distance_points": 0.0020,
    },
    "BTCUSD": {
        "sl_distance_points": 500,
        "tp_distance_points": 1000,
    },
}

PIP_VALUE = {
    "XAUUSD": 0.10,
    "EURUSD": 0.10,
    "BTCUSD": 0.10,
}

CYCLE_SLEEP = 15
MAX_POSITIONS_PER_SYMBOL = 1
MAX_POSITIONS_TOTAL = 3
INITIAL_CAPITAL = 100000.0
COOLDOWN_SECONDS = 300


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


def main():
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    _log("=" * 60)
    _log("GOLD BOT MULTI-SYMBOL LINUX PAPER TRADING")
    _log(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    _log(f"PID: {os.getpid()}")
    _log(f"Symbols: {', '.join(SYMBOLS)}")
    _log("=" * 60)

    _log("Connecting to MT5 adapter (yfinance)...")
    mt5 = MT5Connection()
    if not mt5.initialize():
        _log("FATAL: MT5 adapter failed")
        return
    _log("MT5 adapter connected (yfinance mode)")

    engines: Dict[str, GoldBotEngine] = {}
    risk_bridges: Dict[str, RiskBridge] = {}
    for sym in SYMBOLS:
        cfg = BotConfig()
        cfg.symbol = sym
        sym_cfg = SYMBOL_CONFIGS.get(sym, SYMBOL_CONFIGS["XAUUSD"])
        cfg.sl_distance_points = sym_cfg["sl_distance_points"]
        cfg.tp_distance_points = sym_cfg["tp_distance_points"]
        cfg.risk_reward_ratio = 2.0
        cfg.min_score_to_trade = 280
        cfg.max_positions = MAX_POSITIONS_PER_SYMBOL

        engine = GoldBotEngine(cfg)
        engine._register_strategies()
        engines[sym] = engine
        _log(f"Engine [{sym}]: {len(engine.strategies)} strategies loaded")

        risk_cfg = BotConfig()
        risk_cfg.symbol = sym
        risk_bridges[sym] = RiskBridge(risk_cfg)

    try:
        from gold_bot.ai.validator import ClaudeAIValidator
        ai_validator = ClaudeAIValidator(BotConfig())
        has_ai = True
        _log("AI Validator: available")
    except Exception as e:
        has_ai = False
        ai_validator = None
        _log(f"AI Validator: not available ({e}), using score fallback")

    open_trades: List[Trade] = []
    closed_trades: List[Trade] = []
    total_pnl = 0.0
    last_trade_time: Optional[datetime] = None
    last_daily_report = datetime.now()
    cycles = 0
    last_prices: Dict[str, float] = {}
    min_score = 280

    _log(f"Max positions: {MAX_POSITIONS_PER_SYMBOL}/symbol, {MAX_POSITIONS_TOTAL} total")
    _log(f"Risk per trade: 0.25%")
    _log(f"Min score: {min_score}")
    _log(f"Cooldown: {COOLDOWN_SECONDS}s")
    _log("-" * 60)

    csv_files: Dict[str, object] = {}
    for sym in SYMBOLS:
        csv_path = LOG_DIR / f'multi_trades_{sym.replace("/", "_")}.csv'
        is_new = not csv_path.exists() or csv_path.stat().st_size == 0
        f = open(csv_path, "a", encoding="utf-8")
        if is_new:
            f.write("timestamp,direction,entry,exit,sl,tp,score,strategies,pnl,status\n")
        csv_files[sym] = f
        _log(f"Trade log: {csv_path}")

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

            # --- Heartbeat + health check (always-on, every cycle) ---
            if cycles % 10 == 0:
                open_by_sym = {}
                for t in open_trades:
                    open_by_sym[t.symbol] = open_by_sym.get(t.symbol, 0) + 1
                sym_stats = " ".join(f"{s}:{open_by_sym.get(s, 0)}o" for s in SYMBOLS)
                _log(f"Heartbeat: cycle={cycles} open={len(open_trades)} closed={len(closed_trades)} pnl=${total_pnl:.2f} score={min_score} | {sym_stats}")

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
                    "symbols": {s: sum(1 for t in open_trades if t.symbol == s) for s in SYMBOLS},
                }
                HEALTH_FILE.write_text(json.dumps(health, indent=2), encoding="utf-8")
            except Exception:
                pass

            # --- Weekend guard ---
            if datetime.now().weekday() >= 5:
                if cycles % 600 == 0:
                    _log("Weekend - market closed, waiting...")
                time.sleep(15)
                continue

            # --- Process each symbol ---
            for sym in SYMBOLS:
                engine = engines[sym]
                risk_bridge = risk_bridges[sym]
                point = POINT_MAP.get(sym, 0.01)

                rates = mt5.copy_rates_from_pos(sym, TIMEFRAME_M15, 0, 100)
                if not rates or len(rates) < 20:
                    continue

                current_price = rates[-1].close

                # First-cycle init — skip trading
                if sym not in last_prices or last_prices.get(sym) is None:
                    last_prices[sym] = current_price
                    _log(f"[{sym}] First cycle: price={current_price:.2f}, monitoring started")
                    continue

                # --- SL/TP monitoring for this symbol ---
                for trade in list(open_trades):
                    if trade.symbol != sym:
                        continue
                    hit_sl = False
                    hit_tp = False
                    exit_price = 0.0

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
                            pnl_points = (exit_price - trade.entry_price) / point
                        else:
                            pnl_points = (trade.entry_price - exit_price) / point
                        pnl = pnl_points * PIP_VALUE.get(sym, 0.10)

                        trade.pnl = pnl
                        trade.status = "CLOSED"
                        total_pnl += pnl

                        reason = "SL" if hit_sl else "TP"
                        tag = "WIN" if pnl > 0 else "LOSS"
                        _log(f"[{tag}] [{sym}] CLOSE ({reason}): {trade.entry_price:.2f} -> {exit_price:.2f} | PnL: ${pnl:.2f}")
                        _send_telegram(f"{tag}: {sym} {trade.direction.value} @ {exit_price:.2f} | PnL: ${pnl:.2f}")

                        csv_files[sym].write(
                            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')},"
                            f"{trade.direction.value},{trade.entry_price:.2f},"
                            f"{exit_price:.2f},{trade.stop_loss:.2f},"
                            f"{trade.take_profit:.2f},{trade.score},"
                            f"{'+'.join(trade.strategies)},{pnl:.2f},CLOSED\n"
                        )
                        csv_files[sym].flush()

                        open_trades.remove(trade)
                        closed_trades.append(trade)

                # --- Trailing stop ---
                for trade in list(open_trades):
                    if trade.symbol != sym:
                        continue
                    if trade.direction == SignalDirection.BUY:
                        profit_points = (current_price - trade.entry_price) / point
                    else:
                        profit_points = (trade.entry_price - current_price) / point
                    if profit_points <= 0:
                        continue
                    # Breakeven at 30 points profit
                    if profit_points >= 30:
                        if trade.direction == SignalDirection.BUY:
                            new_sl = trade.entry_price + point
                            if trade.stop_loss < new_sl:
                                trade.stop_loss = new_sl
                                _log(f"  [{sym}] BE BUY SL->{new_sl:.2f} (profit={profit_points:.0f}p)")
                        else:
                            new_sl = trade.entry_price - point
                            if trade.stop_loss > new_sl:
                                trade.stop_loss = new_sl
                                _log(f"  [{sym}] BE SELL SL->{new_sl:.2f} (profit={profit_points:.0f}p)")
                    # Trail at 50 points profit
                    if profit_points >= 50:
                        if trade.direction == SignalDirection.BUY:
                            new_sl = current_price - (50 * point)
                            if trade.stop_loss < new_sl:
                                trade.stop_loss = new_sl
                                _log(f"  [{sym}] TRAIL BUY SL->{new_sl:.2f} (profit={profit_points:.0f}p)")
                        else:
                            new_sl = current_price + (50 * point)
                            if trade.stop_loss > new_sl:
                                trade.stop_loss = new_sl
                                _log(f"  [{sym}] TRAIL SELL SL->{new_sl:.2f} (profit={profit_points:.0f}p)")

                # --- Stale price guard ---
                price_stale = (current_price == last_prices.get(sym))
                if not price_stale:
                    last_prices[sym] = current_price
                if price_stale:
                    continue

                # --- Position limits ---
                open_for_sym = sum(1 for t in open_trades if t.symbol == sym)
                if open_for_sym >= MAX_POSITIONS_PER_SYMBOL:
                    continue
                if len(open_trades) >= MAX_POSITIONS_TOTAL:
                    continue

                # --- Cooldown ---
                if last_trade_time and (datetime.now() - last_trade_time).total_seconds() < COOLDOWN_SECONDS:
                    continue

                # --- Strategy execution ---
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
                        sig = strategy.analyze(data=data, current_price=current_price, symbol=sym)
                        if sig:
                            signals.append(sig)
                            engine.strategy_stats[name]["signals"] += 1
                    except Exception:
                        pass

                if not signals:
                    continue

                aggregated = engine._aggregate_signals(signals)
                if aggregated.total_score < min_score:
                    continue

                # --- AI validation ---
                ai_ok = True
                if has_ai:
                    try:
                        ai_ok = ai_validator.validate(aggregated)
                    except Exception:
                        ai_ok = aggregated.total_score >= (min_score * 1.2)
                if not ai_ok:
                    continue

                # --- Risk bridge ---
                sym_open = [t for t in open_trades if t.symbol == sym]
                risk_result = risk_bridge.check(
                    signal=aggregated,
                    open_trades=sym_open,
                    daily_pnl=total_pnl,
                    balance=INITIAL_CAPITAL + total_pnl,
                    equity=INITIAL_CAPITAL + total_pnl,
                )
                if not risk_result.approved:
                    _log(f"[{sym}] RISK Rejected: {risk_result.reason}")
                    continue

                # --- Calculate SL/TP ---
                sl_points = SYMBOL_CONFIGS[sym]["sl_distance_points"]
                tp_points = SYMBOL_CONFIGS[sym]["tp_distance_points"]

                if aggregated.direction == SignalDirection.BUY:
                    sl = current_price - sl_points
                    tp = current_price + tp_points
                else:
                    sl = current_price + sl_points
                    tp = current_price - tp_points

                trade = Trade(
                    symbol=sym,
                    direction=aggregated.direction,
                    entry_price=current_price,
                    sl=sl,
                    tp=tp,
                    score=aggregated.total_score,
                    strategies=set(s.strategy_name for s in aggregated.signals),
                )

                open_trades.append(trade)
                last_trade_time = datetime.now()

                _log(f"[{sym}] OPEN: {aggregated.direction.value} @ {current_price:.2f} | SL: {sl:.2f} | TP: {tp:.2f} | Score: {aggregated.total_score}")
                _send_telegram(f"OPEN: {sym} {aggregated.direction.value} @ {current_price:.2f} | Score: {aggregated.total_score}")

                csv_files[sym].write(
                    f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')},"
                    f"{aggregated.direction.value},{current_price:.2f},,"
                    f"{sl:.2f},{tp:.2f},{aggregated.total_score},"
                    f"{'+'.join(s.strategy_name for s in aggregated.signals)},,OPEN\n"
                )
                csv_files[sym].flush()

            # --- Auto-adjust min score ---
            if last_trade_time and (datetime.now() - last_trade_time).total_seconds() > 3600 and min_score > 250:
                min_score = max(250, min_score - 10)
                _log(f"[AUTO-ADJUST] min_score lowered to {min_score}")

            # --- Daily report ---
            if (datetime.now() - last_daily_report).total_seconds() > 86400:
                by_sym = {}
                for t in closed_trades:
                    by_sym.setdefault(t.symbol, []).append(t)
                lines = [
                    "DAILY REPORT",
                    f"Cycles: {cycles}",
                    f"Open: {len(open_trades)} | Closed: {len(closed_trades)}",
                    f"Total PnL: ${total_pnl:.2f}",
                ]
                for sym in SYMBOLS:
                    sym_trades = by_sym.get(sym, [])
                    sym_pnl = sum(t.pnl for t in sym_trades)
                    lines.append(f"  {sym}: {len(sym_trades)} trades, PnL: ${sym_pnl:.2f}")
                _send_telegram("\n".join(lines))
                last_daily_report = datetime.now()
                _log(f"DAILY REPORT sent | PnL: ${total_pnl:.2f}")

            time.sleep(CYCLE_SLEEP)

        except KeyboardInterrupt:
            _log("KeyboardInterrupt received")
            running = False
        except Exception as e:
            _log_err(f"Cycle error: {e}\n{traceback.format_exc()}")
            time.sleep(5)

    # --- Shutdown ---
    _log("Shutting down...")
    _log(f"FINAL: cycles={cycles} open={len(open_trades)} closed={len(closed_trades)} pnl=${total_pnl:.2f}")
    _send_telegram(f"MULTI BOT STOPPED | Total PnL: ${total_pnl:.2f}")

    summary = {
        "end_time": datetime.now().isoformat(),
        "cycles": cycles,
        "total_pnl": total_pnl,
        "symbols": {},
    }
    for sym in SYMBOLS:
        sym_trades = [t for t in closed_trades if t.symbol == sym]
        summary["symbols"][sym] = {
            "closed": len(sym_trades),
            "wins": sum(1 for t in sym_trades if t.pnl > 0),
            "pnl": sum(t.pnl for t in sym_trades),
        }
    summary_path = LOG_DIR / f'multi_summary_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _log(f"Summary saved: {summary_path}")

    for f in csv_files.values():
        f.close()
    mt5.shutdown()
    PID_FILE.unlink(missing_ok=True)
    _log("Shutdown complete.")


if __name__ == "__main__":
    main()
