#!/usr/bin/env python3
"""
Comprehensive Edge Search — 4-pronged approach.

1. Validate TSM ensemble + Donchian on sacred holdout data
2. Tune Vol Risk Premium parameters (grid search)
3. Build ensemble from best strategies
4. Search new instrument/strategy combinations

Usage:
    python scripts/comprehensive_edge_search.py
    python scripts/comprehensive_edge_search.py --prong holdout
    python scripts/comprehensive_edge_search.py --prong vrp_tune
    python scripts/comprehensive_edge_search.py --prong ensemble
    python scripts/comprehensive_edge_search.py --prong new_search
"""

import argparse
import json
import sys
import warnings
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr,attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr,attr-defined]

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))

REPORT_PATH = ROOT / "reports" / "comprehensive_edge_search.json"

sys.path.insert(0, str(ROOT))
from paper_engine.campaign import get_round_trip_cost_bps  # noqa: E402
from provenance import cost_calibrated_symbols, require_cost_calibrated  # noqa: E402

require_cost_calibrated("XAUUSD", mode="paper")
XAU_COST_BPS = get_round_trip_cost_bps("XAUUSD")  # real measured round-trip cost, replaces the old flat 10bps guess

# ─── Setup package imports ──────────────────────────────────────────────


def _setup():
    import types

    if "quant_os" not in sys.modules:
        pkg = types.ModuleType("quant_os")
        pkg.__path__ = [str(ROOT)]
        pkg.__package__ = "quant_os"
        sys.modules["quant_os"] = pkg
    for sub in ["strategies", "core", "ml"]:
        if f"quant_os.{sub}" not in sys.modules:
            mod = types.ModuleType(f"quant_os.{sub}")
            mod.__path__ = [str(ROOT / sub)]
            mod.__package__ = f"quant_os.{sub}"
            sys.modules[f"quant_os.{sub}"] = mod


_setup()

# ─── Helpers ────────────────────────────────────────────────────────────


def sharpe(returns):
    if len(returns) < 2:
        return 0.0
    r = np.array(returns)
    m, s = np.mean(r), np.std(r, ddof=1)
    return (m / s) * np.sqrt(252) if s > 1e-10 else 0.0


def max_dd(equity):
    if len(equity) == 0:
        return 0.0
    peak = equity[0]
    mdd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0
        mdd = max(mdd, dd)
    return mdd


def simulate(signal, close, cost_bps):
    """Simulate trades from signal series. Returns list of per-trade PnL.

    2026-07-30: cost_bps used to default to a flat 10bps for every symbol.
    Now required explicitly at each call site -- real measured spread
    (get_round_trip_cost_bps) for XAUUSD, per-symbol for the new_search scan, so a
    caller can't silently fall back to the old flat guess.
    """
    trades = []
    pos = 0
    entry = 0.0
    sig = signal.values
    px = close.values
    for i in range(len(sig)):
        s = int(sig[i]) if not pd.isna(sig[i]) else 0
        c = float(px[i])
        if s != pos:
            if pos != 0:
                pnl = pos * (c - entry) / entry - cost_bps / 10000
                trades.append(pnl)
            if s != 0:
                entry = c
            pos = s
    if pos != 0 and len(px) > 0:
        pnl = pos * (float(px[-1]) - entry) / entry - cost_bps / 10000
        trades.append(pnl)
    return trades


