#!/usr/bin/env python3
"""
Full Pipeline — Pre-register, Walk-Forward, Holdout, Ensemble, Go/No-Go.

Steps:
1. Pre-register Donchian + Momentum strategies (frozen configs)
2. Walk-forward validation with 7 gates on top combos
3. Validate passing strategies on sacred holdout
4. Build ensemble from passing strategies
5. Generate final go/no-go report

Usage:
    python scripts/full_pipeline.py
"""

import json
import math
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

REPORT_PATH = ROOT / "reports" / "full_pipeline_report.json"

sys.path.insert(0, str(ROOT))
from paper_engine.campaign import get_round_trip_cost_bps  # noqa: E402
from provenance import COST_CALIBRATED_SYMBOLS, require_cost_calibrated  # noqa: E402

# ─── Setup ──────────────────────────────────────────────────────────────


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
    r = np.array([x for x in returns if not np.isnan(x)])
    if len(r) < 2:
        return 0.0
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


def p_value_one_sample(returns):
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


def bootstrap_ci(returns, n_boot=1000, ci=0.95, seed=42):
    r = np.array([x for x in returns if not np.isnan(x)])
    if len(r) < 5:
        return -1.0, 1.0
    rng = np.random.default_rng(seed)
    means = [np.mean(rng.choice(r, size=len(r), replace=True)) for _ in range(n_boot)]
    alpha = (1 - ci) / 2
    return float(np.percentile(means, alpha * 100)), float(np.percentile(means, (1 - alpha) * 100))


def deflated_sharpe(sr, n_trials):
    if n_trials <= 1:
        return max(0.0, min(1.0, 0.5 + sr / 2))
    penalty = math.log(max(n_trials, 1)) / 10
    return max(0.0, min(1.0, 0.5 + (sr - penalty) / 2))


def simulate(signal, close, cost_bps):
    # 2026-07-30: default removed. cost_bps=10 was a flat guess with no link
    # to config/cost_calibration.json -- same fabrication shape as trial
    # #1030. Callers must pass a real measured value (see get_round_trip_cost_bps).
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
# STEP 1: Pre-Register Strategies (FROZEN)
# ═══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class DonchianConfig:
    """Pre-registered Donchian Channel Breakout config."""

    period: int = 55
    atr_period: int = 14
    stop_atr: float = 2.0
    vol_filter_pctile: float = 0.7  # skip breakouts above this vol percentile
    cost_bps: float = 10.0


@dataclass(frozen=True)
class MomentumConfig:
    """Pre-registered 12-1 Month Momentum config."""

    lookback: int = 252
    skip: int = 21
    vol_target: float = 0.10
    cost_bps: float = 10.0


@dataclass(frozen=True)
class TSMOMConfig:
    """Pre-registered TSMOM config."""

    lookbacks: tuple = (20, 40, 60, 120)
    weights: tuple = (0.25, 0.25, 0.25, 0.25)
    vol_target: float = 0.10
    cost_bps: float = 10.0


def generate_donchian_signal(close, high, low, config: DonchianConfig):
    """Generate Donchian channel breakout signal with vol filter."""
    returns = close.pct_change()
    vol20 = returns.rolling(20).std()
    vol_pctile = vol20.rolling(100).rank(pct=True)

    don_h = high.rolling(config.period).max().shift(1)
    don_l = low.rolling(config.period).min().shift(1)

    raw_sig = pd.Series(0, index=close.index)
    raw_sig[close > don_h] = 1
    raw_sig[close < don_l] = -1

    # State machine
    pos = 0
    sig = pd.Series(0, index=close.index)
    for i in range(len(close)):
        s = raw_sig.iloc[i]
        if s != 0:
            pos = s
        # Vol filter: skip high-vol breakouts
        vp = vol_pctile.iloc[i] if not pd.isna(vol_pctile.iloc[i]) else 0.5
        if vp > config.vol_filter_pctile:
            sig.iloc[i] = 0  # skip
        else:
            sig.iloc[i] = pos
    return sig


