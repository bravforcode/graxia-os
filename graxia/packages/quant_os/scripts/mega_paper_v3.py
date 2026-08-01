"""
MEGA PAPER TRADER V3 — FIX QUALITY + SCALE

Quality fixes:
  - Tighter SL/TP (1.5x/2.5x ATR)
  - Trailing stop (move to breakeven after 1x ATR profit)
  - Max hold period (prevent stuck trades)
  - Min trades gate (>= 10 for reporting)
  - Honest claims only

Scale:
  8 strategies x 6 params x 17 symbols x 5 timeframes = 4,080 campaigns

Usage:
    python scripts/mega_paper_v3.py --hours 720
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
MAX_HOLD_BARS = {"M15": 96, "M30": 48, "H1": 24, "H4": 20, "D1": 30}  # max hold per TF

SYMBOLS = [
    # Crypto
    "BTCUSD", "ETHUSD",
    # Metals
    "XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD",
    # Indices
    "NAS100", "US30",
    # FX
    "EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCAD", "USDCHF", "NZDUSD",
    # Energy
    "SpotCrude", "NatGas",
]

TIMEFRAMES = ["M15", "M30", "H1", "H4", "D1"]

SPREAD_BPS = {
    "BTCUSD": 2.43, "ETHUSD": 11.67, "XAUUSD": 0.36, "XAGUSD": 6.58,
    "XPTUSD": 3.0, "XPDUSD": 5.0, "NAS100": 1.0, "US30": 0.5,
    "EURUSD": 0.07, "GBPUSD": 0.15, "AUDUSD": 0.1, "USDJPY": 0.06,
    "USDCAD": 0.12, "USDCHF": 0.12, "NZDUSD": 0.15,
    "SpotCrude": 4.88, "NatGas": 3.0,
}

# Strategy param grids — 6 variations each
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
    # NEW strategies from backtest library
    "momentum": [
        {"fast_ma": 5, "slow_ma": 20, "atr_mult": 1.5},
        {"fast_ma": 8, "slow_ma": 21, "atr_mult": 2.0},
        {"fast_ma": 10, "slow_ma": 30, "atr_mult": 1.5},
        {"fast_ma": 5, "slow_ma": 50, "atr_mult": 2.0},
        {"fast_ma": 12, "slow_ma": 26, "atr_mult": 1.5},
        {"fast_ma": 8, "slow_ma": 34, "atr_mult": 2.0},
    ],
    "mean_rev": [
        {"z_period": 20, "entry_z": 2.0, "exit_z": 0.5},
        {"z_period": 30, "entry_z": 2.5, "exit_z": 0.5},
        {"z_period": 40, "entry_z": 3.0, "exit_z": 0.3},
        {"z_period": 15, "entry_z": 1.5, "exit_z": 0.3},
        {"z_period": 25, "entry_z": 2.0, "exit_z": 0.7},
        {"z_period": 50, "entry_z": 2.5, "exit_z": 0.5},
    ],
    "breakout_vol": [
        {"channel_period": 20, "vol_confirm_mult": 1.5, "atr_mult": 2.0},
        {"channel_period": 30, "vol_confirm_mult": 2.0, "atr_mult": 2.5},
        {"channel_period": 40, "vol_confirm_mult": 1.8, "atr_mult": 2.0},
        {"channel_period": 15, "vol_confirm_mult": 1.2, "atr_mult": 1.5},
        {"channel_period": 25, "vol_confirm_mult": 2.5, "atr_mult": 3.0},
        {"channel_period": 10, "vol_confirm_mult": 1.5, "atr_mult": 2.0},
    ],
}

LOG_DIR = _project_root / "logs" / "mega_v3"
REPORTS_DIR = _project_root / "reports" / "paper_engine"
MIN_TRADES_FOR_REPORT = 10  # don't report Sharpe/Sortino with fewer trades


def build_campaigns() -> list[dict]:
    campaigns = []
    cid = 0
    for strat, params_list in PARAM_GRIDS.items():
        for pi, params in enumerate(params_list):
            for symbol in SYMBOLS:
                for tf in TIMEFRAMES:
                    cid += 1
                    campaigns.append({
                        "id": f"{strat[:3]}_{symbol[:3].lower()}_{tf.lower()}_{pi+1}_{cid:05d}",
                        "strategy": strat, "symbol": symbol, "tf": tf,
                        "params": params, "param_idx": pi,
                    })
    return campaigns


# ── ATR ──────────────────────────────────────────────────────────
def _atr(h, l, c, period=14):
    n = len(c)
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
    atr = np.full(n, np.nan)
    if n >= period:
        atr[period] = np.mean(tr[1:period+1])
        for i in range(period+1, n):
            atr[i] = (atr[i-1]*(period-1)+tr[i])/period
    return atr


# ── Strategy signals ─────────────────────────────────────────────
def sig_donchian(c, h, l, p):
    per=p.get("period",20); vf=p.get("vol_filter",True); n=len(c)
    if n<per+2: return 0,0,0,""
    i=n-1; hh=np.max(h[i-per:i]); ll=np.min(l[i-per:i])
    atr=_atr(h,l,c)
    if np.isnan(atr[i]) or atr[i]<=0 or c[i]<=0: return 0,0,0,""
    ar=np.where(c>0,atr/c,0)
    med=np.nanmedian(ar[max(0,i-200):i]) if i>0 else 0
    ok=(atr[i]/c[i]>med*0.8) if vf and med>0 else True
    if c[i]>hh and ok: return 1, c[i]-atr[i]*1.5, c[i]+atr[i]*2.5, "D+"
    if c[i]<ll and ok: return -1, c[i]+atr[i]*1.5, c[i]-atr[i]*2.5, "D-"
    return 0,0,0,""


def sig_tsm(c, h, l, p):
    lbs=p.get("lookbacks",[20,40,60,120]); n=len(c)
    if n<max(lbs)+2: return 0,0,0,""
    i=n-1; atr=_atr(h,l,c)
    if np.isnan(atr[i]) or atr[i]<=0: return 0,0,0,""
    zs=[(c[i]-c[i-lb])/c[i-lb] if c[i-lb]>0 else 0 for lb in lbs]
    az=np.mean(zs)
    if az>0.5: return 1, c[i]-atr[i]*1.5, c[i]+atr[i]*2.5, f"T+ z={az:.2f}"
    if az<-0.5: return -1, c[i]+atr[i]*1.5, c[i]-atr[i]*2.5, f"T- z={az:.2f}"
    return 0,0,0,""


def sig_rsi_bb(c, h, l, p):
    rp=p.get("rsi_period",14); ros=p.get("rsi_oversold",30); rob=p.get("rsi_overbought",70)
    bbp=p.get("bb_period",20); bbs=p.get("bb_std",2.0); n=len(c)
    if n<max(rp,bbp)+2: return 0,0,0,""
    i=n-1
    d=np.diff(c); g=np.where(d>0,d,0.0); ls=np.where(d<0,-d,0.0)
    ag=np.mean(g[:rp]) if len(g)>=rp else 0; al=np.mean(ls[:rp]) if len(ls)>=rp else 0
    for j in range(rp,min(i,len(d))):
        ag=(ag*(rp-1)+g[j])/rp; al=(al*(rp-1)+ls[j])/rp
    rsi=100-100/(1+ag/(al+1e-10)) if al>0 else 100
    w=c[i-bbp+1:i+1] if i>=bbp else c[:i+1]
    mu=np.mean(w); sig=np.std(w,ddof=1) if len(w)>1 else 0
    lo=mu-bbs*sig; up=mu+bbs*sig
    atr=_atr(h,l,c)
    if np.isnan(atr[i]) or atr[i]<=0: return 0,0,0,""
    if rsi<ros and c[i]<=lo: return 1, c[i]-atr[i]*1.5, c[i]+atr[i]*2, f"R+ {rsi:.0f}"
    if rsi>rob and c[i]>=up: return -1, c[i]+atr[i]*1.5, c[i]-atr[i]*2, f"R- {rsi:.0f}"
    return 0,0,0,""


def sig_mrb(c, h, l, p):
    lb=p.get("lookback",20); ez=p.get("entry_z",2.0); n=len(c)
    if n<lb+2: return 0,0,0,""
    i=n-1; w=c[i-lb:i]; mu=np.mean(w); sd=np.std(w,ddof=1)
    if sd<1e-10: return 0,0,0,""
    z=(c[i]-mu)/sd
    atr=_atr(h,l,c)
    if np.isnan(atr[i]) or atr[i]<=0: return 0,0,0,""
    if z<-ez: return 1, c[i]-atr[i]*1.5, c[i]+atr[i]*2, f"M+ z={z:.2f}"
    if z>ez: return -1, c[i]+atr[i]*1.5, c[i]-atr[i]*2, f"M- z={z:.2f}"
    return 0,0,0,""


def sig_vb(c, h, l, p):
    vp=p.get("vol_period",20); vm=p.get("vol_mult",2.0); lb=p.get("lookback",20); n=len(c)
    if n<max(vp,lb)+2: return 0,0,0,""
    i=n-1; ranges=h-l; vma=np.mean(ranges[i-vp:i])
    if vma<=0: return 0,0,0,""
    if ranges[i]<=vma*vm: return 0,0,0,""
    hh=np.max(h[i-lb:i]); ll=np.min(l[i-lb:i])
    atr=_atr(h,l,c)
    if np.isnan(atr[i]) or atr[i]<=0: return 0,0,0,""
    if c[i]>hh: return 1, c[i]-atr[i]*1.5, c[i]+atr[i]*2.5, "V+"
    if c[i]<ll: return -1, c[i]+atr[i]*1.5, c[i]-atr[i]*2.5, "V-"
    return 0,0,0,""


def sig_momentum(c, h, l, p):
    fast=p.get("fast_ma",8); slow=p.get("slow_ma",21); n=len(c)
    if n<slow+2: return 0,0,0,""
    i=n-1
    ma_fast=np.mean(c[i-fast+1:i+1])
    ma_slow=np.mean(c[i-slow+1:i+1])
    ma_fast_prev=np.mean(c[i-fast:i+1]) if i>=fast else ma_fast
    ma_slow_prev=np.mean(c[i-slow:i]) if i>=slow else ma_slow
    atr=_atr(h,l,c)
    if np.isnan(atr[i]) or atr[i]<=0: return 0,0,0,""
    # Crossover long
    if ma_fast>ma_slow and ma_fast_prev<=ma_slow_prev:
        return 1, c[i]-atr[i]*1.5, c[i]+atr[i]*2.5, f"MO+ fast={fast} slow={slow}"
    # Crossover short
    if ma_fast<ma_slow and ma_fast_prev>=ma_slow_prev:
        return -1, c[i]+atr[i]*1.5, c[i]-atr[i]*2.5, f"MO- fast={fast} slow={slow}"
    return 0,0,0,""


def sig_mean_rev(c, h, l, p):
    zp=p.get("z_period",20); ez=p.get("entry_z",2.0); n=len(c)
    if n<zp+2: return 0,0,0,""
    i=n-1; w=c[i-zp:i]; mu=np.mean(w); sd=np.std(w,ddof=1)
    if sd<1e-10: return 0,0,0,""
    z=(c[i]-mu)/sd
    atr=_atr(h,l,c)
    if np.isnan(atr[i]) or atr[i]<=0: return 0,0,0,""
    if z<-ez: return 1, c[i]-atr[i]*1.5, c[i]+atr[i]*2, f"MR+ z={z:.2f}"
    if z>ez: return -1, c[i]+atr[i]*1.5, c[i]-atr[i]*2, f"MR- z={z:.2f}"
    return 0,0,0,""


def sig_breakout_vol(c, h, l, p):
    cp=p.get("channel_period",20); vm=p.get("vol_confirm_mult",1.5); n=len(c)
    if n<cp+2: return 0,0,0,""
    i=n-1
    hh=np.max(h[i-cp:i]); ll=np.min(l[i-cp:i])
    rng=h-l; vma=np.mean(rng[i-cp:i]) if i>=cp else np.mean(rng[:i])
    vol_ok=rng[i]>vma*vm if vma>0 else False
    atr=_atr(h,l,c)
    if np.isnan(atr[i]) or atr[i]<=0: return 0,0,0,""
    if c[i]>hh and vol_ok: return 1, c[i]-atr[i]*1.5, c[i]+atr[i]*2.5, f"BV+"
    if c[i]<ll and vol_ok: return -1, c[i]+atr[i]*1.5, c[i]-atr[i]*2.5, f"BV-"
    return 0,0,0,""


SIGS = {
    "donchian": sig_donchian, "tsm": sig_tsm, "rsi_bb": sig_rsi_bb,
    "mrb": sig_mrb, "volume_breakout": sig_vb,
    "momentum": sig_momentum, "mean_rev": sig_mean_rev, "breakout_vol": sig_breakout_vol,
}


# ── Quality metrics ──────────────────────────────────────────────
@dataclass
class QM:
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
    def wr(self): return self.wins / self.n * 100 if self.n > 0 else 0
    @property
    def pf(self):
        gp = sum(p for p in self.pnls if p > 0)
        gl = abs(sum(p for p in self.pnls if p <= 0))
        return gp / gl if gl > 0 else 0
    @property
    def sharpe(self):
        if self.n < MIN_TRADES_FOR_REPORT: return None  # HONEST: not enough data
        a = np.array(self.pnls); m = np.mean(a); s = np.std(a)
        return round(float(m / s * np.sqrt(252)), 2) if s > 1e-10 else 0
    @property
    def sortino(self):
        if self.n < MIN_TRADES_FOR_REPORT: return None
        neg = [p for p in self.pnls if p < 0]
        if not neg: return None
        ds = float(np.std(neg))
        return round(float(np.mean(self.pnls) / ds * np.sqrt(252)), 2) if ds > 1e-10 else 0


# ── Campaign state ───────────────────────────────────────────────
@dataclass
class CS:
    cfg: dict
    ot: dict | None = None  # open trade
    qm: QM = field(default_factory=QM)
    lbt: int = 0  # last bar time
    holding_bars: int = 0  # bars in current trade
    sigs: int = 0
    cap: float = VIRTUAL_CAPITAL


# ── Portfolio ────────────────────────────────────────────────────
class Portfolio:
    def __init__(self):
        self.sym_pnl: dict[str, list[float]] = defaultdict(list)

    def record(self, sym: str, pnl: float):
        self.sym_pnl[sym].append(pnl)

    def corr_matrix(self) -> dict:
        syms = [s for s, v in self.sym_pnl.items() if len(v) >= 10]
        if len(syms) < 2: return {}
        ml = min(len(self.sym_pnl[s]) for s in syms)
        data = np.array([self.sym_pnl[s][-ml:] for s in syms])
        corr = np.corrcoef(data)
        return {f"{s1}/{s2}": round(float(corr[i,j]), 3)
                for i, s1 in enumerate(syms) for j, s2 in enumerate(syms) if i < j}

    def high_corr(self, threshold=0.7) -> list[str]:
        return [k for k, v in self.corr_matrix().items() if abs(v) > threshold]


# ── Main ─────────────────────────────────────────────────────────
async def main(args):
    import MetaTrader5 as mt5
    if not mt5.initialize():
        mt5.initialize(path=r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe")
    account = mt5.account_info()

    tf_const = {}
    for tf_name in TIMEFRAMES:
        tf_const[tf_name] = getattr(mt5, f"TIMEFRAME_{tf_name}")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    campaigns = build_campaigns()
    states = {c["id"]: CS(cfg=c) for c in campaigns}
    portfolio = Portfolio()
    daily_done = -1

    def fetch_all():
        data = {}
        for tf in TIMEFRAMES:
            data[tf] = {}
            tf_c = tf_const[tf]
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

    nc = len(campaigns)
    print("=" * 80)
    print("MEGA PAPER TRADER V3 — FIX QUALITY + SCALE")
    print("=" * 80)
    print(f"  Campaigns:  {nc}")
    print(f"  Strategies: {len(PARAM_GRIDS)} (donchian, tsm, rsi_bb, mrb, vb, momentum, mean_rev, bv)")
    print(f"  Params:     {sum(len(v) for v in PARAM_GRIDS.values())} ({sum(len(v) for v in PARAM_GRIDS.values())//len(PARAM_GRIDS)} per strategy)")
    print(f"  Symbols:    {len(SYMBOLS)} (crypto, metals, indices, fx, energy)")
    print(f"  Timeframes: {len(TIMEFRAMES)} ({', '.join(TIMEFRAMES)})")
    print(f"  Capital:    ${VIRTUAL_CAPITAL}/campaign (${VIRTUAL_CAPITAL*nc:,.0f} virtual)")
    print(f"  Duration:   {args.hours}h ({args.hours/24:.0f} days)")
    print(f"  Account:    {account.server} #{account.login} (${account.balance:,.0f})")
    print(f"  Quality:    SL=1.5xATR TP=2.5xATR, trailing stop, max hold, min {MIN_TRADES_FOR_REPORT} trades for reporting")
    print(f"  Claims:     Sharpe/Sortino only after {MIN_TRADES_FOR_REPORT}+ trades. No extrapolation.")
    print()

    end_time = datetime.now(UTC) + timedelta(hours=args.hours)
    cycle = 0
    start_ts = datetime.now(UTC).isoformat()

    try:
        while datetime.now(UTC) < end_time:
            cycle += 1
            now = datetime.now(UTC)
            tf_data = fetch_all()
            sigs_t = 0; trades_t = 0

            for c in campaigns:
                cid = c["id"]
                st = states[cid]
                sym = c["symbol"]
                tf = c["tf"]
                if sym not in tf_data.get(tf, {}): continue
                d = tf_data[tf][sym]
                bt = d["bt"]; ca = d["c"]; ha = d["h"]; la = d["l"]

                # --- SL/TP/Trailing/Time-exit ---
                if st.ot:
                    tick = mt5.symbol_info_tick(sym)
                    if tick:
                        cur = tick.bid if st.ot["d"] == 1 else tick.ask
                        ot = st.ot
                        st.holding_bars += 1

                        # Trailing stop: move SL to breakeven after 1 ATR profit
                        if ot.get("trail_active") is None:
                            atr_val = abs(ot["tp"] - ot["e"]) / 2.5  # reverse-engineer ATR
                            if ot["d"] == 1 and cur >= ot["e"] + atr_val:
                                ot["sl"] = ot["e"]  # breakeven
                                ot["trail_active"] = True
                            elif ot["d"] == -1 and cur <= ot["e"] - atr_val:
                                ot["sl"] = ot["e"]
                                ot["trail_active"] = True

                        # Check exit conditions
                        hit_sl = (ot["d"]==1 and cur<=ot["sl"]) or (ot["d"]==-1 and cur>=ot["sl"])
                        hit_tp = (ot["d"]==1 and cur>=ot["tp"]) or (ot["d"]==-1 and cur<=ot["tp"])
                        max_hold = st.holding_bars >= MAX_HOLD_BARS.get(tf, 24)

                        if hit_sl or hit_tp or max_hold:
                            if hit_tp:
                                ep = ot["tp"]; reason = "TP"
                            elif hit_sl:
                                ep = ot["sl"]; reason = "SL"
                            else:
                                ep = cur; reason = "TIME"
                            sc = ep * ot["sz"] * SPREAD_BPS.get(sym, 1) / 10000 * 2
                            pnl = ((ep-ot["e"])*ot["sz"] if ot["d"]==1 else (ot["e"]-ep)*ot["sz"]) - sc
                            st.qm.add(round(pnl, 4))
                            portfolio.record(sym, pnl)
                            st.ot = None
                            st.holding_bars = 0
                            trades_t += 1

                # --- Signal on new bar ---
                if bt != st.lbt:
                    st.lbt = bt
                    sig_fn = SIGS[c["strategy"]]
                    dirc, sl, tp, reason = sig_fn(ca, ha, la, c["params"])

                    if dirc != 0 and st.ot is None:
                        st.sigs += 1; sigs_t += 1
                        entry = ca[-1]
                        sd = abs(entry - sl)
                        min_sd = entry * 0.005
                        if sd < min_sd:
                            sd = min_sd
                            sl = entry - sd if dirc == 1 else entry + sd
                            tp = entry + sd*2.5 if dirc == 1 else entry - sd*2.5
                        rd = st.cap * RISK_PCT / 100
                        sz = rd / sd
                        ms = st.cap * 0.05 / entry if entry > 0 else 0
                        if ms > 0 and sz > ms: sz = ms
                        st.ot = {"d": dirc, "e": entry, "sl": sl, "tp": tp, "sz": sz, "trail_active": None}
                        st.holding_bars = 0

            # Progress
            if cycle % 10 == 0:
                tot_t = sum(s.qm.n for s in states.values())
                tot_s = sum(s.sigs for s in states.values())
                tot_pnl = sum(s.qm.equity for s in states.values())
                opn = sum(1 for s in states.values() if s.ot)
                elapsed = (now - datetime.fromisoformat(start_ts).replace(tzinfo=UTC)).total_seconds() / 3600

                # Count campaigns with enough data for reporting
                reportable = sum(1 for s in states.values() if s.qm.n >= MIN_TRADES_FOR_REPORT)
                profitable = sum(1 for s in states.values() if s.qm.n >= MIN_TRADES_FOR_REPORT and s.qm.equity > 0)

                print(f"\n  [{now.strftime('%H:%M')}] cycle={cycle} sigs={tot_s} trades={tot_t} "
                      f"open={opn} pnl=${tot_pnl:+,.1f} elapsed={elapsed:.1f}h")
                print(f"    reportable(>={MIN_TRADES_FOR_REPORT} trades): {reportable}/{nc} | profitable: {profitable}/{reportable if reportable else 1}")

                # Best reportable
                best_r = max((s for s in states.values() if s.qm.n >= MIN_TRADES_FOR_REPORT),
                             key=lambda s: s.qm.equity, default=None)
                if best_r:
                    print(f"    best reportable: {best_r.cfg['id'][:30]} pnl=${best_r.qm.equity:+.2f} sharpe={best_r.qm.sharpe}")

            # Daily report at midnight
            if now.hour == 0 and now.minute < 2 and daily_done != now.day:
                daily_done = now.day
                _daily(states, portfolio, cycle, start_ts, nc)

            # Checkpoint
            if cycle % 100 == 0:
                _ckpt(states, portfolio, cycle, start_ts, args.hours, nc)

            await asyncio.sleep(CHECK_SEC)

    except KeyboardInterrupt:
        print("\n\nStopping...")
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        # Close open
        for cid, st in states.items():
            if st.ot:
                ot = st.ot; sym = st.cfg["symbol"]
                tick = mt5.symbol_info_tick(sym)
                cur = tick.bid if ot["d"]==1 else (tick.ask if tick else ot["e"])
                sc = cur*ot["sz"]*SPREAD_BPS.get(sym,1)/10000*2
                pnl = ((cur-ot["e"])*ot["sz"] if ot["d"]==1 else (ot["e"]-cur)*ot["sz"]) - sc
                st.qm.add(round(pnl, 4))
                st.ot = None
        mt5.shutdown()
        _final(states, portfolio, start_ts, args.hours, nc)


def _daily(states, portfolio, cycle, start_ts, nc):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d")
    reportable = sorted(
        [s for s in states.values() if s.qm.n >= MIN_TRADES_FOR_REPORT],
        key=lambda s: s.qm.equity, reverse=True
    )
    report = {
        "date": ts, "cycle": cycle, "total": nc,
        "reportable": len(reportable),
        "profitable": sum(1 for s in reportable if s.qm.equity > 0),
        "total_trades": sum(s.qm.n for s in states.values()),
        "total_pnl": round(sum(s.qm.equity for s in states.values()), 2),
        "high_corr": portfolio.high_corr(0.7),
        "top_10": [{"id": s.cfg["id"][:35], "s": s.cfg["strategy"],
                     "y": s.cfg["symbol"], "tf": s.cfg["tf"],
                     "n": s.qm.n, "wr": round(s.qm.wr, 1),
                     "sh": s.qm.sharpe, "pnl": round(s.qm.equity, 2)}
                    for s in reportable[:10]],
    }
    path = REPORTS_DIR / f"mega_v3_daily_{ts}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n  DAILY: {report['reportable']} reportable, {report['profitable']} profitable, "
          f"{report['total_trades']} trades, ${report['total_pnl']:+,.1f}")


def _ckpt(states, portfolio, cycle, start_ts, hours, nc):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    data = {}
    for cid, st in states.items():
        if st.sigs > 0 or st.qm.n > 0:
            data[cid] = {
                "s": st.cfg["strategy"], "y": st.cfg["symbol"], "tf": st.cfg["tf"],
                "pi": st.cfg["param_idx"],
                "n": st.qm.n, "w": st.qm.wins, "wr": round(st.qm.wr, 1),
                "sh": st.qm.sharpe, "so": st.qm.sortino,
                "pf": round(st.qm.pf, 2), "dd": round(st.qm.max_dd, 2),
                "pnl": round(st.qm.equity, 2), "sig": st.sigs,
            }
    path = REPORTS_DIR / f"mega_v3_ckpt_{ts}.json"
    path.write_text(json.dumps({"cycle": cycle, "n": len(data), "campaigns": data,
                                 "high_corr": portfolio.high_corr(0.7)}, indent=2), encoding="utf-8")
    print(f"  Checkpoint: {len(data)} active")


def _final(states, portfolio, start_ts, hours, nc):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    ranked = sorted(states.values(), key=lambda s: s.qm.equity, reverse=True)
    reportable = [s for s in ranked if s.qm.n >= MIN_TRADES_FOR_REPORT]

    report = {
        "start": start_ts, "end": datetime.now(UTC).isoformat(),
        "hours": hours, "n_campaigns": nc,
        "disclaimer": "PAPER TRADING RESULTS. Not live. Past performance does not guarantee future results.",
        "min_trades_for_report": MIN_TRADES_FOR_REPORT,
        "summary": {
            "total_signals": sum(s.sigs for s in states.values()),
            "total_trades": sum(s.qm.n for s in states.values()),
            "reportable_campaigns": len(reportable),
            "profitable_reportable": sum(1 for s in reportable if s.qm.equity > 0),
            "total_pnl_virtual": round(sum(s.qm.equity for s in states.values()), 2),
        },
        "high_corr": portfolio.high_corr(0.7),
        "reportable_campaigns": {},
    }
    for st in reportable:
        c = st.cfg
        report["reportable_campaigns"][c["id"]] = {
            "strategy": c["strategy"], "symbol": c["symbol"], "tf": c["tf"],
            "param_idx": c["param_idx"],
            "trades": st.qm.n, "wins": st.qm.wins, "win_rate": round(st.qm.wr, 1),
            "sharpe": st.qm.sharpe, "sortino": st.qm.sortino,
            "profit_factor": round(st.qm.pf, 2), "max_dd": round(st.qm.max_dd, 2),
            "pnl": round(st.qm.equity, 2), "signals": st.sigs,
        }
    path = REPORTS_DIR / f"mega_v3_final_{ts}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n" + "=" * 80)
    print("MEGA V3 FINAL — VERIFIED DATA ONLY")
    print("=" * 80)
    print(f"  DISCLAIMER: PAPER TRADING. Not live. No guarantees.")
    s = report["summary"]
    print(f"  Total signals:     {s['total_signals']}")
    print(f"  Total trades:      {s['total_trades']}")
    print(f"  Reportable (>{MIN_TRADES_FOR_REPORT} trades): {s['reportable_campaigns']}")
    print(f"  Profitable:        {s['profitable_reportable']}")
    print(f"  Virtual P&L:       ${s['total_pnl_virtual']:+,.2f}")
    if reportable:
        print(f"\n  TOP 20 (>{MIN_TRADES_FOR_REPORT} trades, VERIFIED):")
        print(f"  {'ID':<35} {'S':<5} {'Y':<8} {'TF':<4} {'#T':>4} {'WR':>5} {'SH':>6} {'PF':>5} {'DD':>7} {'P&L':>10}")
        print("  " + "-" * 95)
        for st in reportable[:20]:
            c = st.cfg
            print(f"  {c['id']:<35} {c['strategy'][:4]:<5} {c['symbol'][:8]:<8} {c['tf']:<4} "
                  f"{st.qm.n:>4} {st.qm.wr:>4.0f}% {st.qm.sharpe or 'N/A':>6} {st.qm.pf:>5.2f} "
                  f"{st.qm.max_dd:>6.1f} ${st.qm.equity:>+9.2f}")
    else:
        print(f"\n  NO CAMPAIGNS YET REACH {MIN_TRADES_FOR_REPORT} TRADES — need more time")
    print("=" * 80)
    print(f"  Saved: {path}")


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=720)
    args = parser.parse_args()
    asyncio.run(main(args))

if __name__ == "__main__":
    run()
