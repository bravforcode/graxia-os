"""
Donchian BTCUSD H1 — Live Paper Trading

Runs the sacred-holdout-validated Donchian strategy on live MT5 data
in paper mode. Tracks performance vs backtest baseline.

Usage:
    python scripts/donchian_paper_trade.py                    # default 60min
    python scripts/donchian_paper_trade.py --hours 24         # 24 hours
    python scripts/donchian_paper_trade.py --hours 720        # 30 days
    python scripts/donchian_paper_trade.py --capital 25000    # custom capital
    python scripts/donchian_paper_trade.py --risk 1.0         # risk per trade %
    python scripts/donchian_paper_trade.py --dry-run          # no MT5, log only

Environment:
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID — for notifications
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parent.parent
os.chdir(_project_root)
sys.path.insert(0, str(_project_root))

import numpy as np
import pandas as pd

# ── Constants ────────────────────────────────────────────────────
SYMBOL = "BTCUSD"
TIMEFRAME = "H1"
STRATEGY_PARAMS = {"period": 20, "vol_filter": True}
SPREAD_BPS = 2.43  # measured from cost_calibration.json
BARS_NEEDED = 100  # bars to fetch from MT5 (enough for Donchian(20) + ATR(14))

# Backtest baseline (from sacred holdout)
BASELINE = {
    "sharpe": 2.5706,
    "total_return_pct": 57.1,
    "max_dd_pct": 9.1,
    "win_rate": 50.8,
    "expectancy": 226.54,
    "trades_per_year": 261.8,
    "avg_trade_duration_hrs": 33.5,
    "holdout_trades": 252,
}

LOG_DIR = _project_root / "logs" / "donchian_paper"
REPORTS_DIR = _project_root / "reports" / "paper_engine"


# ── Donchian Strategy (same as paper_engine) ────────────────────
def compute_atr(highs, lows, closes, period=14):
    """Compute ATR from numpy arrays."""
    n = len(closes)
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
    atr = np.full(n, np.nan)
    if n >= period:
        atr[period] = np.mean(tr[1:period + 1])
        for i in range(period + 1, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def donchian_signal(closes, highs, lows, idx, params):
    """Generate Donchian signal for bar at idx. Returns (direction, sl, tp, reason)."""
    period = params.get("period", 20)
    vol_filter = params.get("vol_filter", True)

    if idx < period + 1:
        return 0, 0, 0, ""

    hh = np.max(highs[idx - period: idx - 1])
    ll = np.min(lows[idx - period: idx - 1])

    atr = compute_atr(highs, lows, closes, 14)
    if atr[idx] <= 0 or closes[idx] <= 0:
        return 0, 0, 0, ""

    atr_ratio_all = np.where(closes > 0, atr / closes, 0)
    med_ratio = np.nanmedian(atr_ratio_all[max(0, idx-200):idx]) if idx > 0 else np.nanmedian(atr_ratio_all)

    vol_ok = True
    if vol_filter:
        current_vol_ratio = atr[idx] / closes[idx]
        vol_ok = current_vol_ratio > med_ratio * 0.8 if med_ratio > 0 else True

    if closes[idx] > hh and vol_ok:
        direction = 1
        sl = closes[idx] - atr[idx] * 2.0
        tp = closes[idx] + atr[idx] * 3.0
        reason = f"BREAKOUT LONG high={hh:.2f}"
        return direction, sl, tp, reason
    elif closes[idx] < ll and vol_ok:
        direction = -1
        sl = closes[idx] + atr[idx] * 2.0
        tp = closes[idx] - atr[idx] * 3.0
        reason = f"BREAKOUT SHORT low={ll:.2f}"
        return direction, sl, tp, reason

    return 0, 0, 0, ""


# ── Trade Tracker ────────────────────────────────────────────────
@dataclass
class LiveTrade:
    direction: int  # 1=long, -1=short
    entry_price: float
    entry_time: str
    stop_loss: float
    take_profit: float
    position_size: float  # BTC quantity
    risk_dollar: float
    reason: str
    exit_price: float = 0
    exit_time: str = ""
    exit_reason: str = ""
    pnl: float = 0
    pnl_pct: float = 0
    status: str = "open"  # open, closed


@dataclass
class SessionStats:
    start_time: str = ""
    trades: list = field(default_factory=list)
    total_pnl: float = 0
    wins: int = 0
    losses: int = 0
    max_dd: float = 0
    peak_equity: float = 0
    current_equity: float = 0

    def add_trade(self, trade: LiveTrade):
        self.trades.append(trade)
        self.total_pnl += trade.pnl
        if trade.pnl > 0:
            self.wins += 1
        else:
            self.losses += 1
        self.current_equity = self.peak_equity + self.total_pnl
        if self.current_equity > self.peak_equity:
            self.peak_equity = self.current_equity
        dd = self.peak_equity - self.current_equity
        if dd > self.max_dd:
            self.max_dd = dd

    @property
    def win_rate(self):
        total = self.wins + self.losses
        return self.wins / total * 100 if total > 0 else 0

    @property
    def avg_win(self):
        wins = [t.pnl for t in self.trades if t.pnl > 0]
        return np.mean(wins) if wins else 0

    @property
    def avg_loss(self):
        losses = [t.pnl for t in self.trades if t.pnl <= 0]
        return np.mean(losses) if losses else 0

    @property
    def expectancy(self):
        total = self.wins + self.losses
        if total == 0:
            return 0
        wr = self.wins / total
        return wr * self.avg_win + (1 - wr) * self.avg_loss

    @property
    def profit_factor(self):
        gross_profit = sum(t.pnl for t in self.trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self.trades if t.pnl <= 0))
        return gross_profit / gross_loss if gross_loss > 0 else float("inf")


# ── Telegram ─────────────────────────────────────────────────────
async def send_telegram(token, chat_id, msg):
    if not token or not chat_id:
        return
    try:
        import aiohttp
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with aiohttp.ClientSession() as session:
            await session.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
    except Exception:
        pass


# ── Main Loop ────────────────────────────────────────────────────
async def run_paper_trading(args):
    capital = args.capital
    risk_pct = args.risk / 100
    hours = args.hours
    dry_run = args.dry_run

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    stats = SessionStats(start_time=datetime.now(UTC).isoformat(), peak_equity=capital, current_equity=capital)

    open_trade: LiveTrade | None = None
    last_bar_time = None

    print("=" * 70)
    print("DONCHIAN BTCUSD H1 — LIVE PAPER TRADING")
    print("=" * 70)
    print(f"  Strategy:     Donchian(20) + vol filter")
    print(f"  Symbol:       {SYMBOL}")
    print(f"  Timeframe:    {TIMEFRAME}")
    print(f"  Spread:       {SPREAD_BPS} bps")
    print(f"  Capital:      ${capital:,.2f}")
    print(f"  Risk/Trade:   {args.risk}%")
    print(f"  Duration:     {hours} hours")
    print(f"  Mode:         {'DRY RUN' if dry_run else 'PAPER (MT5)'}")
    print()
    print("  Baseline (holdout):")
    print(f"    Sharpe:     {BASELINE['sharpe']}")
    print(f"    Return:     {BASELINE['total_return_pct']}%")
    print(f"    Max DD:     {BASELINE['max_dd_pct']}%")
    print(f"    Win rate:   {BASELINE['win_rate']}%")
    print(f"    Trades/yr:  {BASELINE['trades_per_year']}")
    print()
    print("=" * 70)

    # Connect to MT5 or load historical data for dry-run
    mt5 = None
    if not dry_run:
        try:
            import MetaTrader5 as _mt5
            mt5 = _mt5
            if not mt5.initialize():
                mt5.initialize(path=r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe")

            account = mt5.account_info()
            if account:
                print(f"  MT5 Connected: {account.server} | Login: {account.login}")
                print(f"  Balance: ${account.balance:,.2f} | Leverage: 1:{account.leverage}")
            else:
                print("  ERROR: MT5 connected but no account info")
                return
        except ImportError:
            print("  ERROR: MetaTrader5 package not installed")
            return
        except Exception as e:
            print(f"  ERROR: MT5 connection failed: {e}")
            return
    else:
        # Dry-run: use MT5 for price data only, log trades instead of placing
        try:
            import MetaTrader5 as _mt5
            mt5 = _mt5
            if not mt5.initialize():
                mt5.initialize(path=r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe")
            account = mt5.account_info()
            if account:
                print(f"  DRY RUN — MT5 prices from {account.server} | NO orders placed")
                print(f"  Balance: ${account.balance:,.2f}")
            else:
                print("  ERROR: MT5 needed even in dry-run for price data")
                return
        except Exception as e:
            print(f"  ERROR: MT5 connection failed: {e}")
            return

    print()
    await send_telegram(token, chat_id, "🚀 *Donchian BTCUSD H1 Paper Trading Started*\n"
                        f"Capital: ${capital:,.0f} | Risk: {args.risk}% | Duration: {hours}h")

    end_time = datetime.now(UTC) + timedelta(hours=hours)
    cycle = 0

    try:
        while datetime.now(UTC) < end_time:
            cycle += 1
            now = datetime.now(UTC)

            # ── Fetch latest H1 bar from MT5 ──
            if mt5:
                rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_H1, 0, BARS_NEEDED)
                if rates is None or len(rates) < BARS_NEEDED:
                    print(f"  [{now.strftime('%H:%M:%S')}] Waiting for MT5 data...")
                    await asyncio.sleep(30)
                    continue

                new_bar_time = int(rates[-1]["time"])
                if last_bar_time == new_bar_time:
                    # No new bar — check open trade SL/TP
                    if open_trade and open_trade.status == "open":
                        tick = mt5.symbol_info_tick(SYMBOL)
                        if tick:
                            current = tick.bid if open_trade.direction == 1 else tick.ask
                            # Check SL
                            if open_trade.direction == 1 and current <= open_trade.stop_loss:
                                open_trade.exit_price = open_trade.stop_loss
                                open_trade.exit_time = now.isoformat()
                                open_trade.exit_reason = "stop_loss"
                                open_trade.pnl = (open_trade.exit_price - open_trade.entry_price) * open_trade.position_size * (-1 if open_trade.direction == 1 else 1)
                                open_trade.pnl -= open_trade.entry_price * open_trade.position_size * SPREAD_BPS / 10000 * 2
                                open_trade.pnl_pct = open_trade.pnl / capital * 100
                                open_trade.status = "closed"
                                stats.add_trade(open_trade)
                                _log_trade(open_trade)
                                print(f"  [{now.strftime('%H:%M:%S')}] SL HIT: ${open_trade.pnl:+,.2f} ({open_trade.pnl_pct:+.2f}%)")
                                await send_telegram(token, chat_id, f"🔴 SL Hit: ${open_trade.pnl:+,.2f}")
                                open_trade = None
                            elif open_trade.direction == -1 and current >= open_trade.stop_loss:
                                open_trade.exit_price = open_trade.stop_loss
                                open_trade.exit_time = now.isoformat()
                                open_trade.exit_reason = "stop_loss"
                                open_trade.pnl = (open_trade.entry_price - open_trade.exit_price) * open_trade.position_size
                                open_trade.pnl -= open_trade.entry_price * open_trade.position_size * SPREAD_BPS / 10000 * 2
                                open_trade.pnl_pct = open_trade.pnl / capital * 100
                                open_trade.status = "closed"
                                stats.add_trade(open_trade)
                                _log_trade(open_trade)
                                print(f"  [{now.strftime('%H:%M:%S')}] SL HIT: ${open_trade.pnl:+,.2f} ({open_trade.pnl_pct:+.2f}%)")
                                await send_telegram(token, chat_id, f"🔴 SL Hit: ${open_trade.pnl:+,.2f}")
                                open_trade = None
                            # Check TP
                            elif open_trade.direction == 1 and current >= open_trade.take_profit:
                                open_trade.exit_price = open_trade.take_profit
                                open_trade.exit_time = now.isoformat()
                                open_trade.exit_reason = "take_profit"
                                open_trade.pnl = (open_trade.exit_price - open_trade.entry_price) * open_trade.position_size
                                open_trade.pnl -= open_trade.entry_price * open_trade.position_size * SPREAD_BPS / 10000 * 2
                                open_trade.pnl_pct = open_trade.pnl / capital * 100
                                open_trade.status = "closed"
                                stats.add_trade(open_trade)
                                _log_trade(open_trade)
                                print(f"  [{now.strftime('%H:%M:%S')}] TP HIT: ${open_trade.pnl:+,.2f} ({open_trade.pnl_pct:+.2f}%)")
                                await send_telegram(token, chat_id, f"🟢 TP Hit: ${open_trade.pnl:+,.2f}")
                                open_trade = None
                            elif open_trade.direction == -1 and current <= open_trade.take_profit:
                                open_trade.exit_price = open_trade.take_profit
                                open_trade.exit_time = now.isoformat()
                                open_trade.exit_reason = "take_profit"
                                open_trade.pnl = (open_trade.entry_price - open_trade.exit_price) * open_trade.position_size
                                open_trade.pnl -= open_trade.entry_price * open_trade.position_size * SPREAD_BPS / 10000 * 2
                                open_trade.pnl_pct = open_trade.pnl / capital * 100
                                open_trade.status = "closed"
                                stats.add_trade(open_trade)
                                _log_trade(open_trade)
                                print(f"  [{now.strftime('%H:%M:%S')}] TP HIT: ${open_trade.pnl:+,.2f} ({open_trade.pnl_pct:+.2f}%)")
                                await send_telegram(token, chat_id, f"🟢 TP Hit: ${open_trade.pnl:+,.2f}")
                                open_trade = None

                    await asyncio.sleep(10)
                    continue

                last_bar_time = new_bar_time

                # Build OHLCV arrays
                closes = np.array([r["close"] for r in rates], dtype=float)
                highs = np.array([r["high"] for r in rates], dtype=float)
                lows = np.array([r["low"] for r in rates], dtype=float)
                idx = len(closes) - 1
                current_price = closes[idx]

                # Generate signal
                direction, sl, tp, reason = donchian_signal(closes, highs, lows, idx, STRATEGY_PARAMS)

                if direction != 0 and open_trade is None:
                    # Calculate position size
                    risk_dollar = capital * risk_pct
                    sl_distance = abs(current_price - sl)
                    position_size = risk_dollar / sl_distance if sl_distance > 0 else 0

                    # Open trade
                    open_trade = LiveTrade(
                        direction=direction,
                        entry_price=current_price,
                        entry_time=now.isoformat(),
                        stop_loss=sl,
                        take_profit=tp,
                        position_size=position_size,
                        risk_dollar=risk_dollar,
                        reason=reason,
                    )

                    side_str = "LONG" if direction == 1 else "SHORT"
                    print(f"  [{now.strftime('%H:%M:%S')}] {side_str} @ ${current_price:,.2f} | SL: ${sl:,.2f} | TP: ${tp:,.2f} | Size: {position_size:.4f} BTC")
                    await send_telegram(token, chat_id, f"📈 *{side_str}* @ ${current_price:,.2f}\nSL: ${sl:,.2f} | TP: ${tp:,.2f}\nSize: {position_size:.4f} BTC")

                elif direction != 0 and open_trade is not None:
                    # Signal against open position — close first
                    if direction != open_trade.direction:
                        tick = mt5.symbol_info_tick(SYMBOL) if mt5 else None
                        current = tick.bid if tick else current_price
                        open_trade.exit_price = current
                        open_trade.exit_time = now.isoformat()
                        open_trade.exit_reason = "signal_reverse"
                        if open_trade.direction == 1:
                            open_trade.pnl = (current - open_trade.entry_price) * open_trade.position_size
                        else:
                            open_trade.pnl = (open_trade.entry_price - current) * open_trade.position_size
                        open_trade.pnl -= open_trade.entry_price * open_trade.position_size * SPREAD_BPS / 10000 * 2
                        open_trade.pnl_pct = open_trade.pnl / capital * 100
                        open_trade.status = "closed"
                        stats.add_trade(open_trade)
                        _log_trade(open_trade)
                        print(f"  [{now.strftime('%H:%M:%S')}] REVERSE: closed at ${current:,.2f} | P&L: ${open_trade.pnl:+,.2f}")
                        open_trade = None

            # ── Print status every 24 cycles (4 min) ──
            if cycle % 24 == 0:
                total_trades = stats.wins + stats.losses
                print(f"\n  [{now.strftime('%H:%M:%S')}] STATUS | Trades: {total_trades} | "
                      f"Win: {stats.win_rate:.1f}% | P&L: ${stats.total_pnl:+,.2f} | "
                      f"DD: ${stats.max_dd:,.2f} | PF: {stats.profit_factor:.2f}")
                if open_trade and open_trade.status == "open":
                    side = "LONG" if open_trade.direction == 1 else "SHORT"
                    print(f"    Open: {side} @ ${open_trade.entry_price:,.2f} | SL: ${open_trade.stop_loss:,.2f} | TP: ${open_trade.take_profit:,.2f}")

            await asyncio.sleep(60)  # Check every minute

    except KeyboardInterrupt:
        print("\n\nStopping paper trading...")
    finally:
        # Close any open trade
        if open_trade and open_trade.status == "open":
            open_trade.exit_price = closes[-1] if 'closes' in dir() else open_trade.entry_price
            open_trade.exit_time = datetime.now(UTC).isoformat()
            open_trade.exit_reason = "session_end"
            if open_trade.direction == 1:
                open_trade.pnl = (open_trade.exit_price - open_trade.entry_price) * open_trade.position_size
            else:
                open_trade.pnl = (open_trade.entry_price - open_trade.exit_price) * open_trade.position_size
            open_trade.pnl -= open_trade.entry_price * open_trade.position_size * SPREAD_BPS / 10000 * 2
            open_trade.pnl_pct = open_trade.pnl / capital * 100
            open_trade.status = "closed"
            stats.add_trade(open_trade)
            _log_trade(open_trade)

        if mt5:
            mt5.shutdown()

        # Print final summary
        _print_final_summary(stats, capital)

        # Save session report
        _save_session_report(stats, capital, hours)

        # Telegram summary
        total = stats.wins + stats.losses
        msg = (f"📊 *Paper Trading Complete*\n"
               f"Duration: {hours}h | Trades: {total}\n"
               f"P&L: ${stats.total_pnl:+,.2f} ({stats.total_pnl/capital*100:+.1f}%)\n"
               f"Win rate: {stats.win_rate:.1f}% | PF: {stats.profit_factor:.2f}\n"
               f"Max DD: ${stats.max_dd:,.2f}")
        await send_telegram(token, chat_id, msg)


def _log_trade(trade: LiveTrade):
    """Append trade to JSONL log."""
    log_path = LOG_DIR / "trades.jsonl"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "direction": "LONG" if trade.direction == 1 else "SHORT",
            "entry_price": trade.entry_price,
            "entry_time": trade.entry_time,
            "exit_price": trade.exit_price,
            "exit_time": trade.exit_time,
            "exit_reason": trade.exit_reason,
            "stop_loss": trade.stop_loss,
            "take_profit": trade.take_profit,
            "position_size": trade.position_size,
            "pnl": round(trade.pnl, 2),
            "pnl_pct": round(trade.pnl_pct, 2),
            "reason": trade.reason,
        }) + "\n")


def _print_final_summary(stats: SessionStats, capital: float):
    total = stats.wins + stats.losses
    print()
    print("=" * 70)
    print("SESSION SUMMARY")
    print("=" * 70)
    print(f"  Total trades:    {total}")
    print(f"  Wins:            {stats.wins}")
    print(f"  Losses:          {stats.losses}")
    print(f"  Win rate:        {stats.win_rate:.1f}%")
    print(f"  Avg win:         ${stats.avg_win:+,.2f}")
    print(f"  Avg loss:        ${stats.avg_loss:+,.2f}")
    print(f"  Expectancy:      ${stats.expectancy:+,.2f}/trade")
    print(f"  Profit factor:   {stats.profit_factor:.2f}")
    print(f"  Total P&L:       ${stats.total_pnl:+,.2f} ({stats.total_pnl/capital*100:+.1f}%)")
    print(f"  Max drawdown:    ${stats.max_dd:,.2f} ({stats.max_dd/capital*100:.1f}%)")
    print()

    # Compare to baseline
    print("  vs Holdout Baseline:")
    if total > 0:
        live_wr = stats.win_rate
        print(f"    Win rate:      {live_wr:.1f}% vs {BASELINE['win_rate']}% baseline")
        print(f"    Expectancy:    ${stats.expectancy:+,.2f} vs ${BASELINE['expectancy']:+,.2f} baseline")
        print(f"    PF:            {stats.profit_factor:.2f} vs 1.42 baseline")
    print()
    print("=" * 70)


def _save_session_report(stats: SessionStats, capital: float, hours: float):
    total = stats.wins + stats.losses
    report = {
        "start_time": stats.start_time,
        "end_time": datetime.now(UTC).isoformat(),
        "duration_hours": hours,
        "capital": capital,
        "trades": total,
        "wins": stats.wins,
        "losses": stats.losses,
        "win_rate": round(stats.win_rate, 1),
        "avg_win": round(stats.avg_win, 2),
        "avg_loss": round(stats.avg_loss, 2),
        "expectancy": round(stats.expectancy, 2),
        "profit_factor": round(stats.profit_factor, 2),
        "total_pnl": round(stats.total_pnl, 2),
        "total_return_pct": round(stats.total_pnl / capital * 100, 1),
        "max_drawdown": round(stats.max_dd, 2),
        "max_dd_pct": round(stats.max_dd / capital * 100, 1),
        "trades_data": [
            {
                "direction": "LONG" if t.direction == 1 else "SHORT",
                "entry": t.entry_price, "exit": t.exit_price,
                "pnl": round(t.pnl, 2), "reason": t.exit_reason,
            }
            for t in stats.trades
        ],
        "baseline": BASELINE,
    }
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = REPORTS_DIR / f"paper_session_{ts}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"  Session report saved: {path}")


# ── CLI ──────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Donchian BTCUSD H1 Paper Trading")
    parser.add_argument("--hours", type=float, default=60, help="Duration in hours (default: 60)")
    parser.add_argument("--capital", type=float, default=100000, help="Starting capital (default: 100000)")
    parser.add_argument("--risk", type=float, default=1.0, help="Risk per trade %% (default: 1.0)")
    parser.add_argument("--dry-run", action="store_true", help="No MT5 connection")
    args = parser.parse_args()

    asyncio.run(run_paper_trading(args))


if __name__ == "__main__":
    main()