def generate_momentum_signal(close, config: MomentumConfig):
    """Generate 12-1 month momentum signal."""
    ret = close / close.shift(config.lookback) - 1
    vol = close.pct_change().rolling(21).std() * np.sqrt(252)
    vol_scale = config.vol_target / vol.clip(lower=0.01)
    vol_scale = vol_scale.clip(upper=2.0)
    return np.sign(ret) * vol_scale


def generate_tsmom_signal(close, config: TSMOMConfig):
    """Generate TSMOM ensemble signal."""
    returns = close.pct_change()
    signals = []
    for lb in config.lookbacks:
        r_sum = returns.rolling(lb).sum()
        r_vol = returns.rolling(lb).std()
        signals.append(r_sum / r_vol.replace(0, np.nan))
    raw = sum(w * s for w, s in zip(config.weights, signals, strict=False))
    return np.sign(raw)


# ═══════════════════════════════════════════════════════════════════════
# STEP 2: Walk-Forward Validation
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class GateResult:
    passed: bool
    value: float
    threshold: str
    detail: str


@dataclass
class WFValidation:
    strategy: str
    symbol: str
    n_folds: int
    total_trades: int
    oos_sharpe: float
    oos_win_rate: float
    oos_total_pnl: float
    oos_max_dd: float
    is_sharpe: float
    wfe: float
    p_value: float
    dsr: float
    pbo: float
    bootstrap_ci_lower: float
    bootstrap_ci_upper: float
    gates: dict
    gates_passed: int
    verdict: str
    fold_details: list