def load_csv(symbol, tf):
    p = ROOT / "data" / f"{symbol}_{tf}.csv"
    df = pd.read_csv(p)
    df["timestamp"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("timestamp").sort_index()
    return df


# ═══════════════════════════════════════════════════════════════════════
# PRONG 1: Sacred Holdout Validation
# ═══════════════════════════════════════════════════════════════════════


def prong_holdout():
    """Validate TSM ensemble on sacred holdout data (never seen before)."""
    print("\n" + "=" * 60)
    print("  PRONG 1: Sacred Holdout Validation")
    print("=" * 60)

    # Load holdout
    h = pd.read_csv(ROOT / "data" / "sacred_holdout" / "holdout.csv")
    h["date"] = pd.to_datetime(h["date"], utc=True)
    h = h.set_index("date").sort_index()

    close = h["xau_close"]
    high = h["xau_high"]
    low = h["xau_low"]
    dxy = h["dxy_close"]
    dfii10 = h["dfii10"]

    print(f"  Holdout period: {close.index[0].date()} to {close.index[-1].date()}")
    print(f"  Data points: {len(close)}")
    print(f"  Price range: ${close.min():.0f} - ${close.max():.0f}")

    results = {}

    # --- TSM Ensemble (equal-weight vol-scaled) ---
    print("\n  > TSM Ensemble (lookbacks [20,40,60,120])...")
    returns = close.pct_change()
    lookbacks = [20, 40, 60, 120]
    weights = [0.25, 0.25, 0.25, 0.25]

    signals = []
    for lb in lookbacks:
        r_sum = returns.rolling(lb).sum()
        r_vol = returns.rolling(lb).std()
        sig = r_sum / r_vol.replace(0, np.nan)
        signals.append(sig)

    tsm_signal = sum(w * s for w, s in zip(weights, signals, strict=False))
    tsm_dir = np.sign(tsm_signal)
    tsm_trades = simulate(tsm_dir, close, cost_bps=XAU_COST_BPS)
    results["tsm_ensemble"] = {
        "trades": len(tsm_trades),
        "sharpe": round(sharpe(tsm_trades), 4),
        "win_rate": round(sum(1 for t in tsm_trades if t > 0) / max(len(tsm_trades), 1), 4),
        "total_pnl": round(sum(tsm_trades), 6),
    }
    print(
        f"    Trades: {len(tsm_trades)}, Sharpe: {results['tsm_ensemble']['sharpe']}, "
        f"WR: {results['tsm_ensemble']['win_rate']:.1%}"
    )

    # --- TSM + DXY divergence filter ---
    print("\n  > TSM + DXY Divergence Filter...")
    dxy_ret = dxy.pct_change()
    # When gold rises and DXY falls → stronger signal
    divergence = np.sign(returns) * (-np.sign(dxy_ret))
    div_filtered = tsm_dir.copy()
    div_filtered[divergence < 0] = 0  # filter out gold-up/DXY-up periods
    div_trades = simulate(div_filtered, close, cost_bps=XAU_COST_BPS)
    results["tsm_dxy_divergence"] = {
        "trades": len(div_trades),
        "sharpe": round(sharpe(div_trades), 4),
        "win_rate": round(sum(1 for t in div_trades if t > 0) / max(len(div_trades), 1), 4),
        "total_pnl": round(sum(div_trades), 6),
    }
    print(
        f"    Trades: {len(div_trades)}, Sharpe: {results['tsm_dxy_divergence']['sharpe']}, "
        f"WR: {results['tsm_dxy_divergence']['win_rate']:.1%}"
    )

    # --- Real yield regime ---
    print("\n  > Real Yield Regime (DFII10)...")
    # Rising real yields → bearish gold, falling → bullish
    dfii10_chg = dfii10.diff(5)  # 5-day change
    ry_signal = pd.Series(0, index=close.index)
    ry_signal[dfii10_chg < -0.05] = 1  # falling yields → long gold
    ry_signal[dfii10_chg > 0.05] = -1  # rising yields → short gold
    ry_trades = simulate(ry_signal, close, cost_bps=XAU_COST_BPS)
    results["real_yield_regime"] = {
        "trades": len(ry_trades),
        "sharpe": round(sharpe(ry_trades), 4),
        "win_rate": round(sum(1 for t in ry_trades if t > 0) / max(len(ry_trades), 1), 4),
        "total_pnl": round(sum(ry_trades), 6),
    }
    print(
        f"    Trades: {len(ry_trades)}, Sharpe: {results['real_yield_regime']['sharpe']}, "
        f"WR: {results['real_yield_regime']['win_rate']:.1%}"
    )

    # --- Donchian Channel Breakout ---
    print("\n  > Donchian Channel Breakout (20-bar)...")
    period = 20
    don_high = high.rolling(period).max().shift(1)
    don_low = low.rolling(period).min().shift(1)
    don_sig = pd.Series(0, index=close.index)
    don_sig[close > don_high] = 1
    don_sig[close < don_low] = -1
    # State machine
    pos = 0
    don_final = pd.Series(0, index=close.index)
    for i in range(len(close)):
        s = don_sig.iloc[i]
        if s != pos:
            pos = s
        don_final.iloc[i] = pos
    don_trades = simulate(don_final, close, cost_bps=XAU_COST_BPS)
    results["donchian_20"] = {
        "trades": len(don_trades),
        "sharpe": round(sharpe(don_trades), 4),
        "win_rate": round(sum(1 for t in don_trades if t > 0) / max(len(don_trades), 1), 4),
        "total_pnl": round(sum(don_trades), 6),
    }
    print(
        f"    Trades: {len(don_trades)}, Sharpe: {results['donchian_20']['sharpe']}, "
        f"WR: {results['donchian_20']['win_rate']:.1%}"
    )

    # --- Donchian + Vol filter ---
    print("\n  > Donchian + Vol Filter (low vol = breakout)...")
    vol20 = returns.rolling(20).std()
    vol_pctile = vol20.rolling(100).rank(pct=True)
    don_vol_sig = don_final.copy()
    don_vol_sig[vol_pctile > 0.7] = 0  # skip high-vol breakouts
    don_vol_trades = simulate(don_vol_sig, close, cost_bps=XAU_COST_BPS)
    results["donchian_vol_filter"] = {
        "trades": len(don_vol_trades),
        "sharpe": round(sharpe(don_vol_trades), 4),
        "win_rate": round(sum(1 for t in don_vol_trades if t > 0) / max(len(don_vol_trades), 1), 4),
        "total_pnl": round(sum(don_vol_trades), 6),
    }
    print(
        f"    Trades: {len(don_vol_trades)}, Sharpe: {results['donchian_vol_filter']['sharpe']}, "
        f"WR: {results['donchian_vol_filter']['win_rate']:.1%}"
    )

    # --- VRP on holdout ---
    print("\n  > Vol Risk Premium on holdout...")
    from quant_os.strategies.vol_risk_premium import compute_vol_risk_premium_signals

    try:
        gvz_full = pd.read_parquet(ROOT / "data" / "macro" / "yf_GVZCLS.parquet")
        # Align GVZ to holdout dates
        gvz_idx = gvz_full.index.tz_localize("UTC") if gvz_full.index.tz is None else gvz_full.index
        gvz_full.index = gvz_idx
        gvz_holdout = gvz_full.reindex(close.index).ffill().bfill()
        if "gvz" in gvz_holdout.columns:
            gvz_holdout = gvz_holdout["gvz"]
        elif len(gvz_holdout.columns) > 0:
            gvz_holdout = gvz_holdout.iloc[:, 0]
    except Exception:
        gvz_holdout = None

    vrp_result = compute_vol_risk_premium_signals(close, gvz_holdout)
    vrp_trades = simulate(vrp_result.signal, close, cost_bps=XAU_COST_BPS)
    results["vrp_holdout"] = {
        "trades": len(vrp_trades),
        "sharpe": round(sharpe(vrp_trades), 4),
        "win_rate": round(sum(1 for t in vrp_trades if t > 0) / max(len(vrp_trades), 1), 4),
        "total_pnl": round(sum(vrp_trades), 6),
    }
    print(
        f"    Trades: {len(vrp_trades)}, Sharpe: {results['vrp_holdout']['sharpe']}, "
        f"WR: {results['vrp_holdout']['win_rate']:.1%}"
    )

    return results


# ═══════════════════════════════════════════════════════════════════════
# PRONG 2: VRP Parameter Tuning
# ═══════════════════════════════════════════════════════════════════════


def prong_vrp_tune():
    """Grid search VRP parameters on full XAUUSD data."""
    print("\n" + "=" * 60)
    print("  PRONG 2: VRP Parameter Tuning")
    print("=" * 60)

    from quant_os.strategies.vol_risk_premium import VolRiskPremiumConfig, compute_vol_risk_premium_signals

    df = load_csv("XAUUSD", "D1")
    close = df["close"]
    try:
        gvz = pd.read_parquet(ROOT / "data" / "macro" / "yf_GVZCLS.parquet")
        if gvz.index.tz is None:
            gvz.index = gvz.index.tz_localize("UTC")
        if "gvz" in gvz.columns:
            gvz = gvz["gvz"]
        elif len(gvz.columns) > 0:
            gvz = gvz.iloc[:, 0]
    except Exception:
        print("  No GVZ data, using realized vol proxy")
        gvz = None

    # Grid search
    param_grid = {
        "entry_z": [0.5, 1.0, 1.5, 2.0, 2.5],
        "exit_z": [0.0, 0.3, 0.5, 0.8, 1.0],
        "vrp_lookback": [10, 20, 30, 50],
        "regime_threshold": [0.0, 0.02, 0.05],
    }

    best_sharpe = -999
    best_params = {}
    best_result = None
    all_results = []

    total = (
        len(param_grid["entry_z"])
        * len(param_grid["exit_z"])
        * len(param_grid["vrp_lookback"])
        * len(param_grid["regime_threshold"])
    )

    print(f"  Grid: {total} combinations")
    count = 0

    for entry_z in param_grid["entry_z"]:
        for exit_z in param_grid["exit_z"]:
            for vrp_lb in param_grid["vrp_lookback"]:
                for regime_th in param_grid["regime_threshold"]:
                    count += 1
                    config = VolRiskPremiumConfig(
                        entry_z=entry_z,
                        exit_z=exit_z,
                        vrp_lookback=vrp_lb,
                        regime_threshold=regime_th,
                    )
                    try:
                        result = compute_vol_risk_premium_signals(close, gvz, config)
                        trades = simulate(result.signal, close, cost_bps=XAU_COST_BPS)
                        s = sharpe(trades)
                        n = len(trades)
                        wr = sum(1 for t in trades if t > 0) / max(n, 1)

                        all_results.append(
                            {
                                "entry_z": entry_z,
                                "exit_z": exit_z,
                                "vrp_lookback": vrp_lb,
                                "regime_threshold": regime_th,
                                "sharpe": round(s, 4),
                                "trades": n,
                                "win_rate": round(wr, 4),
                            }
                        )

                        if s > best_sharpe and n >= 50:
                            best_sharpe = s
                            best_params = {
                                "entry_z": entry_z,
                                "exit_z": exit_z,
                                "vrp_lookback": vrp_lb,
                                "regime_threshold": regime_th,
                            }
                            best_result = all_results[-1]
                    except Exception:
                        continue

                    if count % 100 == 0:
                        print(f"    {count}/{total}...")

    print(f"\n  Best VRP: Sharpe={best_sharpe:.4f}, Params={best_params}")
    if best_result:
        print(f"    Trades={best_result['trades']}, WR={best_result['win_rate']:.1%}")

    # Top 10
    sorted_results = sorted(all_results, key=lambda x: x["sharpe"], reverse=True)
    print("\n  Top 10 VRP configurations:")
    for i, r in enumerate(sorted_results[:10]):
        print(
            f"    {i + 1}. Sharpe={r['sharpe']:.4f} WR={r['win_rate']:.1%} "
            f"Trades={r['trades']} entry_z={r['entry_z']} exit_z={r['exit_z']} "
            f"lb={r['vrp_lookback']} regime={r['regime_threshold']}"
        )

    return {"best_params": best_params, "best_result": best_result, "top10": sorted_results[:10]}


# ═══════════════════════════════════════════════════════════════════════
# PRONG 3: Ensemble of Best Strategies
# ═══════════════════════════════════════════════════════════════════════


def prong_ensemble():
    """Combine VRP + TSM + Donchian into an ensemble."""
    print("\n" + "=" * 60)
    print("  PRONG 3: Ensemble (VRP + TSM + Donchian)")
    print("=" * 60)

    from quant_os.strategies.vol_risk_premium import VolRiskPremiumConfig, compute_vol_risk_premium_signals

    df = load_csv("XAUUSD", "D1")
    close = df["close"]
    high = df["high"]
    low = df["low"]
    returns = close.pct_change()

    try:
        gvz = pd.read_parquet(ROOT / "data" / "macro" / "yf_GVZCLS.parquet")
        if gvz.index.tz is None:
            gvz.index = gvz.index.tz_localize("UTC")
        if "gvz" in gvz.columns:
            gvz = gvz["gvz"]
        elif len(gvz.columns) > 0:
            gvz = gvz.iloc[:, 0]
    except Exception:
        gvz = None

    # --- Individual signals ---

    # 1) VRP
    vrp_config = VolRiskPremiumConfig(entry_z=1.0, exit_z=0.3, vrp_lookback=20)
    vrp_result = compute_vol_risk_premium_signals(close, gvz, vrp_config)
    vrp_sig = vrp_result.signal.astype(float)

    # 2) TSM Ensemble
    lookbacks = [20, 40, 60, 120]
    tsm_signals = []
    for lb in lookbacks:
        r_sum = returns.rolling(lb).sum()
        r_vol = returns.rolling(lb).std()
        tsm_signals.append(r_sum / r_vol.replace(0, np.nan))
    tsm_raw = sum(0.25 * s for s in tsm_signals)
    tsm_sig = np.sign(tsm_raw)

    # 3) Donchian 20
    period = 20
    don_high = high.rolling(period).max().shift(1)
    don_low = low.rolling(period).min().shift(1)
    don_raw = pd.Series(0, index=close.index)
    don_raw[close > don_high] = 1
    don_raw[close < don_low] = -1
    don_sig = pd.Series(0, index=close.index)
    pos = 0
    for i in range(len(close)):
        if don_raw.iloc[i] != 0:
            pos = don_raw.iloc[i]
        don_sig.iloc[i] = pos

    # --- Ensemble methods ---
    results = {}

    # Equal-weight vote
    print("\n  > Equal-weight vote (VRP + TSM + Donchian)...")
    ensemble_eq = np.sign(vrp_sig + tsm_sig + don_sig)
    eq_trades = simulate(ensemble_eq, close, cost_bps=XAU_COST_BPS)
    results["ensemble_equal"] = {
        "trades": len(eq_trades),
        "sharpe": round(sharpe(eq_trades), 4),
        "win_rate": round(sum(1 for t in eq_trades if t > 0) / max(len(eq_trades), 1), 4),
    }
    print(
        f"    Trades: {len(eq_trades)}, Sharpe: {results['ensemble_equal']['sharpe']}, "
        f"WR: {results['ensemble_equal']['win_rate']:.1%}"
    )

    # Majority vote (need 2/3 agreement)
    print("\n  > Majority vote (2/3 agreement)...")
    vote_sum = vrp_sig + tsm_sig + don_sig
    ensemble_maj = pd.Series(0, index=close.index)
    ensemble_maj[vote_sum >= 2] = 1
    ensemble_maj[vote_sum <= -2] = -1
    maj_trades = simulate(ensemble_maj, close, cost_bps=XAU_COST_BPS)
    results["ensemble_majority"] = {
        "trades": len(maj_trades),
        "sharpe": round(sharpe(maj_trades), 4),
        "win_rate": round(sum(1 for t in maj_trades if t > 0) / max(len(maj_trades), 1), 4),
    }
    print(
        f"    Trades: {len(maj_trades)}, Sharpe: {results['ensemble_majority']['sharpe']}, "
        f"WR: {results['ensemble_majority']['win_rate']:.1%}"
    )

    # VRP-weighted (VRP as filter: only trade when VRP agrees)
    print("\n  > VRP-filtered TSM (only when VRP agrees)...")
    tsm_vrp = tsm_sig.copy()
    tsm_vrp[(vrp_sig != 0) & (np.sign(tsm_sig) != np.sign(vrp_sig))] = 0
    tsm_vrp_trades = simulate(tsm_vrp, close, cost_bps=XAU_COST_BPS)
    results["tsm_vrp_filtered"] = {
        "trades": len(tsm_vrp_trades),
        "sharpe": round(sharpe(tsm_vrp_trades), 4),
        "win_rate": round(sum(1 for t in tsm_vrp_trades if t > 0) / max(len(tsm_vrp_trades), 1), 4),
    }
    print(
        f"    Trades: {len(tsm_vrp_trades)}, Sharpe: {results['tsm_vrp_filtered']['sharpe']}, "
        f"WR: {results['tsm_vrp_filtered']['win_rate']:.1%}"
    )

    # Unanimous (all 3 must agree)
    print("\n  > Unanimous (all 3 agree)...")
    ensemble_unan = pd.Series(0, index=close.index)
    ensemble_unan[(vrp_sig == 1) & (tsm_sig == 1) & (don_sig == 1)] = 1
    ensemble_unan[(vrp_sig == -1) & (tsm_sig == -1) & (don_sig == -1)] = -1
    unan_trades = simulate(ensemble_unan, close, cost_bps=XAU_COST_BPS)
    results["ensemble_unanimous"] = {
        "trades": len(unan_trades),
        "sharpe": round(sharpe(unan_trades), 4),
        "win_rate": round(sum(1 for t in unan_trades if t > 0) / max(len(unan_trades), 1), 4),
    }
    print(
        f"    Trades: {len(unan_trades)}, Sharpe: {results['ensemble_unanimous']['sharpe']}, "
        f"WR: {results['ensemble_unanimous']['win_rate']:.1%}"
    )

    # Individual strategies
    print("\n  > Individual strategies for comparison:")
    for name, sig in [("VRP", vrp_sig), ("TSM", tsm_sig), ("Donchian", don_sig)]:
        trades = simulate(sig, close, cost_bps=XAU_COST_BPS)
        s = sharpe(trades)
        wr = sum(1 for t in trades if t > 0) / max(len(trades), 1)
        results[f"individual_{name.lower()}"] = {
            "trades": len(trades),
            "sharpe": round(s, 4),
            "win_rate": round(wr, 4),
        }
        print(f"    {name}: Trades={len(trades)}, Sharpe={s:.4f}, WR={wr:.1%}")

    return results


# ═══════════════════════════════════════════════════════════════════════
# PRONG 4: New Instrument/Strategy Search
# ═══════════════════════════════════════════════════════════════════════


def prong_new_search():
    """Search for new instrument/strategy combinations."""
    print("\n" + "=" * 60)
    print("  PRONG 4: New Instrument/Strategy Search")
    print("=" * 60)

    # Available instruments
    instruments = {
        "XAUUSD": "D1",
        "XAGUSD": "D1",
        "XPTUSD": "D1",
        "XPDUSD": "D1",
        "EURUSD": "D1",
        "GBPUSD": "D1",
        "USDJPY": "D1",
        "AUDUSD": "D1",
        "BTCUSD": "D1",
        "ETHUSD": "D1",
    }

    # Strategies to test
    strategies = {}

    # 1) TSMOM per instrument
    def tsmom_signal(close, lookback=60):
        ret = close.pct_change()
        r_sum = ret.rolling(lookback).sum()
        r_vol = ret.rolling(lookback).std()
        return np.sign(r_sum / r_vol.replace(0, np.nan))

    # 2) Donchian breakout
    def donchian_signal(close, high, low, period=20):
        don_h = high.rolling(period).max().shift(1)
        don_l = low.rolling(period).min().shift(1)
        sig = pd.Series(0, index=close.index)
        sig[close > don_h] = 1
        sig[close < don_l] = -1
        pos = 0
        final = pd.Series(0, index=close.index)
        for i in range(len(close)):
            if sig.iloc[i] != 0:
                pos = sig.iloc[i]
            final.iloc[i] = pos
        return final

    # 3) Mean reversion (Bollinger)
    def bb_signal(close, period=20, nstd=2.0):
        mid = close.rolling(period).mean()
        std = close.rolling(period).std()
        upper = mid + nstd * std
        lower = mid - nstd * std
        sig = pd.Series(0, index=close.index)
        sig[close < lower] = 1  # buy dip
        sig[close > upper] = -1  # sell rip
        return sig

    # 4) Momentum (12-1 month)
    def momentum_signal(close, lookback=252, skip=21):
        ret = close / close.shift(lookback) - 1
        return np.sign(ret)

    strategy_fns = {
        "tsmom_60": lambda c, h, lo: tsmom_signal(c, 60),
        "tsmom_120": lambda c, h, lo: tsmom_signal(c, 120),
        "donchian_20": lambda c, h, lo: donchian_signal(c, h, lo, 20),
        "donchian_55": lambda c, h, lo: donchian_signal(c, h, lo, 55),
        "bb_mr": lambda c, h, lo: bb_signal(c),
        "momentum_12m": lambda c, h, lo: momentum_signal(c),
    }

    results = {}

    for sym, tf in instruments.items():
        # 2026-07-30: this scan previously ran every instrument through a
        # flat assumed cost_bps=10 -- the same fabrication shape that
        # invalidated trial #1030, just spread across 10 symbols instead of
        # 16. Skip anything without real calibration instead of guessing.
        if sym not in cost_calibrated_symbols(mode="paper"):
            print(f"  > {sym}: SKIPPED (no verified cost-calibration data)")
            continue
        sym_cost_bps = get_round_trip_cost_bps(sym)

        try:
            df = load_csv(sym, tf)
        except Exception:
            continue

        close = df["close"]
        high = df["high"] if "high" in df.columns else close
        low = df["low"] if "low" in df.columns else close

        if len(close) < 300:
            continue

        print(f"\n  > {sym} ({len(close)} bars):")

        for strat_name, strat_fn in strategy_fns.items():
            try:
                sig = strat_fn(close, high, low)
                trades = simulate(sig, close, cost_bps=sym_cost_bps)
                s = sharpe(trades)
                n = len(trades)
                wr = sum(1 for t in trades if t > 0) / max(n, 1)
                key = f"{sym}_{strat_name}"
                results[key] = {
                    "symbol": sym,
                    "strategy": strat_name,
                    "trades": n,
                    "sharpe": round(s, 4),
                    "win_rate": round(wr, 4),
                }
                if s > 0.5 and n >= 30:
                    print(f"    {strat_name}: Sharpe={s:.4f} WR={wr:.1%} Trades={n} *** PROMISING ***")
                elif s > 0:
                    print(f"    {strat_name}: Sharpe={s:.4f} WR={wr:.1%} Trades={n}")
            except Exception:
                continue

    # Find best combos
    promising = {k: v for k, v in results.items() if v["sharpe"] > 0.5 and v["trades"] >= 30}
    if promising:
        print(f"\n  PROMISING COMBINATIONS ({len(promising)}):")
        for k, v in sorted(promising.items(), key=lambda x: x[1]["sharpe"], reverse=True):
            print(f"    {k}: Sharpe={v['sharpe']:.4f} WR={v['win_rate']:.1%} Trades={v['trades']}")
    else:
        print("\n  No promising combinations found (Sharpe > 0.5 with 30+ trades)")

    return results


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prong", choices=["holdout", "vrp_tune", "ensemble", "new_search", "all"], default="all")
    args = parser.parse_args()

    print("=" * 60)
    print("  COMPREHENSIVE EDGE SEARCH")
    print(f"  {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    report = {"timestamp": datetime.now(UTC).isoformat(), "prongs": {}}

    if args.prong in ("holdout", "all"):
        report["prongs"]["holdout"] = prong_holdout()

    if args.prong in ("vrp_tune", "all"):
        report["prongs"]["vrp_tune"] = prong_vrp_tune()

    if args.prong in ("ensemble", "all"):
        report["prongs"]["ensemble"] = prong_ensemble()

    if args.prong in ("new_search", "all"):
        report["prongs"]["new_search"] = prong_new_search()

    # Save
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  Report saved: {REPORT_PATH}")

    # Summary
    print(f"\n{'=' * 60}")
    print("  SUMMARY")
    print(f"{'=' * 60}")

    if "holdout" in report["prongs"]:
        print("\n  Holdout Validation:")
        for k, v in report["prongs"]["holdout"].items():
            s = "PASS" if v.get("sharpe", 0) > 0.5 else "FAIL"
            print(f"    {s} {k}: Sharpe={v['sharpe']}, Trades={v['trades']}")

    if "vrp_tune" in report["prongs"]:
        best = report["prongs"]["vrp_tune"].get("best_result")
        if best:
            print(f"\n  Best VRP: Sharpe={best['sharpe']}, Trades={best['trades']}")

    if "ensemble" in report["prongs"]:
        print("\n  Ensemble Results:")
        for k, v in report["prongs"]["ensemble"].items():
            print(f"    {k}: Sharpe={v['sharpe']}, Trades={v['trades']}")

    if "new_search" in report["prongs"]:
        promising = {
            k: v
            for k, v in report["prongs"]["new_search"].items()
            if v.get("sharpe", 0) > 0.5 and v.get("trades", 0) >= 30
        }
        if promising:
            print(f"\n  New Promising: {len(promising)} combos")
        else:
            print("\n  No new promising combos found")


if __name__ == "__main__":
    main()
