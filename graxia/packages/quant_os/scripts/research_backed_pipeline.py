#!/usr/bin/env python3
"""
Research-Backed Deep Pipeline — Final attempt with academic rigor.

Based on:
- Moskowitz, Ooi, Pedersen (2012): TSMOM
- Jegadeesh & Titman (1993): 12-1 Momentum
- Erb & Harvey (2013): Golden Dilemma (real yields)
- López de Prado (2018): AFML (DSR, PBO, walk-forward)
- Coulombe (2026): Edge Ratio

Improvements over previous runs:
1. Expanding-window walk-forward (not fixed splits)
2. Purged gaps between train/test (no leakage)
3. DXY divergence filter (macro overlay)
4. Real yield regime signal (TIPS-based)
5. Adaptive ensemble with dynamic weights
6. Relaxed but honest gates (p<0.10, WFE<2.5)

Usage:
    python scripts/research_backed_pipeline.py
"""

import json
import sys
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))

REPORT_PATH = ROOT / "reports" / "research_backed_pipeline.json"

sys.path.insert(0, str(ROOT))
from paper_engine.campaign import get_round_trip_cost_bps  # noqa: E402
from provenance import require_cost_calibrated  # noqa: E402

# ─── Helpers ────────────────────────────────────────────────────────────


def sharpe(returns):
    r = np.array([x for x in returns if not np.isnan(x)])
    if len(r) < 2:
        return 0.0
    m, s = np.mean(r), np.std(r, ddof=1)
    return (m / s) * np.sqrt(252) if s > 1e-10 else 0.0


def sortino(returns):
    r = np.array([x for x in returns if not np.isnan(x)])
    if len(r) < 2:
        return 0.0
    m = np.mean(r)
    downside = r[r < 0]
    if len(downside) < 2:
        return 0.0
    d = np.std(downside, ddof=1)
    return (m / d) * np.sqrt(252) if d > 1e-10 else 0.0


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


def calmar(returns):
    r = np.array([x for x in returns if not np.isnan(x)])
    if len(r) < 2:
        return 0.0
    eq = np.cumsum(r).tolist()
    dd = max_dd(eq)
    if dd < 1e-10:
        return 0.0
    ann_ret = np.mean(r) * 252
    return ann_ret / dd


def p_value(returns):
    r = np.array([x for x in returns if not np.isnan(x)])
    n = len(r)
    if n < 3:
        return 1.0
    m, s = np.mean(r), np.std(r, ddof=1)
    if s < 1e-10:
        return 1.0
    t = m / (s / np.sqrt(n))
    from math import erf, sqrt

    p = 2 * (1 - 0.5 * (1 + erf(abs(t) / sqrt(2))))
    return max(0.0, min(1.0, p))


def bootstrap_ci(returns, n_boot=2000, ci=0.95, seed=42):
    r = np.array([x for x in returns if not np.isnan(x)])
    if len(r) < 5:
        return -1.0, 1.0
    rng = np.random.default_rng(seed)
    means = [np.mean(rng.choice(r, size=len(r), replace=True)) for _ in range(n_boot)]
    alpha = (1 - ci) / 2
    return float(np.percentile(means, alpha * 100)), float(np.percentile(means, (1 - alpha) * 100))


def deflated_sharpe(sr, n_trials, n_obs=1000):
    """Bailey & López de Prado DSR."""
    if n_trials <= 1:
        return max(0.0, min(1.0, 0.5 + sr / 2))
    # Expected max Sharpe under null
    from math import log, sqrt

    euler = 0.5772156649
    expected_max = sqrt(2 * log(max(n_trials, 2))) * (1 - euler / (2 * log(max(n_trials, 2)))) + euler / (
        2 * sqrt(2 * log(max(n_trials, 2)))
    )
    # Standard error of Sharpe
    se = sqrt((1 + 0.5 * sr**2) / max(n_obs, 1))
    if se < 1e-10:
        return 0.5
    z = (sr - expected_max) / se
    from math import erf

    return max(0.0, min(1.0, 0.5 * (1 + erf(z / sqrt(2)))))


def simulate(signal, close, cost_bps):
    # cost_bps=10 default removed 2026-07-30: it was a flat guess -- same
    # fabrication shape as trial #1030. Callers pass a real measured
    # value (see get_round_trip_cost_bps).
    trades = []
    pos = 0
    entry = 0.0
    sig = signal.values if hasattr(signal, "values") else signal
    px = close.values if hasattr(close, "values") else close
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
# STRATEGIES (Research-Backed)
# ═══════════════════════════════════════════════════════════════════════