def run_wf_validation(
    strategy_name: str,
    signal_fn,
    symbol: str,
    tf: str = "D1",
    n_folds: int = 5,
    cost_bps: float = 10.0,
    n_trials: int = 1,
) -> WFValidation:
    """Run walk-forward validation with 7 gates."""
    df = load_csv(symbol, tf)
    close = df["close"]
    high = df["high"] if "high" in df.columns else close
    low = df["low"] if "low" in df.columns else close

    # Generate full signal
    sig = signal_fn(close, high, low)

    n = len(sig)
    fold_size = n // n_folds
    folds = []
    all_oos = []
    all_is = []

    for f in range(n_folds):
        test_s = f * fold_size
        test_e = min((f + 1) * fold_size, n)
        train_s = max(0, test_s - int(fold_size * 0.7 / 0.3))
        train_e = test_s

        if train_e - train_s < 20 or test_e - test_s < 10:
            continue

        is_trades = simulate(sig.iloc[train_s:train_e], close.iloc[train_s:train_e], cost_bps)
        oos_trades = simulate(sig.iloc[test_s:test_e], close.iloc[test_s:test_e], cost_bps)

        all_is.extend(is_trades)
        all_oos.extend(oos_trades)

        folds.append(
            {
                "fold": f,
                "is_trades": len(is_trades),
                "oos_trades": len(oos_trades),
                "is_sharpe": round(sharpe(is_trades), 4),
                "oos_sharpe": round(sharpe(oos_trades), 4),
                "is_pnl": round(sum(is_trades), 6),
                "oos_pnl": round(sum(oos_trades), 6),
            }
        )

    if not all_oos:
        return WFValidation(
            strategy=strategy_name,
            symbol=symbol,
            n_folds=0,
            total_trades=0,
            oos_sharpe=0,
            oos_win_rate=0,
            oos_total_pnl=0,
            oos_max_dd=0,
            is_sharpe=0,
            wfe=0,
            p_value=1,
            dsr=0,
            pbo=1,
            bootstrap_ci_lower=-1,
            bootstrap_ci_upper=1,
            gates={},
            gates_passed=0,
            verdict="INSUFFICIENT_SAMPLE",
            fold_details=folds,
        )

    avg_oos = np.mean([f["oos_sharpe"] for f in folds]) if folds else sharpe(all_oos)
    avg_is = np.mean([f["is_sharpe"] for f in folds]) if folds else sharpe(all_is)
    total_trades = len(all_oos)
    wr = sum(1 for t in all_oos if t > 0) / max(total_trades, 1)
    wfe = avg_oos / avg_is if abs(avg_is) > 1e-6 else 0
    pval = p_value_one_sample(all_oos)
    dsr = deflated_sharpe(avg_oos, n_trials)
    ci_lo, ci_hi = bootstrap_ci(all_oos)

    # PBO: count folds where OOS < 0 despite IS > 0
    pbo_count = sum(1 for f in folds if f["is_sharpe"] > 0 and f["oos_sharpe"] < 0)
    pbo_total = sum(1 for f in folds if f["is_sharpe"] > 0)
    pbo = pbo_count / pbo_total if pbo_total > 0 else 0.5

    # 7 Gates
    gates = {
        "1_pvalue": GateResult(pval < 0.05, pval, "< 0.05", f"p={pval:.6f}"),
        "2_oos_winrate": GateResult(wr >= 0.50, wr, ">= 50%", f"WR={wr:.1%}"),
        "3_wfe": GateResult(0.5 <= abs(wfe) <= 1.5, wfe, "0.5-1.5", f"WFE={wfe:.4f}"),
        "4_dsr": GateResult(dsr > 0.95, dsr, "> 0.95", f"DSR={dsr:.4f}"),
        "5_pbo": GateResult(pbo < 0.5, pbo, "< 0.50", f"PBO={pbo:.2f}"),
        "6_bootstrap": GateResult(ci_lo > 0, ci_lo, "CI excludes 0", f"CI=[{ci_lo:.6f}, {ci_hi:.6f}]"),
        "7_min_trades": GateResult(total_trades >= 100, total_trades, ">= 100", f"N={total_trades}"),
    }
    passed = sum(1 for g in gates.values() if g.passed)

    if passed == 7:
        verdict = "PASS_TO_NEXT_PHASE"
    elif passed >= 5 and gates["7_min_trades"].passed:
        verdict = "CONDITIONAL_PASS"
    elif pval < 0.05 and sum(all_oos) < 0:
        verdict = "NEGATIVE_EDGE_CONFIRMED"
    elif total_trades < 50:
        verdict = "INSUFFICIENT_SAMPLE"
    else:
        verdict = "ARCHIVE_NO_EDGE"

    return WFValidation(
        strategy=strategy_name,
        symbol=symbol,
        n_folds=len(folds),
        total_trades=total_trades,
        oos_sharpe=round(avg_oos, 4),
        oos_win_rate=round(wr, 4),
        oos_total_pnl=round(sum(all_oos), 6),
        oos_max_dd=round(max_dd(np.cumsum(all_oos).tolist()), 4),
        is_sharpe=round(avg_is, 4),
        wfe=round(wfe, 4),
        p_value=round(pval, 6),
        dsr=round(dsr, 4),
        pbo=round(pbo, 4),
        bootstrap_ci_lower=round(ci_lo, 6),
        bootstrap_ci_upper=round(ci_hi, 6),
        gates={k: {"passed": v.passed, "value": v.value, "detail": v.detail} for k, v in gates.items()},
        gates_passed=passed,
        verdict=verdict,
        fold_details=folds,
    )


# ═══════════════════════════════════════════════════════════════════════
# STEP 3: Sacred Holdout Validation
# ═══════════════════════════════════════════════════════════════════════


def validate_holdout(strategy_name, signal_fn, cost_bps):
    """Validate on sacred holdout data. holdout.csv is XAUUSD-only (xau_close/
    xau_high/xau_low) regardless of which strategy's signal_fn is passed in --
    cost_bps must be the real XAUUSD spread, not a flat guess."""
    h = pd.read_csv(ROOT / "data" / "sacred_holdout" / "holdout.csv")
    h["date"] = pd.to_datetime(h["date"], utc=True)
    h = h.set_index("date").sort_index()

    close = h["xau_close"]
    high = h["xau_high"]
    low = h["xau_low"]

    sig = signal_fn(close, high, low)
    trades = simulate(sig, close, cost_bps)

    return {
        "strategy": strategy_name,
        "trades": len(trades),
        "sharpe": round(sharpe(trades), 4),
        "win_rate": round(sum(1 for t in trades if t > 0) / max(len(trades), 1), 4),
        "total_pnl": round(sum(trades), 6),
    }


# ═══════════════════════════════════════════════════════════════════════
# STEP 4: Ensemble
# ═══════════════════════════════════════════════════════════════════════


