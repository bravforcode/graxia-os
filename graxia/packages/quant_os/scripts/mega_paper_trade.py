"""
MEGA PAPER TRADER — ALL strategies × ALL symbols × ALL params × H1+H4

Generates ~300 campaigns. Collects live signal data for 30 days.
Each campaign gets virtual $100 capital for P&L tracking.

Usage:
    python scripts/mega_paper_trade.py --hours 720
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
os.chdir(_project_root)
sys.path.insert(0, str(_project_root))

import numpy as np
import pandas as pd

# ── Config ───────────────────────────────────────────────────────
CAPITAL_PER_CAMPAIGN = 1000  # virtual $1000 each (data collection, not real trading)
RISK_PCT = 1.0  # 1% risk per trade
BARS = 300
CHECK_INTERVAL_SEC = 55  # seconds between cycles

SPREAD_BPS = {
    "BTCUSD": 2.43, "ETHUSD": 11.67, "XAUUSD": 0.36, "XAGUSD": 6.58,
    "NAS100": 1.0, "US30": 0.5, "EURUSD": 0.07, "GBPUSD": 0.15,
    "AUDUSD": 0.1, "USDJPY": 0.06,
}

# All strategies × all symbols × H1 + H4 × all param variations
STRATEGIES = {
    "donchian": [
        {"period": 20, "vol_filter": True},
        {"period": 10, "vol_filter": True},
        {"period": 40, "vol_filter": True},
        {"period": 20, "vol_filter": False},
    ],
    "tsm": [
        {"lookbacks": [20, 40, 60, 120], "vol_target": 0.10},
        {"lookbacks": [10, 30, 50, 100], "vol_target": 0.12},
        {"lookbacks": [40, 80, 120, 200], "vol_target": 0.08},
    ],
    "rsi_bb": [
        {"rsi_period": 14, "rsi_oversold": 30, "rsi_overbought": 70, "bb_period": 20, "bb_std": 2.0},
        {"rsi_period": 7, "rsi_oversold": 25, "rsi_overbought": 75, "bb_period": 10, "bb_std": 1.5},
        {"rsi_period": 21, "rsi_oversold": 35, "rsi_overbought": 65, "bb_period": 30, "bb_std": 2.5},
    ],
    "mrb": [
        {"lookback": 20, "entry_z": 2.0, "exit_z": 0.5},
        {"lookback": 10, "entry_z": 1.5, "exit_z": 0.3},
        {"lookback": 30, "entry_z": 2.5, "exit_z": 0.7},
    ],
    "volume_breakout": [
        {"vol_period": 20, "vol_mult": 2.0, "lookback": 20},
        {"vol_period": 10, "vol_mult": 1.5, "lookback": 10},
        {"vol_period": 30, "vol_mult": 2.5, "lookback": 30},
    ],
}

SYMBOLS = ["BTCUSD", "ETHUSD", "XAUUSD", "XAGUSD", "NAS100", "US30", "EURUSD", "GBPUSD", "AUDUSD", "USDJPY"]
TIMEFRAMES = ["H1", "H4"]

LOG_DIR = _project_root / "logs" / "mega_paper"
REPORTS_DIR = _project_root / "reports" / "paper_engine"


# ── Generate all campaign configs ────────────────────────────────
def build_campaign_list() -> list[dict]:
    campaigns = []
    cid = 0
    for strat_id, param_list in STRATEGIES.items():
        for params in param_list:
            for symbol in SYMBOLS:
                for tf in TIMEFRAMES:
                    cid += 1
                    campaigns.append({
                        "id": f"{strat_id[:3]}_{symbol[:3].lower()}_{tf.lower()}_{cid:04d}",
                        "strategy": strat_id,
                        "symbol": symbol,
                        "tf": tf,
                        "params": params,
                        "param_idx": param_list.index(params),
                    })
    return campaigns


# ── Strategy signal functions (inline) ───────────────────────────
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
    vf = params.get("vol_filter", True)
    n = len(closes)
    if n < period + 2:
        return 0, 0, 0, ""
    i = n - 1
    hh = np.max(highs[i - period: i])
    ll = np.min(lows[i - period: i])
    atr = compute_atr(highs, lows, closes, 14)
    if np.isnan(atr[i]) or atr[i] <= 0 or closes[i] <= 0:
        return 0, 0, 0, ""
    atr_r = np.where(closes > 0, atr / closes, 0)
    med = np.nanmedian(atr_r[max(0, i - 200):i]) if i > 0 else 0
    vol_ok = (atr[i] / closes[i] > med * 0.8) if vf and med > 0 else True
    if closes[i] > hh and vol_ok:
        return 1, closes[i] - atr[i] * 2, closes[i] + atr[i] * 3, f"don_LONG hh={hh:.2f}"
    elif closes[i] < ll and vol_ok:
        return -1, closes[i] + atr[i] * 2, closes[i] - atr[i] * 3, f"don_SHORT ll={ll:.2f}"
    return 0, 0, 0, ""


def signal_tsm(closes, highs, lows, params):
    lbs = params.get("lookbacks", [20, 40, 60, 120])
    n = len(closes)
    if n < max(lbs) + 2:
        return 0, 0, 0, ""
    i = n - 1
    atr = compute_atr(highs, lows, closes, 14)
    if np.isnan(atr[i]) or atr[i] <= 0:
        return 0, 0, 0, ""
    zs = [(closes[i] - closes[i - lb]) / closes[i - lb] if closes[i - lb] > 0 else 0 for lb in lbs]
    avg_z = np.mean(zs)
    if avg_z > 0.5:
        return 1, closes[i] - atr[i] * 2, closes[i] + atr[i] * 3, f"tsm_LONG z={avg_z:.3f}"
    elif avg_z < -0.5:
        return -1, closes[i] + atr[i] * 2, closes[i] - atr[i] * 3, f"tsm_SHORT z={avg_z:.3f}"
    return 0, 0, 0, ""


def signal_rsi_bb(closes, highs, lows, params):
    rsi_p = params.get("rsi_period", 14)
    rsi_os = params.get("rsi_oversold", 30)
    rsi_ob = params.get("rsi_overbought", 70)
    bb_p = params.get("bb_period", 20)
    bb_s = params.get("bb_std", 2.0)
    n = len(closes)
    if n < max(rsi_p, bb_p) + 2:
        return 0, 0, 0, ""
    i = n - 1

    # RSI (last value)
    delta = np.diff(closes)
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    ag = np.mean(gains[:rsi_p]) if len(gains) >= rsi_p else 0
    al = np.mean(losses[:rsi_p]) if len(losses) >= rsi_p else 0
    for j in range(rsi_p, min(i, len(delta))):
        ag = (ag * (rsi_p - 1) + gains[j]) / rsi_p
        al = (al * (rsi_p - 1) + losses[j]) / rsi_p
    rsi = 100.0 - 100.0 / (1.0 + ag / (al + 1e-10)) if al > 0 else 100.0

    # BB (last value)
    window = closes[i - bb_p + 1: i + 1] if i >= bb_p else closes[:i + 1]
    mu = np.mean(window)
    sigma = np.std(window, ddof=1) if len(window) > 1 else 0
    lower = mu - bb_s * sigma
    upper = mu + bb_s * sigma

    atr = compute_atr(highs, lows, closes, 14)
    if np.isnan(atr[i]) or atr[i] <= 0:
        return 0, 0, 0, ""

    if rsi < rsi_os and closes[i] <= lower:
        return 1, closes[i] - atr[i] * 1.5, closes[i] + atr[i] * 2, f"rsi_LONG rsi={rsi:.1f}"
    elif rsi > rsi_ob and closes[i] >= upper:
        return -1, closes[i] + atr[i] * 1.5, closes[i] - atr[i] * 2, f"rsi_SHORT rsi={rsi:.1f}"
    return 0, 0, 0, ""


def signal_mrb(closes, highs, lows, params):
    lb = params.get("lookback", 20)
    entry_z = params.get("entry_z", 2.0)
    n = len(closes)
    if n < lb + 2:
        return 0, 0, 0, ""
    i = n - 1
    window = closes[i - lb: i]
    mu = np.mean(window)
    std = np.std(window, ddof=1)
    if std < 1e-10:
        return 0, 0, 0, ""
    z = (closes[i] - mu) / std

    atr = compute_atr(highs, lows, closes, 14)
    if np.isnan(atr[i]) or atr[i] <= 0:
        return 0, 0, 0, ""

    if z < -entry_z:
        return 1, closes[i] - atr[i] * 2, closes[i] + atr[i] * 2, f"mrb_LONG z={z:.2f}"
    elif z > entry_z:
        return -1, closes[i] + atr[i] * 2, closes[i] - atr[i] * 2, f"mrb_SHORT z={z:.2f}"
    return 0, 0, 0, ""


def signal_volume_breakout(closes, highs, lows, params):
    vp = params.get("vol_period", 20)
    vm = params.get("vol_mult", 2.0)
    lb = params.get("lookback", 20)
    n = len(closes)
    if n < max(vp, lb) + 2:
        return 0, 0, 0, ""
    i = n - 1
    # Use high/low range as volume proxy (no real volume in MT5 for all assets)
    ranges = highs - lows
    vol_ma = np.mean(ranges[i - vp: i])
    if vol_ma <= 0:
        return 0, 0, 0, ""
    vol_surge = ranges[i] > vol_ma * vm
    if not vol_surge:
        return 0, 0, 0, ""

    hh = np.max(highs[i - lb: i])
    ll = np.min(lows[i - lb: i])

    atr = compute_atr(highs, lows, closes, 14)
    if np.isnan(atr[i]) or atr[i] <= 0:
        return 0, 0, 0, ""

    if closes[i] > hh:
        return 1, closes[i] - atr[i] * 2, closes[i] + atr[i] * 3, f"vb_LONG hh={hh:.2f}"
    elif closes[i] < ll:
        return -1, closes[i] + atr[i] * 2, closes[i] - atr[i] * 3, f"vb_SHORT ll={ll:.2f}"
    return 0, 0, 0, ""


SIGNAL_FNS = {
    "donchian": signal_donchian,
    "tsm": signal_tsm,
    "rsi_bb": signal_rsi_bb,
    "mrb": signal_mrb,
    "volume_breakout": signal_volume_breakout,
}


# ── Campaign state ───────────────────────────────────────────────
@dataclass
class CampState:
    cfg: dict
    open_trade: dict | None = None
    trades: list = field(default_factory=list)
    total_pnl: float = 0.0
    wins: int = 0
    losses: int = 0
    last_bar_time: int = 0
    signals_generated: int = 0
    capital: float = CAPITAL_PER_CAMPAIGN

    @property
    def n_trades(self):
        return self.wins + self.losses

    @property
    def win_rate(self):
        return self.wins / self.n_trades * 100 if self.n_trades > 0 else 0

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
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    campaigns = build_campaign_list()
    tf_const = {"H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4}

    states: dict[str, CampState] = {}
    for c in campaigns:
        states[c["id"]] = CampState(cfg=c)

    # Build symbol data cache: {tf: {symbol: {closes, highs, lows, bar_time}}}
    def fetch_all():
        data = {}
        for tf in TIMEFRAMES:
            data[tf] = {}
            tf_c = tf_const[tf]
            for symbol in SYMBOLS:
                rates = mt5.copy_rates_from_pos(symbol, tf_c, 0, BARS)
                if rates is not None and len(rates) >= BARS:
                    data[tf][symbol] = {
                        "closes": np.array([r["close"] for r in rates], dtype=float),
                        "highs": np.array([r["high"] for r in rates], dtype=float),
                        "lows": np.array([r["low"] for r in rates], dtype=float),
                        "bar_time": int(rates[-1]["time"]),
                    }
        return data

    # Count unique combos
    strat_count = len(STRATEGIES)
    param_count = sum(len(v) for v in STRATEGIES.values())
    sym_count = len(SYMBOLS)
    tf_count = len(TIMEFRAMES)

    print("=" * 80)
    print("MEGA PAPER TRADER")
    print("=" * 80)
    print(f"  Total campaigns:   {len(campaigns)}")
    print(f"  Strategies:        {strat_count}")
    print(f"  Param variations:  {param_count}")
    print(f"  Symbols:           {sym_count}")
    print(f"  Timeframes:        {tf_count}")
    print(f"  Virtual capital:   ${CAPITAL_PER_CAMPAIGN}/campaign (${CAPITAL_PER_CAMPAIGN * len(campaigns):,.0f} total)")
    print(f"  Duration:          {args.hours}h")
    print(f"  Account:           {account.server} #{account.login}")
    print(f"  Balance:           ${account.balance:,.2f}")
    print()
    print(f"  Formula: {strat_count} strategies x {param_count} params x {sym_count} symbols x {tf_count} TFs = {len(campaigns)}")
    print()

    # Print first/last 5
    print(f"  {'ID':<35} {'Strategy':<18} {'Symbol':<10} {'TF':<4}")
    print("  " + "-" * 70)
    for c in campaigns[:5]:
        print(f"  {c['id']:<35} {c['strategy']:<18} {c['symbol']:<10} {c['tf']:<4}")
    print(f"  ... ({len(campaigns) - 10} more)")
    for c in campaigns[-5:]:
        print(f"  {c['id']:<35} {c['strategy']:<18} {c['symbol']:<10} {c['tf']:<4}")
    print()

    end_time = datetime.now(UTC) + timedelta(hours=args.hours)
    cycle = 0
    start_ts = datetime.now(UTC).isoformat()

    try:
        while datetime.now(UTC) < end_time:
            cycle += 1
            now = datetime.now(UTC)
            tf_data = fetch_all()

            signals_this_cycle = 0
            trades_this_cycle = 0

            for c in campaigns:
                cid = c["id"]
                st = states[cid]
                sym = c["symbol"]
                tf = c["tf"]

                if sym not in tf_data.get(tf, {}):
                    continue

                d = tf_data[tf][sym]
                bar_time = d["bar_time"]
                closes = d["closes"]
                highs = d["highs"]
                lows = d["lows"]

                # Check SL/TP on open trade
                if st.open_trade:
                    tick = mt5.symbol_info_tick(sym)
                    if tick:
                        current = tick.bid if st.open_trade["direction"] == 1 else tick.ask
                        ot = st.open_trade
                        hit_sl = (ot["direction"] == 1 and current <= ot["sl"]) or \
                                 (ot["direction"] == -1 and current >= ot["sl"])
                        hit_tp = (ot["direction"] == 1 and current >= ot["tp"]) or \
                                 (ot["direction"] == -1 and current <= ot["tp"])
                        if hit_sl or hit_tp:
                            reason = "stop_loss" if hit_sl else "take_profit"
                            exit_p = ot["sl"] if hit_sl else ot["tp"]
                            sc = exit_p * ot["size"] * SPREAD_BPS.get(sym, 1) / 10000 * 2
                            if ot["direction"] == 1:
                                pnl = (exit_p - ot["entry"]) * ot["size"] - sc
                            else:
                                pnl = (ot["entry"] - exit_p) * ot["size"] - sc
                            st.trades.append({"pnl": round(pnl, 2), "reason": reason,
                                               "dir": "L" if ot["direction"] == 1 else "S",
                                               "entry": ot["entry"], "exit": exit_p,
                                               "bar": now.isoformat()})
                            st.total_pnl += pnl
                            if pnl > 0: st.wins += 1
                            else: st.losses += 1
                            st.open_trade = None
                            trades_this_cycle += 1

                # New bar? Check signal
                if bar_time != st.last_bar_time:
                    st.last_bar_time = bar_time
                    sig_fn = SIGNAL_FNS[c["strategy"]]
                    direction, sl, tp, reason = sig_fn(closes, highs, lows, c["params"])

                    if direction != 0 and st.open_trade is None:
                        st.signals_generated += 1
                        signals_this_cycle += 1
                        entry = closes[-1]
                        sl_dist = abs(entry - sl)
                        min_sl = entry * 0.005
                        if sl_dist < min_sl:
                            sl_dist = min_sl
                            sl = entry - sl_dist if direction == 1 else entry + sl_dist
                            tp = entry + sl_dist * 3 if direction == 1 else entry - sl_dist * 3
                        risk_dollar = st.capital * RISK_PCT / 100
                        size = risk_dollar / sl_dist
                        max_size = st.capital * 0.05 / entry if entry > 0 else 0
                        if max_size > 0 and size > max_size:
                            size = max_size
                        st.open_trade = {
                            "direction": direction, "entry": entry,
                            "sl": sl, "tp": tp, "size": size,
                        }

            # Progress print
            if cycle % 10 == 0:
                total_trades = sum(s.n_trades for s in states.values())
                total_signals = sum(s.signals_generated for s in states.values())
                total_pnl = sum(s.total_pnl for s in states.values())
                open_count = sum(1 for s in states.values() if s.open_trade)
                elapsed = (now - datetime.fromisoformat(start_ts).replace(tzinfo=UTC)).total_seconds() / 3600
                print(f"  [{now.strftime('%H:%M')}] cycle={cycle} "
                      f"signals={total_signals} trades={total_trades} "
                      f"open={open_count} pnl=${total_pnl:+,.0f} "
                      f"elapsed={elapsed:.1f}h")
                if signals_this_cycle > 0:
                    print(f"    +{signals_this_cycle} signals, +{trades_this_cycle} trades this cycle")

            # Save checkpoint every 100 cycles
            if cycle % 100 == 0:
                _save_checkpoint(states, cycle, start_ts, args.hours)

            await asyncio.sleep(CHECK_INTERVAL_SEC)

    except KeyboardInterrupt:
        print("\n\nStopping...")
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Close open trades
        for cid, st in states.items():
            if st.open_trade:
                ot = st.open_trade
                sym = st.cfg["symbol"]
                tick = mt5.symbol_info_tick(sym)
                current = tick.bid if ot["direction"] == 1 else tick.ask if tick else ot["entry"]
                sc = current * ot["size"] * SPREAD_BPS.get(sym, 1) / 10000 * 2
                if ot["direction"] == 1:
                    pnl = (current - ot["entry"]) * ot["size"] - sc
                else:
                    pnl = (ot["entry"] - current) * ot["size"] - sc
                st.trades.append({"pnl": round(pnl, 2), "reason": "session_end",
                                   "dir": "L" if ot["direction"] == 1 else "S",
                                   "entry": ot["entry"], "exit": current,
                                   "bar": datetime.now(UTC).isoformat()})
                st.total_pnl += pnl
                if pnl > 0: st.wins += 1
                else: st.losses += 1
                st.open_trade = None

        mt5.shutdown()

        # Save final
        _save_final(states, start_ts, args.hours, len(campaigns))

        # Print summary — top 20 by P&L
        print("\n" + "=" * 80)
        print("TOP 20 CAMPAIGNS BY P&L")
        print("=" * 80)
        print(f"  {'ID':<35} {'Strat':<8} {'Sym':<8} {'TF':<4} {'#T':>4} {'WR%':>6} {'PF':>6} {'P&L':>10}")
        print("  " + "-" * 85)
        ranked = sorted(states.values(), key=lambda s: s.total_pnl, reverse=True)
        for st in ranked[:20]:
            c = st.cfg
            print(f"  {c['id']:<35} {c['strategy'][:8]:<8} {c['symbol'][:8]:<8} {c['tf']:<4} "
                  f"{st.n_trades:>4} {st.win_rate:>5.1f}% {st.profit_factor:>6.2f} ${st.total_pnl:>+9,.2f}")

        # Bottom 10
        print("\n  BOTTOM 10:")
        for st in ranked[-10:]:
            c = st.cfg
            print(f"  {c['id']:<35} {c['strategy'][:8]:<8} {c['symbol'][:8]:<8} {c['tf']:<4} "
                  f"{st.n_trades:>4} {st.win_rate:>5.1f}% {st.profit_factor:>6.2f} ${st.total_pnl:>+9,.2f}")

        # Stats
        total_trades = sum(s.n_trades for s in states.values())
        total_signals = sum(s.signals_generated for s in states.values())
        total_pnl = sum(s.total_pnl for s in states.values())
        campaigns_with_trades = sum(1 for s in states.values() if s.n_trades > 0)
        print(f"\n  Total signals:    {total_signals}")
        print(f"  Total trades:     {total_trades}")
        print(f"  Campaigns active: {campaigns_with_trades}/{len(campaigns)}")
        print(f"  Total P&L:        ${total_pnl:+,.2f}")
        print("=" * 80)


def _save_checkpoint(states, cycle, start_ts, hours):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    data = {}
    for cid, st in states.items():
        if st.n_trades > 0 or st.signals_generated > 0:
            data[cid] = {
                "strategy": st.cfg["strategy"], "symbol": st.cfg["symbol"], "tf": st.cfg["tf"],
                "trades": st.n_trades, "wins": st.wins, "pnl": round(st.total_pnl, 2),
                "signals": st.signals_generated,
            }
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = REPORTS_DIR / f"mega_checkpoint_{ts}.json"
    path.write_text(json.dumps({"cycle": cycle, "campaigns": data}, indent=2), encoding="utf-8")
    print(f"  Checkpoint saved: {path.name}")


def _save_final(states, start_ts, hours, n_campaigns):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    data = {}
    for cid, st in states.items():
        data[cid] = {
            "strategy": st.cfg["strategy"], "symbol": st.cfg["symbol"], "tf": st.cfg["tf"],
            "param_idx": st.cfg["param_idx"], "trades": st.n_trades, "wins": st.wins,
            "win_rate": round(st.win_rate, 1), "pf": round(st.profit_factor, 2),
            "pnl": round(st.total_pnl, 2), "signals": st.signals_generated,
            "trades_data": st.trades[-50:],  # last 50 trades only
        }
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = REPORTS_DIR / f"mega_session_{ts}.json"
    path.write_text(json.dumps({
        "start": start_ts, "end": datetime.now(UTC).isoformat(),
        "hours": hours, "n_campaigns": n_campaigns, "campaigns": data,
    }, indent=2), encoding="utf-8")
    print(f"\n  Final report: {path}")


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=720)
    args = parser.parse_args()
    asyncio.run(main(args))


if __name__ == "__main__":
    run()
