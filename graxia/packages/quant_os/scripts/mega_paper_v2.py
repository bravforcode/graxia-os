"""
MEGA PAPER TRADER V2 — MASSIVE + HIGH QUALITY

1,440 campaigns: 5 strategies × 6 params × 12 symbols × 4 timeframes
Quality: live Sharpe, Sortino, max DD, correlation, regime filter, spread tracking

Usage:
    python scripts/mega_paper_v2.py --hours 720
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parent.parent
os.chdir(_project_root)
sys.path.insert(0, str(_project_root))

import numpy as np
import pandas as pd

# ── Config ───────────────────────────────────────────────────────
VIRTUAL_CAPITAL = 1000
RISK_PCT = 1.0
BARS = 300
CHECK_SEC = 50
STRATEGIES_LIST = ["donchian", "tsm", "rsi_bb", "mrb", "volume_breakout"]
SYMBOLS = ["BTCUSD", "ETHUSD", "XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD",
           "NAS100", "US30", "EURUSD", "GBPUSD", "AUDUSD", "USDJPY"]
TIMEFRAMES = ["M15", "M30", "H1", "H4"]
SPREAD_BPS = {
    "BTCUSD": 2.43, "ETHUSD": 11.67, "XAUUSD": 0.36, "XAGUSD": 6.58,
    "XPTUSD": 3.0, "XPDUSD": 5.0, "NAS100": 1.0, "US30": 0.5,
    "EURUSD": 0.07, "GBPUSD": 0.15, "AUDUSD": 0.1, "USDJPY": 0.06,
}

PARAM_GRIDS = {
    "donchian": [
        {"period": 10, "vol_filter": True},
        {"period": 15, "vol_filter": True},
        {"period": 20, "vol_filter": True},
        {"period": 30, "vol_filter": True},
        {"period": 40, "vol_filter": True},
        {"period": 20, "vol_filter": False},
    ],
    "tsm": [
        {"lookbacks": [10, 20, 40, 80], "vol_target": 0.10},
        {"lookbacks": [20, 40, 60, 120], "vol_target": 0.10},
        {"lookbacks": [30, 60, 90, 180], "vol_target": 0.08},
        {"lookbacks": [15, 30, 50, 100], "vol_target": 0.12},
        {"lookbacks": [40, 80, 120, 200], "vol_target": 0.06},
        {"lookbacks": [5, 10, 20, 40], "vol_target": 0.15},
    ],
    "rsi_bb": [
        {"rsi_period": 7, "rsi_oversold": 25, "rsi_overbought": 75, "bb_period": 10, "bb_std": 1.5},
        {"rsi_period": 10, "rsi_oversold": 28, "rsi_overbought": 72, "bb_period": 15, "bb_std": 1.8},
        {"rsi_period": 14, "rsi_oversold": 30, "rsi_overbought": 70, "bb_period": 20, "bb_std": 2.0},
        {"rsi_period": 21, "rsi_oversold": 33, "rsi_overbought": 67, "bb_period": 25, "bb_std": 2.2},
        {"rsi_period": 21, "rsi_oversold": 35, "rsi_overbought": 65, "bb_period": 30, "bb_std": 2.5},
        {"rsi_period": 5, "rsi_oversold": 20, "rsi_overbought": 80, "bb_period": 8, "bb_std": 1.2},
    ],
    "mrb": [
        {"lookback": 10, "entry_z": 1.5, "exit_z": 0.3},
        {"lookback": 15, "entry_z": 1.8, "exit_z": 0.4},
        {"lookback": 20, "entry_z": 2.0, "exit_z": 0.5},
        {"lookback": 30, "entry_z": 2.2, "exit_z": 0.5},
        {"lookback": 40, "entry_z": 2.5, "exit_z": 0.7},
        {"lookback": 25, "entry_z": 1.8, "exit_z": 0.3},
    ],
    "volume_breakout": [
        {"vol_period": 10, "vol_mult": 1.5, "lookback": 10},
        {"vol_period": 15, "vol_mult": 1.8, "lookback": 15},
        {"vol_period": 20, "vol_mult": 2.0, "lookback": 20},
        {"vol_period": 25, "vol_mult": 2.2, "lookback": 25},
        {"vol_period": 30, "vol_mult": 2.5, "lookback": 30},
        {"vol_period": 20, "vol_mult": 1.5, "lookback": 30},
    ],
}

TF_CONST_MAP = {}  # filled at runtime with mt5 constants

LOG_DIR = _project_root / "logs" / "mega_v2"
REPORTS_DIR = _project_root / "reports" / "paper_engine"


# ── Build campaigns ──────────────────────────────────────────────
def build_campaigns() -> list[dict]:
    campaigns = []
    cid = 0
    for strat in STRATEGIES_LIST:
        for pi, params in enumerate(PARAM_GRIDS[strat]):
            for symbol in SYMBOLS:
                for tf in TIMEFRAMES:
                    cid += 1
                    campaigns.append({
                        "id": f"{strat[:3]}_{symbol[:3].lower()}_{tf.lower()}_{pi+1}_{cid:05d}",
                        "strategy": strat, "symbol": symbol, "tf": tf,
                        "params": params, "param_idx": pi,
                    })
    return campaigns


# ── Strategy signals ─────────────────────────────────────────────
def _atr(highs, lows, closes, period=14):
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


def sig_donchian(c, h, l, p):
    per = p.get("period", 20); vf = p.get("vol_filter", True); n = len(c)
    if n < per + 2: return 0, 0, 0, ""
    i = n - 1; hh = np.max(h[i-per:i]); ll = np.min(l[i-per:i])
    atr = _atr(h, l, c)
    if np.isnan(atr[i]) or atr[i] <= 0 or c[i] <= 0: return 0, 0, 0, ""
    ar = np.where(c > 0, atr / c, 0)
    med = np.nanmedian(ar[max(0, i-200):i]) if i > 0 else 0
    ok = (atr[i]/c[i] > med*0.8) if vf and med > 0 else True
    if c[i] > hh and ok: return 1, c[i]-atr[i]*2, c[i]+atr[i]*3, f"D+"
    if c[i] < ll and ok: return -1, c[i]+atr[i]*2, c[i]-atr[i]*3, f"D-"
    return 0, 0, 0, ""


def sig_tsm(c, h, l, p):
    lbs = p.get("lookbacks", [20,40,60,120]); n = len(c)
    if n < max(lbs)+2: return 0, 0, 0, ""
    i = n-1; atr = _atr(h, l, c)
    if np.isnan(atr[i]) or atr[i] <= 0: return 0, 0, 0, ""
    zs = [(c[i]-c[i-lb])/c[i-lb] if c[i-lb]>0 else 0 for lb in lbs]
    az = np.mean(zs)
    if az > 0.5: return 1, c[i]-atr[i]*2, c[i]+atr[i]*3, f"T+ z={az:.2f}"
    if az < -0.5: return -1, c[i]+atr[i]*2, c[i]-atr[i]*3, f"T- z={az:.2f}"
    return 0, 0, 0, ""


def sig_rsi_bb(c, h, l, p):
    rp = p.get("rsi_period", 14); ros = p.get("rsi_oversold", 30); rob = p.get("rsi_overbought", 70)
    bbp = p.get("bb_period", 20); bbs = p.get("bb_std", 2.0); n = len(c)
    if n < max(rp, bbp)+2: return 0, 0, 0, ""
    i = n-1
    d = np.diff(c); g = np.where(d>0,d,0.0); ls = np.where(d<0,-d,0.0)
    ag = np.mean(g[:rp]) if len(g)>=rp else 0; al = np.mean(ls[:rp]) if len(ls)>=rp else 0
    for j in range(rp, min(i, len(d))):
        ag = (ag*(rp-1)+g[j])/rp; al = (al*(rp-1)+ls[j])/rp
    rsi = 100-100/(1+ag/(al+1e-10)) if al>0 else 100
    w = c[i-bbp+1:i+1] if i>=bbp else c[:i+1]
    mu = np.mean(w); sig = np.std(w, ddof=1) if len(w)>1 else 0
    lo = mu-bbs*sig; up = mu+bbs*sig
    atr = _atr(h, l, c)
    if np.isnan(atr[i]) or atr[i]<=0: return 0, 0, 0, ""
    if rsi<ros and c[i]<=lo: return 1, c[i]-atr[i]*1.5, c[i]+atr[i]*2, f"R+ rsi={rsi:.0f}"
    if rsi>rob and c[i]>=up: return -1, c[i]+atr[i]*1.5, c[i]-atr[i]*2, f"R- rsi={rsi:.0f}"
    return 0, 0, 0, ""


def sig_mrb(c, h, l, p):
    lb = p.get("lookback", 20); ez = p.get("entry_z", 2.0); n = len(c)
    if n < lb+2: return 0, 0, 0, ""
    i = n-1; w = c[i-lb:i]; mu = np.mean(w); sd = np.std(w, ddof=1)
    if sd < 1e-10: return 0, 0, 0, ""
    z = (c[i]-mu)/sd
    atr = _atr(h, l, c)
    if np.isnan(atr[i]) or atr[i]<=0: return 0, 0, 0, ""
    if z < -ez: return 1, c[i]-atr[i]*2, c[i]+atr[i]*2, f"M+ z={z:.2f}"
    if z > ez: return -1, c[i]+atr[i]*2, c[i]-atr[i]*2, f"M- z={z:.2f}"
    return 0, 0, 0, ""


def sig_vb(c, h, l, p):
    vp = p.get("vol_period", 20); vm = p.get("vol_mult", 2.0); lb = p.get("lookback", 20); n = len(c)
    if n < max(vp, lb)+2: return 0, 0, 0, ""
    i = n-1; ranges = h-l; vma = np.mean(ranges[i-vp:i])
    if vma <= 0: return 0, 0, 0, ""
    if ranges[i] <= vma*vm: return 0, 0, 0, ""
    hh = np.max(h[i-lb:i]); ll = np.min(l[i-lb:i])
    atr = _atr(h, l, c)
    if np.isnan(atr[i]) or atr[i]<=0: return 0, 0, 0, ""
    if c[i]>hh: return 1, c[i]-atr[i]*2, c[i]+atr[i]*3, f"V+"
    if c[i]<ll: return -1, c[i]+atr[i]*2, c[i]-atr[i]*3, f"V-"
    return 0, 0, 0, ""


SIGS = {"donchian": sig_donchian, "tsm": sig_tsm, "rsi_bb": sig_rsi_bb, "mrb": sig_mrb, "volume_breakout": sig_vb}


# ── Quality metrics ──────────────────────────────────────────────
@dataclass
class QualityMetrics:
    """Rolling quality metrics for a single campaign."""
    pnls: list = field(default_factory=list)
    max_dd: float = 0.0
    peak: float = 0.0
    equity: float = 0.0

    def add(self, pnl: float):
        self.pnls.append(pnl)
        self.equity += pnl
        if self.equity > self.peak: self.peak = self.equity
        dd = self.peak - self.equity
        if dd > self.max_dd: self.max_dd = dd

    @property
    def n(self): return len(self.pnls)

    @property
    def wins(self): return sum(1 for p in self.pnls if p > 0)

    @property
    def win_rate(self): return self.wins / self.n * 100 if self.n > 0 else 0

    @property
    def avg_win(self):
        w = [p for p in self.pnls if p > 0]
        return float(np.mean(w)) if w else 0

    @property
    def avg_loss(self):
        ls = [p for p in self.pnls if p <= 0]
        return float(np.mean(ls)) if ls else 0

    @property
    def expectancy(self):
        if self.n == 0: return 0
        wr = self.wins / self.n
        return wr * self.avg_win + (1 - wr) * self.avg_loss

    @property
    def profit_factor(self):
        gp = sum(p for p in self.pnls if p > 0)
        gl = abs(sum(p for p in self.pnls if p <= 0))
        return gp / gl if gl > 0 else float("inf")

    @property
    def sharpe(self):
        if self.n < 3: return 0
        a = np.array(self.pnls)
        m = np.mean(a); s = np.std(a)
        return float(m / s * np.sqrt(252)) if s > 1e-10 else 0

    @property
    def sortino(self):
        if self.n < 3: return 0
        neg = np.array([p for p in self.pnls if p < 0])
        if len(neg) == 0: return 999.0
        ds = float(np.std(neg))
        return float(np.mean(self.pnls) / ds * np.sqrt(252)) if ds > 1e-10 else 0


# ── Campaign state ───────────────────────────────────────────────
@dataclass
class CampState:
    cfg: dict
    open_trade: dict | None = None
    qm: QualityMetrics = field(default_factory=QualityMetrics)
    last_bar_time: int = 0
    signals: int = 0
    capital: float = VIRTUAL_CAPITAL

    @property
    def n_trades(self): return self.qm.n
    @property
    def total_pnl(self): return self.qm.equity
    @property
    def win_rate(self): return self.qm.win_rate
    @property
    def pf(self): return self.qm.profit_factor
    @property
    def sharpe(self): return self.qm.sharpe


# ── Portfolio tracker ────────────────────────────────────────────
class PortfolioTracker:
    """Track cross-campaign correlations + portfolio metrics."""

    def __init__(self):
        self.symbol_pnl: dict[str, list[float]] = defaultdict(list)
        self.correlation_refresh = 0

    def record(self, symbol: str, pnl: float):
        self.symbol_pnl[symbol].append(pnl)

    def correlation_matrix(self) -> dict:
        """Compute correlation between symbols from P&L series."""
        syms = [s for s, v in self.symbol_pnl.items() if len(v) >= 5]
        if len(syms) < 2: return {}
        # Truncate to same length
        min_len = min(len(self.symbol_pnl[s]) for s in syms)
        data = np.array([self.symbol_pnl[s][-min_len:] for s in syms])
        corr = np.corrcoef(data)
        result = {}
        for i, s1 in enumerate(syms):
            for j, s2 in enumerate(syms):
                if i < j:
                    result[f"{s1}/{s2}"] = round(float(corr[i, j]), 3)
        return result

    def high_correlation_pairs(self, threshold=0.7) -> list[str]:
        corr = self.correlation_matrix()
        return [k for k, v in corr.items() if abs(v) > threshold]


# ── Main ─────────────────────────────────────────────────────────
async def main(args):
    import MetaTrader5 as mt5
    if not mt5.initialize():
        mt5.initialize(path=r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe")
    account = mt5.account_info()

    TF_CONST_MAP["M15"] = mt5.TIMEFRAME_M15
    TF_CONST_MAP["M30"] = mt5.TIMEFRAME_M30
    TF_CONST_MAP["H1"] = mt5.TIMEFRAME_H1
    TF_CONST_MAP["H4"] = mt5.TIMEFRAME_H4

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    campaigns = build_campaigns()
    states: dict[str, CampState] = {}
    for c in campaigns:
        states[c["id"]] = CampState(cfg=c)

    portfolio = PortfolioTracker()
    daily_report_hour = -1  # print daily report once per UTC day

    def fetch_all():
        data = {}
        for tf in TIMEFRAMES:
            data[tf] = {}
            tf_c = TF_CONST_MAP[tf]
            for sym in SYMBOLS:
                rates = mt5.copy_rates_from_pos(sym, tf_c, 0, BARS)
                if rates is not None and len(rates) >= BARS:
                    data[tf][sym] = {
                        "c": np.array([r["close"] for r in rates], dtype=float),
                        "h": np.array([r["high"] for r in rates], dtype=float),
                        "l": np.array([r["low"] for r in rates], dtype=float),
                        "bt": int(rates[-1]["time"]),
                    }
        return data

    n_c = len(campaigns)
    n_s = len(STRATEGIES_LIST)
    n_p = sum(len(v) for v in PARAM_GRIDS.values())
    n_sym = len(SYMBOLS)
    n_tf = len(TIMEFRAMES)

    print("=" * 80)
    print("MEGA PAPER TRADER V2 — MASSIVE + HIGH QUALITY")
    print("=" * 80)
    print(f"  Campaigns:   {n_c}")
    print(f"  Formula:     {n_s} strategies × {n_p} params × {n_sym} symbols × {n_tf} TFs")
    print(f"  Duration:    {args.hours}h ({args.hours/24:.0f} days)")
    print(f"  Capital:     ${VIRTUAL_CAPITAL}/campaign (${VIRTUAL_CAPITAL*n_c:,.0f} virtual)")
    print(f"  Account:     {account.server} #{account.login} (${account.balance:,.0f})")
    print(f"  Quality:     Sharpe, Sortino, MaxDD, Correlation, Regime filter")
    print()

    end_time = datetime.now(UTC) + timedelta(hours=args.hours)
    cycle = 0
    start_ts = datetime.now(UTC).isoformat()

    try:
        while datetime.now(UTC) < end_time:
            cycle += 1
            now = datetime.now(UTC)
            tf_data = fetch_all()
            sigs_this = 0; trades_this = 0

            for c in campaigns:
                cid = c["id"]
                st = states[cid]
                sym = c["symbol"]
                tf = c["tf"]

                if sym not in tf_data.get(tf, {}):
                    continue
                d = tf_data[tf][sym]
                bt = d["bt"]; c_arr = d["c"]; h_arr = d["h"]; l_arr = d["l"]

                # Check SL/TP
                if st.open_trade:
                    tick = mt5.symbol_info_tick(sym)
                    if tick:
                        cur = tick.bid if st.open_trade["d"] == 1 else tick.ask
                        ot = st.open_trade
                        hit_sl = (ot["d"]==1 and cur<=ot["sl"]) or (ot["d"]==-1 and cur>=ot["sl"])
                        hit_tp = (ot["d"]==1 and cur>=ot["tp"]) or (ot["d"]==-1 and cur<=ot["tp"])
                        if hit_sl or hit_tp:
                            ep = ot["sl"] if hit_sl else ot["tp"]
                            sc = ep * ot["sz"] * SPREAD_BPS.get(sym, 1) / 10000 * 2
                            pnl = ((ep-ot["e"])*ot["sz"] if ot["d"]==1 else (ot["e"]-ep)*ot["sz"]) - sc
                            st.qm.add(round(pnl, 4))
                            portfolio.record(sym, pnl)
                            st.open_trade = None
                            trades_this += 1

                # New bar signal
                if bt != st.last_bar_time:
                    st.last_bar_time = bt
                    sig_fn = SIGS[c["strategy"]]
                    dirc, sl, tp, reason = sig_fn(c_arr, h_arr, l_arr, c["params"])

                    if dirc != 0 and st.open_trade is None:
                        st.signals += 1; sigs_this += 1
                        entry = c_arr[-1]
                        sd = abs(entry - sl)
                        min_sd = entry * 0.005
                        if sd < min_sd:
                            sd = min_sd
                            sl = entry - sd if dirc == 1 else entry + sd
                            tp = entry + sd*3 if dirc == 1 else entry - sd*3
                        rd = st.capital * RISK_PCT / 100
                        sz = rd / sd
                        ms = st.capital * 0.05 / entry if entry > 0 else 0
                        if ms > 0 and sz > ms: sz = ms
                        st.open_trade = {"d": dirc, "e": entry, "sl": sl, "tp": tp, "sz": sz}

            # Progress
            if cycle % 10 == 0:
                tot_t = sum(s.n_trades for s in states.values())
                tot_s = sum(s.signals for s in states.values())
                tot_pnl = sum(s.total_pnl for s in states.values())
                opn = sum(1 for s in states.values() if s.open_trade)
                elapsed = (now - datetime.fromisoformat(start_ts).replace(tzinfo=UTC)).total_seconds() / 3600
                # Best campaign
                best = max(states.values(), key=lambda s: s.total_pnl)
                worst = min(states.values(), key=lambda s: s.total_pnl)
                hi_corr = portfolio.high_correlation_pairs(0.7)
                print(f"\n  [{now.strftime('%H:%M')}] cycle={cycle} signals={tot_s} trades={tot_t} "
                      f"open={opn} pnl=${tot_pnl:+,.1f} elapsed={elapsed:.1f}h")
                print(f"    best: {best.cfg['id'][:30]} pnl=${best.total_pnl:+.2f} sharpe={best.sharpe:.2f}")
                print(f"    worst: {worst.cfg['id'][:30]} pnl=${worst.total_pnl:+.2f}")
                if hi_corr:
                    print(f"    high corr: {', '.join(hi_corr[:3])}")

            # Daily report
            if now.hour == 0 and now.minute < 2 and daily_report_hour != now.day:
                daily_report_hour = now.day
                _daily_report(states, portfolio, cycle, start_ts)

            # Checkpoint every 100 cycles
            if cycle % 100 == 0:
                _checkpoint(states, portfolio, cycle, start_ts, args.hours, n_c)

            await asyncio.sleep(CHECK_SEC)

    except KeyboardInterrupt:
        print("\n\nStopping...")
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        for cid, st in states.items():
            if st.open_trade:
                ot = st.open_trade; sym = st.cfg["symbol"]
                tick = mt5.symbol_info_tick(sym)
                cur = tick.bid if ot["d"]==1 else (tick.ask if tick else ot["e"])
                sc = cur*ot["sz"]*SPREAD_BPS.get(sym,1)/10000*2
                pnl = ((cur-ot["e"])*ot["sz"] if ot["d"]==1 else (ot["e"]-cur)*ot["sz"]) - sc
                st.qm.add(round(pnl, 4))
                st.open_trade = None
        mt5.shutdown()
        _final_report(states, portfolio, start_ts, args.hours, n_c)


def _daily_report(states, portfolio, cycle, start_ts):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d")
    ranked = sorted(states.values(), key=lambda s: s.total_pnl, reverse=True)
    active = [s for s in ranked if s.n_trades >= 3]
    report = {
        "date": ts, "cycle": cycle,
        "total_campaigns": len(states),
        "active_campaigns": len(active),
        "total_trades": sum(s.n_trades for s in states.values()),
        "total_pnl": round(sum(s.total_pnl for s in states.values()), 2),
        "high_corr": portfolio.high_correlation_pairs(0.7),
        "top_10": [{"id": s.cfg["id"][:35], "strat": s.cfg["strategy"],
                     "sym": s.cfg["symbol"], "tf": s.cfg["tf"],
                     "trades": s.n_trades, "wr": round(s.win_rate, 1),
                     "sharpe": round(s.sharpe, 2), "pnl": round(s.total_pnl, 2)}
                    for s in active[:10]],
        "bottom_5": [{"id": s.cfg["id"][:35], "pnl": round(s.total_pnl, 2)}
                     for s in active[-5:]],
    }
    path = REPORTS_DIR / f"mega_daily_{ts}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n  DAILY REPORT: {path.name} | trades={report['total_trades']} pnl=${report['total_pnl']:+,.1f}")


def _checkpoint(states, portfolio, cycle, start_ts, hours, n_c):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    data = {}
    for cid, st in states.items():
        if st.n_trades > 0 or st.signals > 0:
            data[cid] = {
                "s": st.cfg["strategy"], "y": st.cfg["symbol"], "tf": st.cfg["tf"],
                "pi": st.cfg["param_idx"],
                "n": st.n_trades, "w": st.qm.wins, "wr": round(st.win_rate, 1),
                "sh": round(st.sharpe, 2), "so": round(st.sortino, 2),
                "pf": round(st.pf, 2), "dd": round(st.qm.max_dd, 2),
                "pnl": round(st.total_pnl, 2), "sig": st.signals,
            }
    corr = portfolio.correlation_matrix()
    path = REPORTS_DIR / f"mega_v2_ckpt_{ts}.json"
    path.write_text(json.dumps({"cycle": cycle, "campaigns": data,
                                 "correlation": corr, "high_corr": portfolio.high_correlation_pairs(0.7)},
                                indent=2), encoding="utf-8")
    print(f"  Checkpoint: {path.name} ({len(data)} active campaigns)")


def _final_report(states, portfolio, start_ts, hours, n_c):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    ranked = sorted(states.values(), key=lambda s: s.total_pnl, reverse=True)

    report = {
        "start": start_ts, "end": datetime.now(UTC).isoformat(),
        "hours": hours, "n_campaigns": n_c,
        "summary": {
            "total_trades": sum(s.n_trades for s in states.values()),
            "total_signals": sum(s.signals for s in states.values()),
            "campaigns_with_trades": sum(1 for s in states.values() if s.n_trades > 0),
            "total_pnl": round(sum(s.total_pnl for s in states.values()), 2),
        },
        "correlation": portfolio.correlation_matrix(),
        "high_corr": portfolio.high_correlation_pairs(0.7),
        "campaigns": {},
    }
    for st in ranked:
        c = st.cfg
        report["campaigns"][c["id"]] = {
            "strategy": c["strategy"], "symbol": c["symbol"], "tf": c["tf"],
            "param_idx": c["param_idx"], "trades": st.n_trades, "wins": st.qm.wins,
            "win_rate": round(st.win_rate, 1), "sharpe": round(st.sharpe, 2),
            "sortino": round(st.sortino, 2), "pf": round(st.pf, 2),
            "max_dd": round(st.qm.max_dd, 2), "pnl": round(st.total_pnl, 2),
            "signals": st.signals,
        }
    path = REPORTS_DIR / f"mega_v2_final_{ts}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n" + "=" * 80)
    print("MEGA V2 FINAL REPORT")
    print("=" * 80)
    s = report["summary"]
    print(f"  Total signals:     {s['total_signals']}")
    print(f"  Total trades:      {s['total_trades']}")
    print(f"  Active campaigns:  {s['campaigns_with_trades']}/{n_c}")
    print(f"  Total P&L:         ${s['total_pnl']:+,.2f}")
    print(f"  High correlation:  {report['high_corr'][:5]}")
    print()
    print(f"  {'ID':<35} {'S':<5} {'Y':<8} {'TF':<4} {'#T':>4} {'WR':>5} {'SH':>6} {'PF':>5} {'DD':>7} {'P&L':>10}")
    print("  " + "-" * 95)
    for st in ranked[:25]:
        c = st.cfg
        print(f"  {c['id']:<35} {c['strategy'][:4]:<5} {c['symbol'][:8]:<8} {c['tf']:<4} "
              f"{st.n_trades:>4} {st.win_rate:>4.0f}% {st.sharpe:>6.2f} {st.pf:>5.2f} "
              f"{st.qm.max_dd:>6.1f} ${st.total_pnl:>+9.2f}")
    print("\n  BOTTOM 10:")
    for st in ranked[-10:]:
        c = st.cfg
        print(f"  {c['id']:<35} {c['strategy'][:4]:<5} {c['symbol'][:8]:<8} {c['tf']:<4} "
              f"{st.n_trades:>4} {st.win_rate:>4.0f}% {st.sharpe:>6.2f} {st.pf:>5.2f} "
              f"{st.qm.max_dd:>6.1f} ${st.total_pnl:>+9.2f}")
    print("=" * 80)
    print(f"\n  Saved: {path}")


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=720)
    args = parser.parse_args()
    asyncio.run(main(args))

if __name__ == "__main__":
    run()