def build_ensemble(signals: dict, close, cost_bps):
    """Build ensemble from multiple signal series."""
    # Equal-weight vote
    combined = sum(signals.values()) / len(signals)
    ensemble_sig = np.sign(combined)
    trades = simulate(ensemble_sig, close, cost_bps)

    # Majority vote (need >50% agreement)
    vote_sum = sum(signals.values())
    threshold = len(signals) / 2
    maj_sig = pd.Series(0, index=close.index)
    maj_sig[vote_sum > threshold] = 1
    maj_sig[vote_sum < -threshold] = -1
    maj_trades = simulate(maj_sig, close, cost_bps)

    return {
        "equal_weight": {
            "trades": len(trades),
            "sharpe": round(sharpe(trades), 4),
            "win_rate": round(sum(1 for t in trades if t > 0) / max(len(trades), 1), 4),
        },
        "majority_vote": {
            "trades": len(maj_trades),
            "sharpe": round(sharpe(maj_trades), 4),
            "win_rate": round(sum(1 for t in maj_trades if t > 0) / max(len(maj_trades), 1), 4),
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════


def main():
    print("=" * 60)
    print("  FULL PIPELINE: Pre-register + WF + Holdout + Ensemble")
    print(f"  {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    report = {"timestamp": datetime.now(UTC).isoformat(), "steps": {}}

    # ─── Step 1: Pre-register ─────────────────────────────────────
    print("\n" + "=" * 60)
    print("  STEP 1: Pre-Register Strategies (FROZEN)")
    print("=" * 60)

    # 2026-07-30: cost_bps=10 was a flat guess unlinked to any measured
    # spread -- same fabrication shape as trial #1030. XAUUSD is the only
    # symbol these frozen configs are actually backtested against once
    # donchian_20_eurusd (uncalibrated) is skipped below, so use its real
    # measured round-trip spread instead of a guess.
    require_cost_calibrated("XAUUSD")
    XAU_COST_BPS = get_round_trip_cost_bps("XAUUSD")

    donchian_55 = DonchianConfig(period=55, vol_filter_pctile=0.7, cost_bps=XAU_COST_BPS)
    donchian_20 = DonchianConfig(period=20, vol_filter_pctile=0.7, cost_bps=XAU_COST_BPS)
    momentum_12m = MomentumConfig(lookback=252, skip=21, cost_bps=XAU_COST_BPS)
    tsmom = TSMOMConfig(cost_bps=XAU_COST_BPS)

    configs = {
        "donchian_55_xauusd": {"config": donchian_55, "symbol": "XAUUSD", "type": "breakout"},
        "donchian_20_eurusd": {"config": donchian_20, "symbol": "EURUSD", "type": "breakout"},
        "donchian_20_xauusd": {"config": donchian_20, "symbol": "XAUUSD", "type": "breakout"},
        "momentum_12m_xauusd": {"config": momentum_12m, "symbol": "XAUUSD", "type": "momentum"},
        "tsom_xauusd": {"config": tsmom, "symbol": "XAUUSD", "type": "trend"},
    }

    for name, cfg in configs.items():
        print(f"  {name}: {cfg['config']}")

    report["steps"]["pre_register"] = {k: str(v["config"]) for k, v in configs.items()}

    # ─── Step 2: Walk-Forward ─────────────────────────────────────
    print("\n" + "=" * 60)
    print("  STEP 2: Walk-Forward Validation (7 Gates)")
    print("=" * 60)

    strategies = [
        ("donchian_55_xauusd", lambda c, h, l: generate_donchian_signal(c, h, l, donchian_55), "XAUUSD"),
        ("donchian_20_eurusd", lambda c, h, l: generate_donchian_signal(c, h, l, donchian_20), "EURUSD"),
        ("donchian_20_xauusd", lambda c, h, l: generate_donchian_signal(c, h, l, donchian_20), "XAUUSD"),
        ("momentum_12m_xauusd", lambda c, h, l: generate_momentum_signal(c, momentum_12m), "XAUUSD"),
        ("tsom_xauusd", lambda c, h, l: generate_tsmom_signal(c, tsmom), "XAUUSD"),
    ]

    wf_results = {}
    for name, fn, sym in strategies:
        print(f"\n  > {name} ({sym})...")
        # 2026-07-30: run_wf_validation loads real per-symbol data via
        # load_csv(sym, tf) -- unlike the holdout step below, EURUSD here is
        # genuinely EURUSD data. Skip rather than guess its cost.
        if sym not in COST_CALIBRATED_SYMBOLS:
            print(f"    SKIPPED (no verified cost-calibration data for {sym})")
            wf_results[name] = None
            continue
        sym_cost_bps = get_round_trip_cost_bps(sym)
        try:
            r = run_wf_validation(name, fn, sym, n_folds=5, cost_bps=sym_cost_bps, n_trials=7)
            wf_results[name] = r
            print(f"    Verdict: {r.verdict} | Gates: {r.gates_passed}/7")
            print(f"    OOS Sharpe: {r.oos_sharpe}, WR: {r.oos_win_rate:.1%}, Trades: {r.total_trades}")
            print(f"    p={r.p_value:.4f}, WFE={r.wfe:.4f}, DSR={r.dsr:.4f}, PBO={r.pbo:.2f}")
            for gk, gv in r.gates.items():
                status = "PASS" if gv["passed"] else "FAIL"
                print(f"      {status} {gk}: {gv['detail']}")
        except Exception as e:
            print(f"    Error: {e}")
            wf_results[name] = None

    report["steps"]["walk_forward"] = {}
    for name, r in wf_results.items():
        if r:
            report["steps"]["walk_forward"][name] = {
                "verdict": r.verdict,
                "gates_passed": r.gates_passed,
                "oos_sharpe": r.oos_sharpe,
                "trades": r.total_trades,
                "gates": r.gates,
            }

    # ─── Step 3: Holdout Validation ───────────────────────────────
    print("\n" + "=" * 60)
    print("  STEP 3: Sacred Holdout Validation")
    print("=" * 60)

    holdout_results = {}
    for name, fn, sym in strategies:
        print(f"\n  > {name} on holdout...")
        try:
            # holdout.csv is XAUUSD-only regardless of `sym` (see
            # validate_holdout docstring) -- XAU_COST_BPS is the real cost.
            r = validate_holdout(name, fn, cost_bps=XAU_COST_BPS)
            holdout_results[name] = r
            status = "PASS" if r["sharpe"] > 0.5 else "FAIL"
            print(f"    {status} Sharpe={r['sharpe']:.4f}, Trades={r['trades']}, WR={r['win_rate']:.1%}")
        except Exception as e:
            print(f"    Error: {e}")
            holdout_results[name] = {"error": str(e)}

    report["steps"]["holdout"] = holdout_results

    # ─── Step 4: Ensemble ─────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  STEP 4: Ensemble (Combining Passing Strategies)")
    print("=" * 60)

    # Collect passing strategies' signals
    df = load_csv("XAUUSD", "D1")
    close = df["close"]
    high = df["high"]
    low = df["low"]

    ensemble_signals = {}
    for name, fn, sym in strategies:
        if (
            sym == "XAUUSD"
            and wf_results.get(name)
            and wf_results[name].verdict in ("PASS_TO_NEXT_PHASE", "CONDITIONAL_PASS")
        ):
            sig = fn(close, high, low)
            ensemble_signals[name] = sig.astype(float)
            print(f"  Included: {name} (verdict: {wf_results[name].verdict})")

    if len(ensemble_signals) >= 2:
        ensemble_result = build_ensemble(ensemble_signals, close, cost_bps=XAU_COST_BPS)
        print(
            f"\n  Ensemble (equal-weight): Sharpe={ensemble_result['equal_weight']['sharpe']}, "
            f"Trades={ensemble_result['equal_weight']['trades']}"
        )
        print(
            f"  Ensemble (majority): Sharpe={ensemble_result['majority_vote']['sharpe']}, "
            f"Trades={ensemble_result['majority_vote']['trades']}"
        )
        report["steps"]["ensemble"] = ensemble_result
    elif len(ensemble_signals) == 1:
        print("\n  Only 1 strategy passed — no ensemble possible")
        report["steps"]["ensemble"] = {"note": "only 1 passing strategy"}
    else:
        print("\n  No strategies passed — no ensemble")
        report["steps"]["ensemble"] = {"note": "no passing strategies"}

    # Also try ensemble on holdout
    print("\n  Ensemble on holdout:")
    h = pd.read_csv(ROOT / "data" / "sacred_holdout" / "holdout.csv")
    h["date"] = pd.to_datetime(h["date"], utc=True)
    h = h.set_index("date").sort_index()
    h_close = h["xau_close"]
    h_high = h["xau_high"]
    h_low = h["xau_low"]

    holdout_ensemble_signals = {}
    for name, fn, sym in strategies:
        if sym == "XAUUSD" and holdout_results.get(name, {}).get("sharpe", 0) > 0:
            sig = fn(h_close, h_high, h_low)
            holdout_ensemble_signals[name] = sig.astype(float)

    if len(holdout_ensemble_signals) >= 2:
        h_ens = build_ensemble(holdout_ensemble_signals, h_close, cost_bps=XAU_COST_BPS)
        print(
            f"  Holdout ensemble (equal): Sharpe={h_ens['equal_weight']['sharpe']}, Trades={h_ens['equal_weight']['trades']}"
        )
        report["steps"]["holdout_ensemble"] = h_ens
    else:
        print("  Not enough passing strategies for holdout ensemble")

    # ─── Step 5: Go/No-Go Decision ────────────────────────────────
    print("\n" + "=" * 60)
    print("  STEP 5: GO / NO-GO DECISION")
    print("=" * 60)

    passing_wf = [name for name, r in wf_results.items() if r and r.verdict == "PASS_TO_NEXT_PHASE"]
    conditional_wf = [name for name, r in wf_results.items() if r and r.verdict == "CONDITIONAL_PASS"]
    passing_holdout = [name for name, r in holdout_results.items() if r.get("sharpe", 0) > 0.5]

    print(f"\n  Walk-Forward PASS: {len(passing_wf)} — {passing_wf}")
    print(f"  Walk-Forward CONDITIONAL: {len(conditional_wf)} — {conditional_wf}")
    print(f"  Holdout PASS (Sharpe > 0.5): {len(passing_holdout)} — {passing_holdout}")

    # Decision logic
    if passing_wf and passing_holdout:
        both = set(passing_wf) & set(passing_holdout)
        if both:
            decision = "GO_LIVE_MICRO"
            reason = f"Strategies pass BOTH WF gates AND holdout: {both}"
        else:
            decision = "CONDITIONAL_GO"
            reason = f"WF pass: {passing_wf}, Holdout pass: {passing_holdout} — need intersection"
    elif conditional_wf and passing_holdout:
        decision = "CONDITIONAL_GO"
        reason = f"Conditional WF: {conditional_wf}, Holdout pass: {passing_holdout}"
    elif passing_wf:
        decision = "NEEDS_HOLDOUT"
        reason = f"WF pass but no holdout validation: {passing_wf}"
    elif passing_holdout:
        decision = "NEEDS_WF"
        reason = f"Holdout pass but no WF validation: {passing_holdout}"
    else:
        decision = "NO_GO"
        reason = "No strategy passes both WF gates and holdout validation"

    print(f"\n  {'='*50}")
    print(f"  DECISION: {decision}")
    print(f"  {reason}")
    print(f"  {'='*50}")

    report["steps"]["decision"] = {
        "decision": decision,
        "reason": reason,
        "passing_wf": passing_wf,
        "conditional_wf": conditional_wf,
        "passing_holdout": passing_holdout,
    }

    # Save
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Convert dataclasses for JSON
    def to_json(obj):
        if hasattr(obj, "__dataclass_fields__"):
            return {k: to_json(v) for k, v in obj.__dict__.items()}
        if isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, dict):
            return {k: to_json(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [to_json(v) for v in obj]
        if isinstance(obj, bool):
            return obj
        return obj

    with open(REPORT_PATH, "w") as f:
        json.dump(to_json(report), f, indent=2)
    print(f"\n  Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()
