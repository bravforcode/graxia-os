"""
DONCHIAN BTCUSD H1 — LIVE DEMO TRADING

Places REAL orders on Pepperstone-Demo via MT5.
Config loaded from config/strategy_config.json (period=35, 1% risk, 2x/3x ATR SL/TP).
Kill switch closes all positions at 5% drawdown.

Usage:
    python scripts/live_donchian.py              # default: 30 days
    python scripts/live_donchian.py --hours 24
    python scripts/live_donchian.py --dry-run    # log signals without placing orders
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
os.chdir(_project_root)
sys.path.insert(0, str(_project_root))

import numpy as np
import pandas as pd

# ── Config (reads from config/strategy_config.json) ──────────────
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "strategy_config.json"
_cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))

SYMBOL = _cfg["symbol"]
TIMEFRAME = _cfg["timeframe"]
BARS = 200
STRATEGY_PARAMS = _cfg["params"]
SPREAD_BPS = _cfg["spread_bps"]
SL_ATR_MULT = _cfg["sl_atr_mult"]
TP_ATR_MULT = _cfg["tp_atr_mult"]
RISK_PER_TRADE_PCT = _cfg["risk_per_trade_pct"]
MAX_DRAWDOWN_PCT = _cfg["max_drawdown_pct"]
MAX_HOLD_BARS = _cfg["max_hold_bars"]
TRAIL_BREAKEVEN_ATR = _cfg["trail_breakeven_atr"]

print(f"  Config loaded from: {_CONFIG_PATH.name}")
print(f"  Params: period={STRATEGY_PARAMS['period']}, vol_filter={STRATEGY_PARAMS['vol_filter']}")
print(f"  SL/TP: {SL_ATR_MULT}x/{TP_ATR_MULT}x ATR | Risk: {RISK_PER_TRADE_PCT}%")

LOG_DIR = _project_root / "logs" / "live_donchian"
REPORTS_DIR = _project_root / "reports" / "live_trading"


# ── ATR ──────────────────────────────────────────────────────────
def compute_atr(highs, lows, closes, period=14):
    n = len(closes)
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    atr = np.full(n, np.nan)
    if n >= period:
        atr[period] = np.mean(tr[1:period + 1])
        for i in range(period + 1, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


# ── Donchian Signal ──────────────────────────────────────────────
def donchian_signal(closes, highs, lows, params):
    period = params.get("period", 20)
    vol_filter = params.get("vol_filter", True)
    atr_period = params.get("atr_period", 14)
    n = len(closes)
    if n < period + 2:
        return 0, 0.0, 0.0, ""
    i = n - 1
    hh = np.max(highs[i - period: i])
    ll = np.min(lows[i - period: i])
    atr = compute_atr(highs, lows, closes, atr_period)
    if np.isnan(atr[i]) or atr[i] <= 0 or closes[i] <= 0:
        return 0, 0.0, 0.0, ""

    atr_ratio_all = np.where(closes > 0, atr / closes, 0)
    med = np.nanmedian(atr_ratio_all[max(0, i - 200):i]) if i > 0 else 0
    vol_ok = (atr[i] / closes[i] > med * 0.8) if vol_filter and med > 0 else True

    if closes[i] > hh and vol_ok:
        return 1, closes[i] - atr[i] * SL_ATR_MULT, closes[i] + atr[i] * TP_ATR_MULT, f"BREAKOUT_LONG hh={hh:.2f}"
    elif closes[i] < ll and vol_ok:
        return -1, closes[i] + atr[i] * SL_ATR_MULT, closes[i] - atr[i] * TP_ATR_MULT, f"BREAKOUT_SHORT ll={ll:.2f}"
    return 0, 0.0, 0.0, ""


# ── MT5 Order Functions ──────────────────────────────────────────
def mt5_get_filling_mode(mt5, symbol):
    """Detect filling mode from MT5 bitmask. Pepperstone BTCUSD=IOC(1)."""
    info = mt5.symbol_info(symbol)
    if info is None:
        return 2  # default RETURN
    filling = info.filling_mode
    if filling & 4:  # RETURN
        return 2
    if filling & 2:  # IOC
        return 1
    if filling & 1:  # FOK
        return 0
    return 2


def mt5_open_order(mt5, symbol, direction, lots, sl, tp, comment="DONCH"):
    """Place a market order on MT5. Returns dict with result or None."""
    order_type = 0 if direction == 1 else 1  # BUY=0, SELL=1
    filling = mt5_get_filling_mode(mt5, symbol)
    info = mt5.symbol_info(symbol)

    request = {
        "action": 1,  # TRADE_ACTION_DEAL
        "symbol": symbol,
        "volume": lots,
        "type": order_type,
        "sl": round(sl, info.digits),
        "tp": round(tp, info.digits),
        "comment": comment,
        "type_filling": filling,
        "type_time": 0,
    }

    result = mt5.order_send(request)
    if result is None:
        print(f"  ERROR: order_send returned None: {mt5.last_error()}")
        return None

    if result.retcode == 10009:
        side = "BUY" if direction == 1 else "SELL"
        print(f"  ORDER FILLED: {side} {lots:.4f} {symbol} @ {result.price:.5f} "
              f"SL={sl:.5f} TP={tp:.5f} ticket={result.order}")
        return {
            "ticket": result.order, "price": result.price,
            "volume": result.volume, "direction": direction,
            "sl": sl, "tp": tp, "lots": lots,
        }
    else:
        print(f"  ORDER FAILED: retcode={result.retcode} {result.comment}")
        return None


def mt5_close_position(mt5, ticket, symbol, direction, lots):
    """Close an open position by placing opposite market order."""
    close_type = 1 if direction == 1 else 0  # opposite direction
    filling = mt5_get_filling_mode(mt5, symbol)

    request = {
        "action": 1,  # TRADE_ACTION_DEAL (opposite market order, not action=5)
        "symbol": symbol,
        "volume": lots,
        "type": close_type,
        "position": ticket,
        "comment": "KILL",
        "type_filling": filling,
        "type_time": 0,
    }

    result = mt5.order_send(request)
    if result and result.retcode == 10009:
        print(f"  POSITION CLOSED: ticket={ticket} @ {result.price:.5f}")
        return result.price
    else:
        rc = result.retcode if result else "None"
        print(f"  CLOSE FAILED: ticket={ticket} retcode={rc}")
        return None


def mt5_close_all(mt5):
    """Close ALL open positions. Kill switch. Uses opposite market orders."""
    positions = mt5.positions_get()
    if not positions:
        print("  No positions to close.")
        return
    print(f"\n  KILL SWITCH: Closing {len(positions)} positions...")
    for pos in positions:
        mt5_close_position(mt5, pos.ticket, pos.symbol,
                           0 if pos.type == 0 else 1, pos.volume)
    print(f"  All positions closed.")


# ── Position Size ────────────────────────────────────────────────
def calc_position_size(mt5, symbol, account_balance, risk_pct, sl_distance):
    """Calculate lot size based on risk %. Returns lots."""
    info = mt5.symbol_info(symbol)
    if info is None:
        return 0.0
    contract_size = info.trade_contract_size  # usually 1 for BTCUSD
    tick_value = info.trade_tick_value  # value per tick
    tick_size = info.trade_tick_size

    if tick_size <= 0 or sl_distance <= 0:
        return 0.0

    risk_dollar = account_balance * risk_pct / 100
    # Lots = risk_dollar / (sl_distance / tick_size * tick_value)
    sl_ticks = sl_distance / tick_size
    value_per_lot = sl_ticks * tick_value
    lots = risk_dollar / value_per_lot if value_per_lot > 0 else 0

    # Clamp to min/max
    lots = max(lots, info.volume_min)
    lots = min(lots, info.volume_max)
    # Round to volume step
    step = info.volume_step
    if step > 0:
        lots = round(lots / step) * step

    return round(lots, 2)


# ── Kill Switch ──────────────────────────────────────────────────
class KillSwitch:
    def __init__(self, mt5, max_dd_pct):
        self.mt5 = mt5
        self.max_dd_pct = max_dd_pct
        self.peak_balance = 0
        self.active = False

    def update(self):
        """Check drawdown. If exceeded, close everything."""
        info = self.mt5.account_info()
        if info is None:
            return
        balance = info.balance
        equity = info.equity

        if balance > self.peak_balance:
            self.peak_balance = balance

        if self.peak_balance > 0:
            dd_pct = (self.peak_balance - equity) / self.peak_balance * 100
            if dd_pct >= self.max_dd_pct and not self.active:
                self.active = True
                print(f"\n  !! KILL SWITCH ACTIVATED !! DD={dd_pct:.1f}% >= {self.max_dd_pct}%")
                print(f"  Peak balance: ${self.peak_balance:,.2f} | Current equity: ${equity:,.2f}")
                mt5_close_all(self.mt5)

    def reset(self):
        self.active = False
        self.peak_balance = 0


# ── Log Trade ────────────────────────────────────────────────────
def log_trade(LOG_DIR, trade_data):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_DIR / "trades.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(trade_data) + "\n")


# ── Main ─────────────────────────────────────────────────────────
def run(args):
    if not args.dry_run and not os.environ.get("QUANT_OS_ALLOW_UNVALIDATED_LIVE"):
        raise SystemExit(
            "BLOCKED: live_donchian.py bypasses the orchestrator/OMS/KillSwitch/"
            "PreTradeRiskGate and trades unvalidated hand-rolled signals directly via MT5. "
            "This is one of the scripts that caused the 2026-07-17 incident "
            "(see reports/incident_unvalidated_scripts_20260717.md). "
            "Do not restart until signal logic is validated through pooled DK tests. "
            "Set QUANT_OS_ALLOW_UNVALIDATED_LIVE=1 to override, or use --dry-run."
        )
    import MetaTrader5 as mt5

    if not mt5.initialize():
        mt5.initialize(path=r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe")

    account = mt5.account_info()
    if not account:
        print("ERROR: No account info")
        return

    tf_const = {
        "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
    }[TIMEFRAME]

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    kill_switch = KillSwitch(mt5, MAX_DRAWDOWN_PCT)
    kill_switch.peak_balance = account.balance

    print("=" * 70)
    print("DONCHIAN BTCUSD H1 — LIVE DEMO TRADING")
    print("=" * 70)
    print(f"  Account:   {account.server} #{account.login}")
    print(f"  Balance:   ${account.balance:,.2f}")
    print(f"  Equity:    ${account.equity:,.2f}")
    print(f"  Leverage:  1:{account.leverage}")
    print(f"  Symbol:    {SYMBOL}")
    print(f"  Strategy:  Donchian({STRATEGY_PARAMS['period']}) vol={STRATEGY_PARAMS['vol_filter']}")
    print(f"  Risk:      {RISK_PER_TRADE_PCT}%/trade")
    print(f"  Kill DD:   {MAX_DRAWDOWN_PCT}%")
    print(f"  SL/TP:     {SL_ATR_MULT}x/{TP_ATR_MULT}x ATR")
    print(f"  Max hold:  {MAX_HOLD_BARS} bars")
    print(f"  Mode:      {'DRY RUN' if args.dry_run else 'LIVE DEMO'}")
    print(f"  Duration:  {args.hours}h ({args.hours/24:.0f} days)")
    print()

    # Pre-fetch data
    rates = mt5.copy_rates_from_pos(SYMBOL, tf_const, 0, BARS)
    if rates is None or len(rates) < BARS:
        print(f"ERROR: Cannot fetch {BARS} bars for {SYMBOL}")
        return

    last_bar_time = int(rates[-1]["time"])
    open_position = None  # dict: ticket, direction, lots, sl, tp, entry_price, entry_time, holding_bars
    trades_log = []
    end_time = datetime.now(UTC) + timedelta(hours=args.hours)
    cycle = 0

    try:
        while datetime.now(UTC) < end_time:
            cycle += 1
            now = datetime.now(UTC)

            # Re-fetch data
            rates = mt5.copy_rates_from_pos(SYMBOL, tf_const, 0, BARS)
            if rates is None or len(rates) < BARS:
                time.sleep(10)
                continue

            closes = np.array([r["close"] for r in rates], dtype=float)
            highs = np.array([r["high"] for r in rates], dtype=float)
            lows = np.array([r["low"] for r in rates], dtype=float)
            current_bar_time = int(rates[-1]["time"])
            current_price = closes[-1]

            # ── Kill switch check ──
            kill_switch.update()
            if kill_switch.active:
                print(f"  [{now.strftime('%H:%M')}] Kill switch active — no new trades")
                time.sleep(60)
                continue

            # ── Manage open position ──
            if open_position:
                open_position["holding_bars"] += 1
                tick = mt5.symbol_info_tick(SYMBOL)
                cur = tick.bid if open_position["direction"] == 1 else tick.ask

                # Trailing stop — close at breakeven if price moved 1x ATR in our favor
                # (Avoids TRADE_ACTION_SLTP which may not work on Pepperstone BTCUSD)
                if not open_position.get("trail_active"):
                    atr_approx = abs(open_position["tp"] - open_position["entry_price"]) / TP_ATR_MULT
                    if open_position["direction"] == 1 and cur >= open_position["entry_price"] + atr_approx * TRAIL_BREAKEVEN_ATR:
                        exit_price = mt5_close_position(
                            mt5, open_position["ticket"], SYMBOL,
                            open_position["direction"], open_position["lots"]
                        )
                        if exit_price:
                            pnl = (exit_price - open_position["entry_price"]) * open_position["lots"]
                            trade = {
                                "entry_time": open_position["entry_time"],
                                "exit_time": now.isoformat(),
                                "direction": "LONG",
                                "entry_price": open_position["entry_price"],
                                "exit_price": exit_price,
                                "lots": open_position["lots"],
                                "pnl": round(pnl, 2),
                                "reason": "TRAIL_BE",
                                "holding_bars": open_position["holding_bars"],
                                "ticket": open_position["ticket"],
                            }
                            trades_log.append(trade)
                            log_trade(LOG_DIR, trade)
                            icon = "+" if pnl > 0 else ""
                            print(f"  [{now.strftime('%H:%M')}] TRAIL BE: P&L=${icon}{pnl:.2f}")
                        open_position = None
                        continue
                    elif open_position["direction"] == -1 and cur <= open_position["entry_price"] - atr_approx * TRAIL_BREAKEVEN_ATR:
                        exit_price = mt5_close_position(
                            mt5, open_position["ticket"], SYMBOL,
                            open_position["direction"], open_position["lots"]
                        )
                        if exit_price:
                            pnl = (open_position["entry_price"] - exit_price) * open_position["lots"]
                            trade = {
                                "entry_time": open_position["entry_time"],
                                "exit_time": now.isoformat(),
                                "direction": "SHORT",
                                "entry_price": open_position["entry_price"],
                                "exit_price": exit_price,
                                "lots": open_position["lots"],
                                "pnl": round(pnl, 2),
                                "reason": "TRAIL_BE",
                                "holding_bars": open_position["holding_bars"],
                                "ticket": open_position["ticket"],
                            }
                            trades_log.append(trade)
                            log_trade(LOG_DIR, trade)
                            icon = "+" if pnl > 0 else ""
                            print(f"  [{now.strftime('%H:%M')}] TRAIL BE: P&L=${icon}{pnl:.2f}")
                        open_position = None
                        continue

                # Check SL/TP/time exit
                hit_sl = (open_position["direction"] == 1 and cur <= open_position["sl"]) or \
                         (open_position["direction"] == -1 and cur >= open_position["sl"])
                hit_tp = (open_position["direction"] == 1 and cur >= open_position["tp"]) or \
                         (open_position["direction"] == -1 and cur <= open_position["tp"])
                time_exit = open_position["holding_bars"] >= MAX_HOLD_BARS

                if hit_sl or hit_tp or time_exit:
                    reason = "TP" if hit_tp else ("SL" if hit_sl else "TIME")
                    exit_price = mt5_close_position(
                        mt5, open_position["ticket"], SYMBOL,
                        open_position["direction"], open_position["lots"]
                    )
                    if exit_price:
                        if open_position["direction"] == 1:
                            pnl = (exit_price - open_position["entry_price"]) * open_position["lots"]
                        else:
                            pnl = (open_position["entry_price"] - exit_price) * open_position["lots"]
                        trade = {
                            "entry_time": open_position["entry_time"],
                            "exit_time": now.isoformat(),
                            "direction": "LONG" if open_position["direction"] == 1 else "SHORT",
                            "entry_price": open_position["entry_price"],
                            "exit_price": exit_price,
                            "lots": open_position["lots"],
                            "pnl": round(pnl, 2),
                            "reason": reason,
                            "holding_bars": open_position["holding_bars"],
                            "ticket": open_position["ticket"],
                        }
                        trades_log.append(trade)
                        log_trade(LOG_DIR, trade)
                        icon = "+" if pnl > 0 else ""
                        print(f"  [{now.strftime('%H:%M')}] {reason}: P&L=${icon}{pnl:.2f} "
                              f"(entry={open_position['entry_price']:.2f} exit={exit_price:.2f})")
                    open_position = None

            # ── Check signal on new bar ──
            if current_bar_time != last_bar_time:
                last_bar_time = current_bar_time
                direction, sl, tp, reason = donchian_signal(closes, highs, lows, STRATEGY_PARAMS)

                if direction != 0 and open_position is None:
                    # Calculate position size using CURRENT equity (not stale balance)
                    info = mt5.symbol_info(SYMBOL)
                    sl_distance = abs(current_price - sl)
                    current_equity = mt5.account_info().equity
                    lots = calc_position_size(mt5, SYMBOL, current_equity, RISK_PER_TRADE_PCT, sl_distance)

                    if lots <= 0:
                        print(f"  [{now.strftime('%H:%M')}] SIGNAL {reason} but lots=0 — skipped")
                        continue

                    if not args.dry_run:
                        result = mt5_open_order(mt5, SYMBOL, direction, lots, sl, tp, "DONCH_V1")
                        if result:
                            open_position = {
                                "ticket": result["ticket"],
                                "direction": direction,
                                "lots": lots,
                                "entry_price": result["price"],
                                "sl": sl, "tp": tp,
                                "entry_time": now.isoformat(),
                                "holding_bars": 0,
                                "trail_active": False,
                            }
                        else:
                            print(f"  [{now.strftime('%H:%M')}] ORDER FAILED for {reason}")
                    else:
                        side = "LONG" if direction == 1 else "SHORT"
                        print(f"  [{now.strftime('%H:%M')}] DRY: {side} @ {current_price:.2f} "
                              f"SL={sl:.2f} TP={tp:.2f} lots={lots:.4f}")
                        open_position = {
                            "ticket": 0, "direction": direction, "lots": lots,
                            "entry_price": current_price, "sl": sl, "tp": tp,
                            "entry_time": now.isoformat(), "holding_bars": 0,
                            "trail_active": False,
                        }

                elif direction != 0 and open_position is not None and direction != open_position["direction"]:
                    # Signal reversal — close current, don't open new (conservative)
                    tick = mt5.symbol_info_tick(SYMBOL)
                    cur = tick.bid if open_position["direction"] == 1 else tick.ask
                    if not args.dry_run:
                        exit_price = mt5_close_position(
                            mt5, open_position["ticket"], SYMBOL,
                            open_position["direction"], open_position["lots"]
                        )
                    else:
                        exit_price = cur

                    if exit_price:
                        if open_position["direction"] == 1:
                            pnl = (exit_price - open_position["entry_price"]) * open_position["lots"]
                        else:
                            pnl = (open_position["entry_price"] - exit_price) * open_position["lots"]
                        trade = {
                            "entry_time": open_position["entry_time"],
                            "exit_time": now.isoformat(),
                            "direction": "LONG" if open_position["direction"] == 1 else "SHORT",
                            "entry_price": open_position["entry_price"],
                            "exit_price": exit_price,
                            "lots": open_position["lots"],
                            "pnl": round(pnl, 2),
                            "reason": "REVERSE",
                            "holding_bars": open_position["holding_bars"],
                            "ticket": open_position["ticket"],
                        }
                        trades_log.append(trade)
                        log_trade(LOG_DIR, trade)
                        icon = "+" if pnl > 0 else ""
                        print(f"  [{now.strftime('%H:%M')}] REVERSE: P&L=${icon}{pnl:.2f}")
                    open_position = None

            # Status every 30 minutes
            if cycle % 30 == 0:
                total_pnl = sum(t["pnl"] for t in trades_log)
                wins = sum(1 for t in trades_log if t["pnl"] > 0)
                losses = sum(1 for t in trades_log if t["pnl"] <= 0)
                info = mt5.account_info()
                print(f"\n  [{now.strftime('%H:%M')}] STATUS | Balance: ${info.balance:,.2f} | "
                      f"Equity: ${info.equity:,.2f} | "
                      f"Trades: {len(trades_log)} ({wins}W/{losses}L) | "
                      f"P&L: ${total_pnl:+,.2f} | "
                      f"Open: {'YES' if open_position else 'NO'}")

            time.sleep(55)

    except KeyboardInterrupt:
        print("\n\nStopping...")
    finally:
        # Close any open position
        if open_position and open_position["ticket"] > 0:
            print("  Closing open position on exit...")
            if not args.dry_run:
                mt5_close_position(mt5, open_position["ticket"], SYMBOL,
                                   open_position["direction"], open_position["lots"])
        mt5.shutdown()

        # Final summary
        print("\n" + "=" * 70)
        print("SESSION SUMMARY")
        print("=" * 70)
        total_pnl = sum(t["pnl"] for t in trades_log)
        wins = sum(1 for t in trades_log if t["pnl"] > 0)
        losses = len(trades_log) - wins
        print(f"  Trades:     {len(trades_log)}")
        print(f"  Wins:       {wins}")
        print(f"  Losses:     {losses}")
        print(f"  Win rate:   {wins/len(trades_log)*100:.1f}%" if trades_log else "  Win rate:   N/A")
        print(f"  Total P&L:  ${total_pnl:+,.2f}")
        print(f"  Kill hits:  {1 if kill_switch.active else 0}")
        print("=" * 70)

        # Save report
        report = {
            "start": trades_log[0]["entry_time"] if trades_log else datetime.now(UTC).isoformat(),
            "end": datetime.now(UTC).isoformat(),
            "hours": args.hours,
            "mode": "DRY_RUN" if args.dry_run else "LIVE_DEMO",
            "trades": len(trades_log),
            "wins": wins, "losses": losses,
            "total_pnl": round(total_pnl, 2),
            "kill_switches": 1 if kill_switch.active else 0,
            "trades_data": trades_log,
        }
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        path = REPORTS_DIR / f"live_donchian_{ts}.json"
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"  Report: {path}")


def run_entry():
    parser = argparse.ArgumentParser(description="Donchian BTCUSD H1 Live Demo")
    parser.add_argument("--hours", type=float, default=720, help="Duration (default: 720h = 30 days)")
    parser.add_argument("--dry-run", action="store_true", help="Log signals without placing orders")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    run_entry()
