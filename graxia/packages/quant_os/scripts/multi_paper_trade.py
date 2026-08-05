"""
Multi-Campaign Paper Trader — Donchian + TSM + Volume Breakout
Runs ALL WFA survivors on live MT5 data simultaneously.

Usage:
    python scripts/multi_paper_trade.py --hours 720
    python scripts/multi_paper_trade.py --hours 720 --capital 49842
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
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parent.parent
os.chdir(_project_root)
sys.path.insert(0, str(_project_root))

import numpy as np
import pandas as pd

# ── Campaign definitions from WFA top 40 (unique strategy+symbol+TF) ──
CAMPAIGNS = [
    # Donchian — top 16 unique combos
    {"id": "don_btc_h1",  "strategy": "donchian", "symbol": "BTCUSD",  "tf": "H1",  "params": {"period": 20, "vol_filter": True}, "oos_sharpe": 1.834, "capital_pct": 10},
    {"id": "don_nas_h1",  "strategy": "donchian", "symbol": "NAS100",  "tf": "H1",  "params": {"period": 20, "vol_filter": True}, "oos_sharpe": 1.728, "capital_pct": 8},
    {"id": "don_xau_h1",  "strategy": "donchian", "symbol": "XAUUSD",  "tf": "H1",  "params": {"period": 20, "vol_filter": True}, "oos_sharpe": 1.465, "capital_pct": 8},
    {"id": "don_aud_h1",  "strategy": "donchian", "symbol": "AUDUSD",  "tf": "H1",  "params": {"period": 20, "vol_filter": True}, "oos_sharpe": 1.256, "capital_pct": 6},
    {"id": "don_xag_h1",  "strategy": "donchian", "symbol": "XAGUSD",  "tf": "H1",  "params": {"period": 20, "vol_filter": True}, "oos_sharpe": 1.204, "capital_pct": 6},
    {"id": "don_eth_h4",  "strategy": "donchian", "symbol": "ETHUSD",  "tf": "H4",  "params": {"period": 20, "vol_filter": True}, "oos_sharpe": 1.156, "capital_pct": 5},
    {"id": "don_eur_h1",  "strategy": "donchian", "symbol": "EURUSD",  "tf": "H1",  "params": {"period": 20, "vol_filter": True}, "oos_sharpe": 1.049, "capital_pct": 5},
    {"id": "don_nas_h4",  "strategy": "donchian", "symbol": "NAS100",  "tf": "H4",  "params": {"period": 20, "vol_filter": True}, "oos_sharpe": 1.025, "capital_pct": 4},
    {"id": "don_us30_h4", "strategy": "donchian", "symbol": "US30",    "tf": "H4",  "params": {"period": 20, "vol_filter": True}, "oos_sharpe": 0.980, "capital_pct": 4},
    {"id": "don_gbp_h1",  "strategy": "donchian", "symbol": "GBPUSD",  "tf": "H1",  "params": {"period": 20, "vol_filter": True}, "oos_sharpe": 0.970, "capital_pct": 5},
    {"id": "don_us30_h1", "strategy": "donchian", "symbol": "US30",    "tf": "H1",  "params": {"period": 20, "vol_filter": True}, "oos_sharpe": 0.878, "capital_pct": 4},
    {"id": "don_eth_h1",  "strategy": "donchian", "symbol": "ETHUSD",  "tf": "H1",  "params": {"period": 20, "vol_filter": True}, "oos_sharpe": 0.784, "capital_pct": 4},
    {"id": "don_jpy_h1",  "strategy": "donchian", "symbol": "USDJPY",  "tf": "H1",  "params": {"period": 20, "vol_filter": True}, "oos_sharpe": 0.772, "capital_pct": 4},
    # TSM — top 4 unique combos
    {"id": "tsm_xau_h1",  "strategy": "tsm",      "symbol": "XAUUSD",  "tf": "H1",  "params": {"lookbacks": [20, 40, 60, 120], "vol_target": 0.10}, "oos_sharpe": 1.315, "capital_pct": 7},
    {"id": "tsm_xag_h1",  "strategy": "tsm",      "symbol": "XAGUSD",  "tf": "H1",  "params": {"lookbacks": [20, 40, 60, 120], "vol_target": 0.10}, "oos_sharpe": 1.238, "capital_pct": 6},
    {"id": "tsm_btc_h1",  "strategy": "tsm",      "symbol": "BTCUSD",  "tf": "H1",  "params": {"lookbacks": [20, 40, 60, 120], "vol_target": 0.10}, "oos_sharpe": 0.796, "capital_pct": 5},
    # Volume Breakout — top 1
    {"id": "vb_us30_h1",  "strategy": "volume_breakout", "symbol": "US30", "tf": "H1", "params": {"vol_period": 20, "vol_mult": 2.0, "lookback": 20}, "oos_sharpe": 0.632, "capital_pct": 3},
]

SPREAD_BPS = {
    "BTCUSD": 2.43, "ETHUSD": 11.67, "XAUUSD": 0.36, "XAGUSD": 6.58,
    "NAS100": 1.0, "US30": 0.5, "EURUSD": 0.07, "GBPUSD": 0.15,
    "AUDUSD": 0.1, "USDJPY": 0.06,
}
TF_MAP = {"H1": "TIMEFRAME_H1", "H4": "TIMEFRAME_H4"}
BARS = 200

LOG_DIR = _project_root / "logs" / "multi_paper"
REPORTS_DIR = _project_root / "reports" / "paper_engine"


# ── Strategy logic (inline, no imports needed) ───────────────────
def compute_atr(highs, lows, closes, period=14):
    n = len(closes)
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    atr = np.full(n, np.nan)
    if n >= period:
        atr[period] = np.mean(tr[1: period + 1])
        for i in range(period + 1, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def signal_donchian(closes, highs, lows, params):
    period = params.get("period", 20)
    vol_filter = params.get("vol_filter", True)
    n = len(closes)
    if n < period + 2:
        return 0, 0, 0, ""
    i = n - 1
    hh = np.max(highs[i - period: i])
    ll = np.min(lows[i - period: i])
    atr = compute_atr(highs, lows, closes, 14)
    if np.isnan(atr[i]) or atr[i] <= 0 or closes[i] <= 0:
        return 0, 0, 0, ""
    atr_ratio_all = np.where(closes > 0, atr / closes, 0)
    med_ratio = np.nanmedian(atr_ratio_all[max(0, i - 200):i]) if i > 0 else 0
    vol_ok = (atr[i] / closes[i] > med_ratio * 0.8) if vol_filter and med_ratio > 0 else True

    if closes[i] > hh and vol_ok:
        return 1, closes[i] - atr[i] * 2, closes[i] + atr[i] * 3, f"LONG high={hh:.2f}"
    elif closes[i] < ll and vol_ok:
        return -1, closes[i] + atr[i] * 2, closes[i] - atr[i] * 3, f"SHORT low={ll:.2f}"
    return 0, 0, 0, ""


def signal_tsm(closes, highs, lows, params):
    lookbacks = params.get("lookbacks", [20, 40, 60, 120])
    vol_target = params.get("vol_target", 0.10)
    n = len(closes)
    if n < max(lookbacks) + 2:
        return 0, 0, 0, ""
    i = n - 1
    atr = compute_atr(highs, lows, closes, 14)
    if np.isnan(atr[i]) or atr[i] <= 0:
        return 0, 0, 0, ""
    z_scores = []
    for lb in lookbacks:
        ret = (closes[i] - closes[i - lb]) / closes[i - lb] if closes[i - lb] > 0 else 0
        z_scores.append(ret)
    avg_z = np.mean(z_scores)
    if avg_z > 0.5:
        return 1, closes[i] - atr[i] * 2, closes[i] + atr[i] * 3, f"TSM z={avg_z:.3f}"
    elif avg_z < -0.5:
        return -1, closes[i] + atr[i] * 2, closes[i] - atr[i] * 3, f"TSM z={avg_z:.3f}"
    return 0, 0, 0, ""


def signal_volume_breakout(closes, highs, lows, params):
    vol_period = params.get("vol_period", 20)
    vol_mult = params.get("vol_mult", 2.0)
    lookback = params.get("lookback", 20)
    n = len(closes)
    if n < max(vol_period, lookback) + 2:
        return 0, 0, 0, ""
    i = n - 1
    atr = compute_atr(highs, lows, closes, 14)
    if np.isnan(atr[i]) or atr[i] <= 0:
        return 0, 0, 0, ""
    hh = np.max(highs[i - lookback: i])
    ll = np.min(lows[i - lookback: i])
    if closes[i] > hh:
        return 1, closes[i] - atr[i] * 2, closes[i] + atr[i] * 3, f"VB LONG high={hh:.2f}"
    elif closes[i] < ll:
        return -1, closes[i] + atr[i] * 2, closes[i] - atr[i] * 3, f"VB SHORT low={ll:.2f}"
    return 0, 0, 0, ""


SIGNAL_FNS = {
    "donchian": signal_donchian,
    "tsm": signal_tsm,
    "volume_breakout": signal_volume_breakout,
}


# ── Campaign state ───────────────────────────────────────────────
@dataclass
class CampaignState:
    cfg: dict
    open_trade: Any = None
    trades: list = field(default_factory=list)
    total_pnl: float = 0
    wins: int = 0
    losses: int = 0
    last_bar_time: int = 0
    signals_generated: int = 0
    capital: float = 0

    @property
    def win_rate(self):
        t = self.wins + self.losses
        return self.wins / t * 100 if t > 0 else 0

    @property
    def profit_factor(self):
        gp = sum(t["pnl"] for t in self.trades if t["pnl"] > 0)
        gl = abs(sum(t["pnl"] for t in self.trades if t["pnl"] <= 0))
        return gp / gl if gl > 0 else float("inf")


# ── Main ─────────────────────────────────────────────────────────
async def main(args):
    import MetaTrader5 as mt5
    if not mt5.initialize():
        mt5.initialize(path=r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe")

    account = mt5.account_info()
    total_capital = args.capital or account.balance
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    tf_const = {tf: getattr(mt5, attr) for tf, attr in TF_MAP.items()}

    # Build TF -> [campaign_ids] mapping
    tf_groups: dict[str, list[str]] = {}
    for c in CAMPAIGNS:
        tf_groups.setdefault(c["tf"], []).append(c["id"])

    # Init states
    states: dict[str, CampaignState] = {}
    for c in CAMPAIGNS:
        alloc = total_capital * c["capital_pct"] / 100
        states[c["id"]] = CampaignState(cfg=c, capital=alloc)

    # Pre-fetch all symbols for each TF
    def fetch_tf(tf):
        tf_tf = tf_const[tf]
        data: dict[str, dict] = {}
        for c in CAMPAIGNS:
            if c["tf"] != tf:
                continue
            sym = c["symbol"]
            if sym in data:
                continue
            rates = mt5.copy_rates_from_pos(sym, tf_tf, 0, BARS)
            if rates is not None and len(rates) >= BARS:
                data[sym] = {
                    "closes": np.array([r["close"] for r in rates], dtype=float),
                    "highs": np.array([r["high"] for r in rates], dtype=float),
                    "lows": np.array([r["low"] for r in rates], dtype=float),
                    "bar_time": int(rates[-1]["time"]),
                    "current_price": float(rates[-1]["close"]),
                }
        return data

    print("=" * 80)
    print("MULTI-CAMPAIGN PAPER TRADER")
    print("=" * 80)
    print(f"  Capital:     ${total_capital:,.2f}")
    print(f"  Campaigns:   {len(CAMPAIGNS)}")
    print(f"  Duration:    {args.hours}h")
    print(f"  Strategies:  donchian, tsm, volume_breakout")
    print(f"  Symbols:     {len(set(c['symbol'] for c in CAMPAIGNS))}")
    print(f"  Account:     {account.server} #{account.login}")
    print()

    # Print campaign table
    print(f"  {'ID':<16} {'Strategy':<18} {'Symbol':<10} {'TF':<5} {'OOS':>6} {'Alloc':>10}")
    print("  " + "-" * 70)
    for c in CAMPAIGNS:
        alloc = total_capital * c["capital_pct"] / 100
        print(f"  {c['id']:<16} {c['strategy']:<18} {c['symbol']:<10} {c['tf']:<5} {c['oos_sharpe']:>6.3f} ${alloc:>9,.0f}")
    print()

    end_time = datetime.now(UTC) + timedelta(hours=args.hours)
    cycle = 0

    try:
        while datetime.now(UTC) < end_time:
            cycle += 1
            now = datetime.now(UTC)

            # Fetch data for each TF
            tf_data: dict[str, dict] = {}
            for tf in tf_groups:
                tf_data[tf] = fetch_tf(tf)

            # Process each campaign
            for c in CAMPAIGNS:
                cid = c["id"]
                st = states[cid]
                sym = c["symbol"]
                tf = c["tf"]

                if sym not in tf_data.get(tf, {}):
                    continue

                d = tf_data[tf][sym]
                bar_time = d["bar_time"]

                # Check SL/TP on current tick if open
                if st.open_trade and st.open_trade["status"] == "open":
                    tick = mt5.symbol_info_tick(sym)
                    if tick:
                        current = tick.bid if st.open_trade["direction"] == 1 else tick.ask
                        ot = st.open_trade
                        # SL
                        hit_sl = (ot["direction"] == 1 and current <= ot["sl"]) or \
                                 (ot["direction"] == -1 and current >= ot["sl"])
                        # TP
                        hit_tp = (ot["direction"] == 1 and current >= ot["tp"]) or \
                                 (ot["direction"] == -1 and current <= ot["tp"])

                        if hit_sl or hit_tp:
                            reason = "stop_loss" if hit_sl else "take_profit"
                            exit_price = ot["sl"] if hit_sl else ot["tp"]
                            spread_cost = exit_price * ot["size"] * SPREAD_BPS.get(sym, 1) / 10000
                            if ot["direction"] == 1:
                                pnl = (exit_price - ot["entry"]) * ot["size"] - spread_cost
                            else:
                                pnl = (ot["entry"] - exit_price) * ot["size"] - spread_cost
                            st.trades.append({
                                "direction": "LONG" if ot["direction"] == 1 else "SHORT",
                                "entry": ot["entry"], "exit": exit_price,
                                "pnl": round(pnl, 2), "reason": reason,
                                "entry_time": ot["entry_time"],
                                "exit_time": now.isoformat(),
                            })
                            st.total_pnl += pnl
                            if pnl > 0: st.wins += 1
                            else: st.losses += 1
                            st.open_trade = None
                            _log_trade(LOG_DIR, cid, st.trades[-1])
                            icon = "+" if pnl > 0 else ""
                            print(f"  [{now.strftime('%H:%M')}] {cid:<16} {reason.upper():<10} P&L: ${icon}{pnl:,.2f}")

                # New bar? Check signal
                if bar_time != st.last_bar_time:
                    st.last_bar_time = bar_time
                    closes = d["closes"]
                    highs = d["highs"]
                    lows = d["lows"]

                    sig_fn = SIGNAL_FNS[c["strategy"]]
                    direction, sl, tp, reason = sig_fn(closes, highs, lows, c["params"])

                    if direction != 0 and st.open_trade is None:
                        st.signals_generated += 1
                        entry = closes[-1]
                        sl_distance = abs(entry - sl)

                        # Guard: min SL distance = 0.5% of entry (prevent tiny ATR → exploding size)
                        min_sl_distance = entry * 0.005
                        if sl_distance < min_sl_distance:
                            sl_distance = min_sl_distance
                            if direction == 1:
                                sl = entry - sl_distance
                                tp = entry + sl_distance * 3
                            else:
                                sl = entry + sl_distance
                                tp = entry - sl_distance * 3

                        risk_dollar = st.capital * args.risk / 100
                        size = risk_dollar / sl_distance

                        # Guard: max position size = 5% of capital / price
                        max_size = st.capital * 0.05 / entry if entry > 0 else 0
                        if max_size > 0 and size > max_size:
                            size = max_size

                        spread_cost = entry * size * SPREAD_BPS.get(sym, 1) / 10000

                        st.open_trade = {
                            "direction": direction,
                            "entry": entry, "sl": sl, "tp": tp,
                            "size": size, "entry_time": now.isoformat(),
                            "reason": reason, "status": "open",
                        }
                        side = "LONG" if direction == 1 else "SHORT"
                        print(f"  [{now.strftime('%H:%M')}] {cid:<16} {side:<6} @ {entry:,.2f} SL={sl:,.2f} TP={tp:,.2f} size={size:.4f}")

                    elif direction != 0 and st.open_trade is not None and direction != st.open_trade["direction"]:
                        # Reverse — close current
                        tick = mt5.symbol_info_tick(sym)
                        current = tick.bid if st.open_trade["direction"] == 1 else tick.ask
                        ot = st.open_trade
                        spread_cost = current * ot["size"] * SPREAD_BPS.get(sym, 1) / 10000
                        if ot["direction"] == 1:
                            pnl = (current - ot["entry"]) * ot["size"] - spread_cost
                        else:
                            pnl = (ot["entry"] - current) * ot["size"] - spread_cost
                        st.trades.append({
                            "direction": "LONG" if ot["direction"] == 1 else "SHORT",
                            "entry": ot["entry"], "exit": current,
                            "pnl": round(pnl, 2), "reason": "reverse",
                            "entry_time": ot["entry_time"],
                            "exit_time": now.isoformat(),
                        })
                        st.total_pnl += pnl
                        if pnl > 0: st.wins += 1
                        else: st.losses += 1
                        _log_trade(LOG_DIR, cid, st.trades[-1])
                        st.open_trade = None

            # Status print every 15 cycles
            if cycle % 15 == 0:
                total_trades = sum(s.wins + s.losses for s in states.values())
                total_pnl = sum(s.total_pnl for s in states.values())
                total_signals = sum(s.signals_generated for s in states.values())
                open_count = sum(1 for s in states.values() if s.open_trade)
                print(f"\n  [{now.strftime('%H:%M')}] CYCLE {cycle} | Signals: {total_signals} | "
                      f"Trades: {total_trades} | Open: {open_count} | P&L: ${total_pnl:+,.2f}")
                print()

            await asyncio.sleep(60)

    except KeyboardInterrupt:
        print("\n\nStopping...")
    finally:
        # Close all open trades
        for cid, st in states.items():
            if st.open_trade and st.open_trade["status"] == "open":
                ot = st.open_trade
                sym = ot.get("symbol", st.cfg["symbol"])
                tick = mt5.symbol_info_tick(sym)
                current = tick.bid if ot["direction"] == 1 else tick.ask if tick else ot["entry"]
                spread_cost = current * ot["size"] * SPREAD_BPS.get(sym, 1) / 10000
                if ot["direction"] == 1:
                    pnl = (current - ot["entry"]) * ot["size"] - spread_cost
                else:
                    pnl = (ot["entry"] - current) * ot["size"] - spread_cost
                st.trades.append({
                    "direction": "LONG" if ot["direction"] == 1 else "SHORT",
                    "entry": ot["entry"], "exit": current,
                    "pnl": round(pnl, 2), "reason": "session_end",
                    "entry_time": ot["entry_time"], "exit_time": datetime.now(UTC).isoformat(),
                })
                st.total_pnl += pnl
                if pnl > 0: st.wins += 1
                else: st.losses += 1
                st.open_trade = None

        mt5.shutdown()

        # Final summary
        print("\n" + "=" * 80)
        print("MULTI-CAMPAIGN RESULTS")
        print("=" * 80)
        print(f"  {'ID':<16} {'Trades':>7} {'Wins':>5} {'WR%':>6} {'PF':>6} {'P&L':>12} {'Signals':>8}")
        print("  " + "-" * 65)
        for cid, st in sorted(states.items(), key=lambda x: x[1].total_pnl, reverse=True):
            t = st.wins + st.losses
            print(f"  {cid:<16} {t:>7} {st.wins:>5} {st.win_rate:>5.1f}% {st.profit_factor:>6.2f} ${st.total_pnl:>+11,.2f} {st.signals_generated:>8}")
        print("  " + "-" * 65)
        grand_pnl = sum(s.total_pnl for s in states.values())
        grand_trades = sum(s.wins + s.losses for s in states.values())
        print(f"  {'TOTAL':<16} {grand_trades:>7} {'':>5} {'':>6} {'':>6} ${grand_pnl:>+11,.2f}")

        # Save session report
        report = {
            "start_time": states[CAMPAIGNS[0]["id"]].trades[0]["entry_time"] if any(s.trades for s in states.values()) else "",
            "end_time": datetime.now(UTC).isoformat(),
            "duration_hours": args.hours,
            "total_capital": total_capital,
            "campaigns": {},
        }
        for cid, st in states.items():
            report["campaigns"][cid] = {
                "strategy": st.cfg["strategy"],
                "symbol": st.cfg["symbol"],
                "timeframe": st.cfg["tf"],
                "trades": st.wins + st.losses,
                "wins": st.wins,
                "win_rate": round(st.win_rate, 1),
                "profit_factor": round(st.profit_factor, 2),
                "total_pnl": round(st.total_pnl, 2),
                "signals": st.signals_generated,
            }
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        path = REPORTS_DIR / f"multi_session_{ts}.json"
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\n  Report saved: {path}")


def _log_trade(log_dir, cid, trade):
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(log_dir / "trades.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"campaign": cid, **trade}) + "\n")


def run():
    parser = argparse.ArgumentParser(description="Multi-Campaign Paper Trader")
    parser.add_argument("--hours", type=float, default=720)
    parser.add_argument("--capital", type=float, default=None)
    parser.add_argument("--risk", type=float, default=1.0, help="Risk per trade %%")
    args = parser.parse_args()

    import asyncio
    asyncio.run(main(args))


if __name__ == "__main__":
    run()