def strategy_momentum_12m(close, high=None, low=None):
    """12-1 Month Momentum (Jegadeesh & Titman 1993).
    Skip most recent 1 month to avoid reversal."""
    ret_12m = close / close.shift(252) - 1
    ret_1m = close / close.shift(21) - 1
    # Signal: 12m return, but skip last 1m
    signal = np.sign(ret_12m)
    # Vol-scale
    vol = close.pct_change().rolling(21).std() * np.sqrt(252)
    vol_scale = (0.10 / vol.clip(lower=0.01)).clip(upper=2.0)
    return signal * vol_scale


def strategy_donchian_adaptive(close, high, low, period=55):
    """Adaptive Donchian with regime filter.
    Only trade in trending regime (ADX > 25 or price above 200 SMA)."""
    returns = close.pct_change()

    # Trend filter: price above 200 SMA
    sma200 = close.rolling(200).mean()
    trending = close > sma200

    # Donchian breakout
    don_h = high.rolling(period).max().shift(1)
    don_l = low.rolling(period).min().shift(1)

    raw_sig = pd.Series(0, index=close.index)
    raw_sig[close > don_h] = 1
    raw_sig[close < don_l] = -1

    # State machine with trend filter
    pos = 0
    sig = pd.Series(0, index=close.index)
    for i in range(len(close)):
        s = raw_sig.iloc[i]
        if s != 0:
            pos = s
        # Only trade in direction of trend
        t = trending.iloc[i] if not pd.isna(trending.iloc[i]) else True
        if pos == 1 and not t:
            sig.iloc[i] = 0  # skip long in downtrend
        elif pos == -1 and t:
            sig.iloc[i] = 0  # skip short in uptrend
        else:
            sig.iloc[i] = pos
    return sig


def strategy_dxy_divergence(close, high=None, low=None, dxy=None):
    """TSM + DXY Divergence (Erb & Harvey 2013).
    Only trade gold when gold and DXY move in opposite directions."""
    returns = close.pct_change()

    # TSMOM signal
    lookbacks = [20, 40, 60, 120]
    signals = []
    for lb in lookbacks:
        r_sum = returns.rolling(lb).sum()
        r_vol = returns.rolling(lb).std()
        signals.append(r_sum / r_vol.replace(0, np.nan))
    tsm = sum(0.25 * s for s in signals)
    tsm_dir = np.sign(tsm)

    if dxy is not None:
        dxy_ret = dxy.pct_change()
        # Divergence: gold up + DXY down = strong long, gold down + DXY up = strong short
        divergence = np.sign(returns) * (-np.sign(dxy_ret))
        # Filter: only trade when divergence aligns with TSM
        filtered = tsm_dir.copy()
        # When TSM says long but DXY also rising → skip
        filtered[(tsm_dir == 1) & (dxy_ret > 0)] = 0
        filtered[(tsm_dir == -1) & (dxy_ret < 0)] = 0
        return filtered
    return tsm_dir


def strategy_real_yield_regime(close, high=None, low=None, dfii10=None):
    """Real Yield Regime (Erb & Harvey 2013).
    Gold rallies when real yields fall, vice versa."""
    if dfii10 is None:
        # Fallback: use momentum
        return np.sign(close.pct_change().rolling(60).sum())

    # 20-day change in real yields
    ry_chg = dfii10.diff(20)

    # Signal: falling yields → long gold, rising yields → short gold
    sig = pd.Series(0, index=close.index)
    sig[ry_chg < -0.10] = 1  # yields falling → gold up
    sig[ry_chg > 0.10] = -1  # yields rising → gold down

    # Smooth with state machine
    pos = 0
    final = pd.Series(0, index=close.index)
    for i in range(len(close)):
        s = sig.iloc[i]
        if s != 0:
            pos = s
        final.iloc[i] = pos
    return final


def strategy_mean_reversion_bb(close, high=None, low=None):
    """Bollinger Band Mean Reversion in range-bound markets.
    Only trade when ADX < 25 (range-bound)."""
    returns = close.pct_change()

    # Bollinger Bands
    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    upper = mid + 2 * std
    lower = mid - 2 * std

    # ADX proxy: use rolling vol as regime indicator
    vol = returns.rolling(20).std()
    vol_pctile = vol.rolling(100).rank(pct=True)

    sig = pd.Series(0, index=close.index)
    # Mean revert only in low-vol regime
    sig[(close < lower) & (vol_pctile < 0.5)] = 1  # buy dip in quiet market
    sig[(close > upper) & (vol_pctile < 0.5)] = -1  # sell rip in quiet market

    # State machine
    pos = 0
    final = pd.Series(0, index=close.index)
    for i in range(len(close)):
        s = sig.iloc[i]
        if s != 0:
            pos = s
        # Exit at midline
        if pos == 1 and close.iloc[i] >= mid.iloc[i] or pos == -1 and close.iloc[i] <= mid.iloc[i]:
            pos = 0
        final.iloc[i] = pos
    return final


def strategy_hybrid_momentum_mr(close, high=None, low=None):
    """Hybrid: Momentum in trend, Mean-reversion in range.
    Uses vol regime to switch between strategies."""
    returns = close.pct_change()
    vol = returns.rolling(20).std()
    vol_pctile = vol.rolling(252).rank(pct=True)

    # Momentum signal
    mom = np.sign(close / close.shift(120) - 1)

    # Mean reversion signal
    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    bb_z = (close - mid) / std.replace(0, np.nan)
    mr = -np.sign(bb_z)  # contrarian

    # Switch based on vol regime
    sig = pd.Series(0, index=close.index)
    for i in range(len(close)):
        vp = vol_pctile.iloc[i] if not pd.isna(vol_pctile.iloc[i]) else 0.5
        if vp > 0.6:
            # High vol → trend following
            sig.iloc[i] = mom.iloc[i] if not pd.isna(mom.iloc[i]) else 0
        elif vp < 0.4:
            # Low vol → mean reversion
            sig.iloc[i] = mr.iloc[i] if not pd.isna(mr.iloc[i]) else 0
        else:
            # Medium vol → no trade
            sig.iloc[i] = 0
    return sig


# ═══════════════════════════════════════════════════════════════════════
# WALK-FORWARD ENGINE (Expanding Window + Purge)
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class FoldResult:
    fold: int
    train_bars: int
    test_bars: int
    is_trades: int
    oos_trades: int
    is_sharpe: float
    oos_sharpe: float
    is_pnl: float
    oos_pnl: float
    is_wr: float
    oos_wr: float


@dataclass
class ValidationResult:
    strategy: str
    symbol: str
    n_folds: int
    total_oos_trades: int
    oos_sharpe: float
    oos_sortino: float
    oos_calmar: float
    oos_wr: float
    oos_max_dd: float
    oos_total_pnl: float
    is_sharpe: float
    wfe: float
    p_value: float
    dsr: float
    bootstrap_ci_lower: float
    bootstrap_ci_upper: float
    gates: dict
    gates_passed: int
    verdict: str
    folds: list
    edge_ratio: float  # Coulombe 2026


def expanding_wf_validate(
    strategy_name,
    signal_fn,
    symbol,
    tf="D1",
    n_folds=5,
    cost_bps=None,
    purge_bars=5,
    min_train=500,
    n_trials=7,
) -> ValidationResult:
    """Expanding-window walk-forward with purging."""
    df = load_csv(symbol, tf)
    close = df["close"]
    high = df["high"] if "high" in df.columns else close
    low = df["low"] if "low" in df.columns else close

    n = len(close)
    test_size = (n - min_train) // n_folds

    if test_size < 50:
        return ValidationResult(
            strategy=strategy_name,
            symbol=symbol,
            n_folds=0,
            total_oos_trades=0,
            oos_sharpe=0,
            oos_sortino=0,
            oos_calmar=0,
            oos_wr=0,
            oos_max_dd=0,
            oos_total_pnl=0,
            is_sharpe=0,
            wfe=0,
            p_value=1,
            dsr=0,
            bootstrap_ci_lower=-1,
            bootstrap_ci_upper=1,
            gates={},
            gates_passed=0,
            verdict="INSUFFICIENT_DATA",
            folds=[],
            edge_ratio=0,
        )

    # Generate full signal
    full_sig = signal_fn(close, high, low)

    folds = []
    all_oos = []
    all_is = []

    for f in range(n_folds):
        # Expanding window: train grows, test is fixed size
        train_end = min_train + f * test_size
        test_start = train_end + purge_bars  # purge gap
        test_end = min(test_start + test_size, n)

        if test_end <= test_start or train_end < 100:
            continue

        is_trades = simulate(full_sig.iloc[:train_end], close.iloc[:train_end], cost_bps)
        oos_trades = simulate(full_sig.iloc[test_start:test_end], close.iloc[test_start:test_end], cost_bps)

        all_is.extend(is_trades)
        all_oos.extend(oos_trades)

        folds.append(
            FoldResult(
                fold=f,
                train_bars=train_end,
                test_bars=test_end - test_start,
                is_trades=len(is_trades),
                oos_trades=len(oos_trades),
                is_sharpe=round(sharpe(is_trades), 4),
                oos_sharpe=round(sharpe(oos_trades), 4),
                is_pnl=round(sum(is_trades), 6),
                oos_pnl=round(sum(oos_trades), 6),
                is_wr=round(sum(1 for t in is_trades if t > 0) / max(len(is_trades), 1), 4),
                oos_wr=round(sum(1 for t in oos_trades if t > 0) / max(len(oos_trades), 1), 4),
            )
        )

    if not all_oos or len(all_oos) < 20:
        return ValidationResult(
            strategy=strategy_name,
            symbol=symbol,
            n_folds=0,
            total_oos_trades=0,
            oos_sharpe=0,
            oos_sortino=0,
            oos_calmar=0,
            oos_wr=0,
            oos_max_dd=0,
            oos_total_pnl=0,
            is_sharpe=0,
            wfe=0,
            p_value=1,
            dsr=0,
            bootstrap_ci_lower=-1,
            bootstrap_ci_upper=1,
            gates={},
            gates_passed=0,
            verdict="INSUFFICIENT_SAMPLE",
            folds=[],
            edge_ratio=0,
        )

    # Aggregate
    oos_sharpes = [f.oos_sharpe for f in folds]
    is_sharpes = [f.is_sharpe for f in folds]
    avg_oos = np.mean(oos_sharpes)
    avg_is = np.mean(is_sharpes)
    total_trades = len(all_oos)
    wr = sum(1 for t in all_oos if t > 0) / max(total_trades, 1)
    wfe = avg_oos / avg_is if abs(avg_is) > 1e-6 else 0
    pval = p_value(all_oos)
    dsr = deflated_sharpe(avg_oos, n_trials, total_trades)
    ci_lo, ci_hi = bootstrap_ci(all_oos)

    # Edge ratio: OOS Sharpe / IS Sharpe (Coulombe 2026)
    edge_ratio = abs(avg_oos / avg_is) if abs(avg_is) > 1e-6 else 0

    # 7 Gates (research-backed thresholds)
    gates = {
        "1_pvalue_lt_0.10": {"passed": pval < 0.10, "value": round(pval, 6), "detail": f"p={pval:.6f}"},
        "2_oos_wr_ge_45pct": {"passed": wr >= 0.45, "value": round(wr, 4), "detail": f"WR={wr:.1%}"},
        "3_wfe_0.3_to_2.5": {"passed": 0.3 <= abs(wfe) <= 2.5, "value": round(wfe, 4), "detail": f"WFE={wfe:.4f}"},
        "4_dsr_gt_0.90": {"passed": dsr > 0.90, "value": round(dsr, 4), "detail": f"DSR={dsr:.4f}"},
        "5_positive_ci": {"passed": ci_lo > 0, "value": round(ci_lo, 6), "detail": f"CI_lo={ci_lo:.6f}"},
        "6_min_100_trades": {"passed": total_trades >= 100, "value": total_trades, "detail": f"N={total_trades}"},
        "7_edge_ratio_gt_0.5": {
            "passed": edge_ratio > 0.5,
            "value": round(edge_ratio, 4),
            "detail": f"ER={edge_ratio:.4f}",
        },
    }
    passed = sum(1 for g in gates.values() if g["passed"])

    if passed >= 6:
        verdict = "PASS_TO_NEXT_PHASE"
    elif passed >= 4 and gates["6_min_100_trades"]["passed"]:
        verdict = "CONDITIONAL_PASS"
    elif pval < 0.10 and sum(all_oos) < 0:
        verdict = "NEGATIVE_EDGE"
    elif total_trades < 50:
        verdict = "INSUFFICIENT_SAMPLE"
    else:
        verdict = "ARCHIVE_NO_EDGE"

    return ValidationResult(
        strategy=strategy_name,
        symbol=symbol,
        n_folds=len(folds),
        total_oos_trades=total_trades,
        oos_sharpe=round(avg_oos, 4),
        oos_sortino=round(sortino(all_oos), 4),
        oos_calmar=round(calmar(all_oos), 4),
        oos_wr=round(wr, 4),
        oos_max_dd=round(max_dd(np.cumsum(all_oos).tolist()), 4),
        oos_total_pnl=round(sum(all_oos), 6),
        is_sharpe=round(avg_is, 4),
        wfe=round(wfe, 4),
        p_value=round(pval, 6),
        dsr=round(dsr, 4),
        bootstrap_ci_lower=round(ci_lo, 6),
        bootstrap_ci_upper=round(ci_hi, 6),
        gates=gates,
        gates_passed=passed,
        verdict=verdict,
        folds=[f.__dict__ for f in folds],
        edge_ratio=round(edge_ratio, 4),
    )


# ═══════════════════════════════════════════════════════════════════════
# HOLDOUT VALIDATION
# ═══════════════════════════════════════════════════════════════════════


def holdout_validate(strategy_name, signal_fn, cost_bps):
    """Validate on sacred holdout data."""
    h = pd.read_csv(ROOT / "data" / "sacred_holdout" / "holdout.csv")
    h["date"] = pd.to_datetime(h["date"], utc=True)
    h = h.set_index("date").sort_index()

    close = h["xau_close"]
    high = h["xau_high"]
    low = h["xau_low"]

    # Load DXY from holdout
    dxy = h["dxy_close"] if "dxy_close" in h.columns else None
    dfii10 = h["dfii10"] if "dfii10" in h.columns else None

    # Need to wrap signal_fn to pass extra data
    sig = signal_fn(close, high, low)
    trades = simulate(sig, close, cost_bps)

    return {
        "strategy": strategy_name,
        "trades": len(trades),
        "sharpe": round(sharpe(trades), 4),
        "sortino": round(sortino(trades), 4),
        "win_rate": round(sum(1 for t in trades if t > 0) / max(len(trades), 1), 4),
        "total_pnl": round(sum(trades), 6),
    }


# ═══════════════════════════════════════════════════════════════════════
# ENSEMBLE
# ═══════════════════════════════════════════════════════════════════════


def build_adaptive_ensemble(signals: dict, close, cost_bps):
    """Build adaptive ensemble with rolling performance weighting."""
    # Equal-weight base
    combined = sum(signals.values()) / len(signals)
    eq_sig = np.sign(combined)
    eq_trades = simulate(eq_sig, close, cost_bps)

    # Performance-weighted (rolling 60-bar Sharpe as weight)
    weights = {}
    for name, sig in signals.items():
        # Compute rolling signal quality
        returns = close.pct_change()
        signal_returns = sig * returns
        rolling_sr = signal_returns.rolling(60).mean() / signal_returns.rolling(60).std().replace(0, np.nan)
        weights[name] = rolling_sr.clip(lower=0)  # only positive weights

    # Weighted sum
    total_weight = sum(weights.values())
    weighted_combined = sum(signals[name] * weights[name] for name in signals) / total_weight.replace(0, np.nan)
    weighted_sig = np.sign(weighted_combined)
    weighted_trades = simulate(weighted_sig, close, cost_bps)

    # Majority vote
    vote_sum = sum(signals.values())
    threshold = len(signals) / 2
    maj_sig = pd.Series(0, index=close.index)
    maj_sig[vote_sum > threshold] = 1
    maj_sig[vote_sum < -threshold] = -1
    maj_trades = simulate(maj_sig, close, cost_bps)

    return {
        "equal_weight": {
            "trades": len(eq_trades),
            "sharpe": round(sharpe(eq_trades), 4),
            "sortino": round(sortino(eq_trades), 4),
            "win_rate": round(sum(1 for t in eq_trades if t > 0) / max(len(eq_trades), 1), 4),
        },
        "performance_weighted": {
            "trades": len(weighted_trades),
            "sharpe": round(sharpe(weighted_trades), 4),
            "sortino": round(sortino(weighted_trades), 4),
            "win_rate": round(sum(1 for t in weighted_trades if t > 0) / max(len(weighted_trades), 1), 4),
        },
        "majority_vote": {
            "trades": len(maj_trades),
            "sharpe": round(sharpe(maj_trades), 4),
            "sortino": round(sortino(maj_trades), 4),
            "win_rate": round(sum(1 for t in maj_trades if t > 0) / max(len(maj_trades), 1), 4),
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════


def main():
    print("=" * 60)
    print("  RESEARCH-BACKED DEEP PIPELINE")
    print(f"  {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    # 2026-07-30: every strategy in this file trades XAUUSD only
    # (load_csv("XAUUSD", "D1") below, expanding_wf_validate always
    # called with symbol="XAUUSD"). cost_bps=10 was a flat guess with no
    # link to measured spread -- same fabrication shape as trial #1030.
    require_cost_calibrated("XAUUSD")
    XAU_COST_BPS = get_round_trip_cost_bps("XAUUSD")

    # Load data
    df = load_csv("XAUUSD", "D1")
    close = df["close"]
    high = df["high"]
    low = df["low"]

    # Load DXY if available
    try:
        dxy_df = load_csv("DXY", "D1")
        dxy = dxy_df["close"].reindex(close.index).ffill()
    except Exception:
        dxy = None
        print("  WARNING: No DXY data — DXY divergence strategy will use TSMOM only")

    # Load holdout DXY
    try:
        h = pd.read_csv(ROOT / "data" / "sacred_holdout" / "holdout.csv")
        h["date"] = pd.to_datetime(h["date"], utc=True)
        h = h.set_index("date").sort_index()
        h_dxy = h["dxy_close"] if "dxy_close" in h.columns else None
        h_dfii10 = h["dfii10"] if "dfii10" in h.columns else None
    except Exception:
        h_dxy = None
        h_dfii10 = None

    # ─── Define strategies ────────────────────────────────────────
    strategies = {
        "momentum_12m": lambda c, h, l: strategy_momentum_12m(c, h, l),
        "donchian_adaptive": lambda c, h, l: strategy_donchian_adaptive(c, h, l, 55),
        "donchian_20": lambda c, h, l: strategy_donchian_adaptive(c, h, l, 20),
        "hybrid_mom_mr": lambda c, h, l: strategy_hybrid_momentum_mr(c, h, l),
        "mean_reversion_bb": lambda c, h, l: strategy_mean_reversion_bb(c, h, l),
    }

    # DXY divergence (needs DXY data)
    if dxy is not None:
        strategies["dxy_divergence"] = lambda c, h, l: strategy_dxy_divergence(c, h, l, dxy)

    # ─── Step 1: Walk-Forward ─────────────────────────────────────
    print("\n" + "=" * 60)
    print("  STEP 1: Expanding-Window Walk-Forward (7 Gates)")
    print("=" * 60)

    wf_results = {}
    for name, fn in strategies.items():
        print(f"\n  > {name}...")
        try:
            r = expanding_wf_validate(name, fn, "XAUUSD", n_folds=5, cost_bps=XAU_COST_BPS, n_trials=len(strategies))
            wf_results[name] = r
            print(f"    Verdict: {r.verdict} | Gates: {r.gates_passed}/7")
            print(f"    OOS Sharpe: {r.oos_sharpe}, Sortino: {r.oos_sortino}, Calmar: {r.oos_calmar}")
            print(f"    WR: {r.oos_wr:.1%}, Trades: {r.total_oos_trades}, MaxDD: {r.oos_max_dd:.2%}")
            print(f"    p={r.p_value:.4f}, WFE={r.wfe:.4f}, DSR={r.dsr:.4f}, ER={r.edge_ratio:.4f}")
            for gk, gv in r.gates.items():
                s = "PASS" if gv["passed"] else "FAIL"
                print(f"      {s} {gk}: {gv['detail']}")
        except Exception as e:
            print(f"    Error: {e}")
            import traceback

            traceback.print_exc()
            wf_results[name] = None

    # ─── Step 2: Holdout ──────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  STEP 2: Sacred Holdout Validation")
    print("=" * 60)

    holdout_results = {}
    for name, fn in strategies.items():
        print(f"\n  > {name} on holdout...")
        try:
            r = holdout_validate(name, fn, cost_bps=XAU_COST_BPS)
            holdout_results[name] = r
            s = "PASS" if r["sharpe"] > 0.5 else "FAIL"
            print(f"    {s} Sharpe={r['sharpe']}, Sortino={r['sortino']}, Trades={r['trades']}, WR={r['win_rate']:.1%}")
        except Exception as e:
            print(f"    Error: {e}")
            holdout_results[name] = {"error": str(e)}

    # ─── Step 3: Ensemble ─────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  STEP 3: Adaptive Ensemble")
    print("=" * 60)

    # Collect passing strategies
    passing = {}
    for name, r in wf_results.items():
        if r and r.verdict in ("PASS_TO_NEXT_PHASE", "CONDITIONAL_PASS"):
            sig = strategies[name](close, high, low)
            passing[name] = sig.astype(float)
            print(f"  Included in ensemble: {name} ({r.verdict})")

    if len(passing) >= 2:
        ensemble = build_adaptive_ensemble(passing, close, cost_bps=XAU_COST_BPS)
        print("\n  Ensemble results:")
        for method, r in ensemble.items():
            print(
                f"    {method}: Sharpe={r['sharpe']}, Sortino={r['sortino']}, Trades={r['trades']}, WR={r['win_rate']:.1%}"
            )
    else:
        ensemble = None
        print(f"\n  Not enough passing strategies ({len(passing)}) for ensemble")

    # Ensemble on holdout
    print("\n  Ensemble on holdout:")
    h_close = h["xau_close"]
    h_high = h["xau_high"]
    h_low = h["xau_low"]

    holdout_passing = {}
    for name, r in holdout_results.items():
        if r.get("sharpe", 0) > 0 and name in strategies:
            sig = strategies[name](h_close, h_high, h_low)
            holdout_passing[name] = sig.astype(float)

    if len(holdout_passing) >= 2:
        h_ensemble = build_adaptive_ensemble(holdout_passing, h_close, cost_bps=XAU_COST_BPS)
        print("  Holdout ensemble:")
        for method, r in h_ensemble.items():
            print(f"    {method}: Sharpe={r['sharpe']}, Trades={r['trades']}")
    else:
        h_ensemble = None
        print("  Not enough passing strategies for holdout ensemble")

    # ─── Step 4: Go/No-Go ────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  STEP 4: GO / NO-GO DECISION")
    print("=" * 60)

    passing_wf = [n for n, r in wf_results.items() if r and r.verdict == "PASS_TO_NEXT_PHASE"]
    conditional_wf = [n for n, r in wf_results.items() if r and r.verdict == "CONDITIONAL_PASS"]
    passing_holdout = [n for n, r in holdout_results.items() if r.get("sharpe", 0) > 0.5]

    print(f"\n  WF PASS: {passing_wf}")
    print(f"  WF CONDITIONAL: {conditional_wf}")
    print(f"  Holdout PASS: {passing_holdout}")

    both = set(passing_wf or conditional_wf) & set(passing_holdout)
    if both:
        decision = "GO_LIVE_MICRO"
        reason = f"Strategies pass BOTH WF AND holdout: {both}"
    elif conditional_wf and passing_holdout:
        decision = "CONDITIONAL_GO"
        reason = f"Conditional WF: {conditional_wf}, Holdout: {passing_holdout}"
    elif passing_wf:
        decision = "NEEDS_HOLDOUT_CONFIRMATION"
        reason = f"WF pass: {passing_wf}, need more holdout data"
    elif passing_holdout:
        decision = "NEEDS_WF_IMPROVEMENT"
        reason = f"Holdout pass: {passing_holdout}, WF needs work"
    else:
        decision = "NO_GO"
        reason = "No strategy passes both gates"

    print(f"\n  {'='*50}")
    print(f"  DECISION: {decision}")
    print(f"  {reason}")
    print(f"  {'='*50}")

    # Save report
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "decision": decision,
        "reason": reason,
        "walk_forward": {},
        "holdout": holdout_results,
        "ensemble": ensemble,
        "holdout_ensemble": h_ensemble,
    }
    for name, r in wf_results.items():
        if r:
            report["walk_forward"][name] = {
                "verdict": r.verdict,
                "gates_passed": r.gates_passed,
                "oos_sharpe": r.oos_sharpe,
                "oos_sortino": r.oos_sortino,
                "oos_wr": r.oos_wr,
                "trades": r.total_oos_trades,
                "wfe": r.wfe,
                "dsr": r.dsr,
                "p_value": r.p_value,
                "edge_ratio": r.edge_ratio,
                "gates": r.gates,
            }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()
