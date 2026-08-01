#!/usr/bin/env python3
"""
Multi-Factor Alpha Research — compute candidate factors, test IC/IR, build composite.

Factors tested:
  1. TSMOM (time-series momentum) — sign of lookback return
  2. Mean Reversion — z-score of price vs SMA
  3. Volatility Regime — vol expansion/contraction
  4. Trend Strength — ADX-based
  5. Momentum Quality — Sharpe of recent returns
  6. Volume Momentum — volume expansion
  7. Price vs Fair Value — deviation from moving average
  8. Cross-Asset Momentum — momentum of correlated assets

Usage:
    python scripts/run_multifactor_research.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Allow running from repo root
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import signal_validator directly
import types
_validation_pkg = types.ModuleType("validation")
_validation_pkg.__path__ = [str(PROJECT_ROOT / "validation")]
sys.modules["validation"] = _validation_pkg
from validation.signal_validator import SignalValidator, SignalValidatorConfig


# ── Config ──────────────────────────────────────────────────────────────

ASSETS = {
    "XAUUSD": "data/XAUUSD_D1.csv",
    "NAS100": "data/NAS100_D1.csv",
    "OIL": "data/market_data/yfinance/CL_F.csv",
    "USDJPY": "data/USDJPY_D1.csv",
}

LOOKBACKS = [20, 40, 60, 120]
FORWARD_RETURN = 1  # 1-day forward return


# ── Factor Computation ──────────────────────────────────────────────────

def compute_factors(close: pd.Series, high: pd.Series = None, low: pd.Series = None,
                    volume: pd.Series = None, lookback: int = 20) -> dict[str, pd.Series]:
    """Compute candidate alpha factors from OHLCV data."""
    factors = {}

    # 1. TSMOM — sign of lookback return (baseline)
    ret_lookback = close.pct_change(lookback)
    factors["tsmom"] = np.sign(ret_lookback)

    # 2. Mean Reversion — z-score of price vs SMA
    sma = close.rolling(lookback).mean()
    std = close.rolling(lookback).std()
    zscore = (close - sma) / std.replace(0, np.nan)
    factors["mean_rev"] = -np.sign(zscore)  # Contrarian: buy when below SMA

    # 3. Volatility Regime — vol expansion/contraction
    ret = close.pct_change()
    vol = ret.rolling(lookback).std()
    vol_sma = vol.rolling(lookback).mean()
    vol_ratio = vol / vol_sma.replace(0, np.nan)
    # High vol → defensive (reduce), Low vol → aggressive (increase)
    factors["vol_regime"] = np.where(vol_ratio > 1.2, -0.5, np.where(vol_ratio < 0.8, 0.5, 0.0))

    # 4. Trend Strength — ADX-based (simplified)
    if high is not None and low is not None:
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(lookback).mean()
        plus_dm = (high - high.shift(1)).clip(lower=0)
        minus_dm = (low.shift(1) - low).clip(lower=0)
        plus_di = plus_dm.rolling(lookback).mean() / atr.replace(0, np.nan) * 100
        minus_di = minus_dm.rolling(lookback).mean() / atr.replace(0, np.nan) * 100
        dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
        adx = dx.rolling(lookback).mean()
        # Strong trend → follow, weak trend → mean revert
        trend_dir = np.sign(close - close.shift(lookback))
        factors["trend_str"] = np.where(adx > 25, trend_dir, 0.0)
    else:
        factors["trend_str"] = pd.Series(0.0, index=close.index)

    # 5. Momentum Quality — Sharpe of recent returns
    ret_series = close.pct_change()
    rolling_sharpe = ret_series.rolling(lookback).mean() / ret_series.rolling(lookback).std().replace(0, np.nan)
    factors["mom_quality"] = np.sign(rolling_sharpe)

    # 6. Price vs Fair Value — deviation from EMA
    ema = close.ewm(span=lookback, adjust=False).mean()
    deviation = (close - ema) / ema.replace(0, np.nan) * 100
    factors["fair_value"] = -np.sign(deviation)  # Contrarian

    # 7. Returns Smoothing — smoothed momentum (less noisy than raw TSMOM)
    smoothed_ret = ret_series.rolling(lookback).mean()
    factors["smooth_mom"] = np.sign(smoothed_ret)

    # 8. Volatility-Adjusted Momentum — momentum scaled by vol
    vol_adj_mom = ret_lookback / vol.replace(0, np.nan)
    factors["vol_adj_mom"] = np.sign(vol_adj_mom)

    return factors


def compute_forward_returns(close: pd.Series, periods: int = 1) -> pd.Series:
    """Compute forward returns."""
    return close.pct_change(periods).shift(-periods)


def compute_regime(close: pd.Series, lookback: int = 60) -> pd.Series:
    """Simple regime detection: trending vs ranging."""
    sma = close.rolling(lookback).mean()
    std = close.rolling(lookback).std()
    zscore = (close - sma) / std.replace(0, np.nan)
    # Trending: |z| > 1, Ranging: |z| < 0.5
    regime = pd.Series("ranging", index=close.index)
    regime[zscore.abs() > 1.0] = "trending"
    regime[zscore.abs() > 2.0] = "strong_trend"
    return regime


# ── Analysis ────────────────────────────────────────────────────────────

def analyze_factor(factor: pd.Series, forward_ret: pd.Series, regime: pd.Series,
                   symbol: str, factor_name: str, lookback: int) -> dict:
    """Run IC/IR analysis on a single factor."""
    aligned = pd.DataFrame({
        "factor": factor,
        "fwd_ret": forward_ret,
        "regime": regime,
    }).dropna()

    if len(aligned) < 60:
        return {"symbol": symbol, "factor": factor_name, "lookback": lookback,
                "verdict": "INSUFFICIENT_DATA", "n_obs": len(aligned)}

    # Overall IC
    validator = SignalValidator(SignalValidatorConfig(ic_window=60))
    report = validator.evaluate(
        signal=aligned["factor"].values,
        forward_returns=aligned["fwd_ret"].values,
        strategy_id=f"{symbol}_{factor_name}_{lookback}d",
    )

    ic_report = report.ic_report
    decay_report = report.decay_report

    # IC by regime
    regime_ics = {}
    for r in aligned["regime"].unique():
        mask = aligned["regime"] == r
        if mask.sum() >= 30:
            from validation.signal_validator import _correlation
            regime_ics[r] = _correlation(
                aligned.loc[mask, "factor"].values,
                aligned.loc[mask, "fwd_ret"].values,
                "spearman",
            )

    return {
        "symbol": symbol,
        "factor": factor_name,
        "lookback": lookback,
        "n_obs": len(aligned),
        "mean_ic": ic_report.mean_ic if ic_report else 0.0,
        "ic_std": ic_report.ic_std if ic_report else 0.0,
        "ic_ir": ic_report.ic_ir if ic_report else 0.0,
        "ic_hit_rate": ic_report.ic_hit_rate if ic_report else 0.0,
        "verdict": report.verdict,
        "score": report.score,
        "sharpe_early": decay_report.early_sharpe if decay_report else 0.0,
        "sharpe_late": decay_report.late_sharpe if decay_report else 0.0,
        "regime_ics": regime_ics,
    }


# ── Main ────────────────────────────────────────────────────────────────

def main():
    print("=" * 80)
    print("Multi-Factor Alpha Research — IC/IR Analysis on Actual Data")
    print("=" * 80)

    all_results = []

    for symbol, csv_rel in ASSETS.items():
        csv_path = PROJECT_ROOT / csv_rel
        if not csv_path.exists():
            print(f"SKIP {symbol}: {csv_path} not found")
            continue

        df = pd.read_csv(csv_path)

        # Find columns
        close_col = next((c for c in ["close", "Close"] if c in df.columns), None)
        high_col = next((c for c in ["high", "High"] if c in df.columns), None)
        low_col = next((c for c in ["low", "Low"] if c in df.columns), None)
        vol_col = next((c for c in ["volume", "Volume"] if c in df.columns), None)

        time_col = next((c for c in ["time", "Time", "date", "Date"] if c in df.columns), None)
        if time_col:
            df = df.set_index(pd.to_datetime(df[time_col]))
        else:
            df = df.set_index(pd.to_datetime(df.iloc[:, 0]))

        close = df[close_col].astype(float).dropna()
        high = df[high_col].astype(float) if high_col else None
        low = df[low_col].astype(float) if low_col else None
        volume = df[vol_col].astype(float) if vol_col else None

        if len(close) < 200:
            print(f"SKIP {symbol}: only {len(close)} bars")
            continue

        forward_ret = compute_forward_returns(close, FORWARD_RETURN)
        regime = compute_regime(close, lookback=60)

        for lookback in LOOKBACKS:
            if len(close) < lookback + 100:
                continue

            factors = compute_factors(close, high, low, volume, lookback)

            for factor_name, factor_series in factors.items():
                result = analyze_factor(factor_series, forward_ret, regime,
                                       symbol, factor_name, lookback)
                all_results.append(result)

    if not all_results:
        print("No results.")
        return

    # Print results table
    print(f"\n{'='*80}")
    print(f"{'Symbol':<8} {'Factor':<14} {'LB':>4} {'IC':>7} {'IC_IR':>7} {'Hit%':>6} {'Verdict':<15}")
    print(f"{'-'*8} {'-'*14} {'-'*4} {'-'*7} {'-'*7} {'-'*6} {'-'*15}")

    for r in sorted(all_results, key=lambda x: x.get("ic_ir", 0), reverse=True):
        ic = r.get("mean_ic", 0)
        ir = r.get("ic_ir", 0)
        hit = r.get("ic_hit_rate", 0)
        v = r.get("verdict", "?")
        print(f"{r['symbol']:<8} {r['factor']:<14} {r['lookback']:>4} {ic:>7.4f} {ir:>7.2f} {hit:>5.1%} {v:<15}")

    # Summary by factor
    print(f"\n{'='*80}")
    print("SUMMARY BY FACTOR (averaged across all assets/lookbacks)")
    print(f"{'='*80}")

    factor_summary = {}
    for r in all_results:
        f = r["factor"]
        if f not in factor_summary:
            factor_summary[f] = []
        factor_summary[f].append(r)

    print(f"\n{'Factor':<14} {'Avg IC':>8} {'Avg IR':>8} {'Avg Hit%':>9} {'Procs':>6} {'NoGo':>6}")
    print(f"{'-'*14} {'-'*8} {'-'*8} {'-'*9} {'-'*6} {'-'*6}")

    for factor_name in sorted(factor_summary.keys()):
        results = factor_summary[factor_name]
        avg_ic = np.mean([r["mean_ic"] for r in results])
        avg_ir = np.mean([r["ic_ir"] for r in results])
        avg_hit = np.mean([r["ic_hit_rate"] for r in results])
        n_proceed = sum(1 for r in results if r["verdict"] == "PROCEED")
        n_nogo = sum(1 for r in results if r["verdict"] == "NO_GO")
        print(f"{factor_name:<14} {avg_ic:>8.4f} {avg_ir:>8.2f} {avg_hit:>8.1%} {n_proceed:>6} {n_nogo:>6}")

    # Best factor per asset
    print(f"\n{'='*80}")
    print("BEST FACTOR PER ASSET")
    print(f"{'='*80}")

    for symbol in ASSETS:
        asset_results = [r for r in all_results if r["symbol"] == symbol and r.get("ic_ir", 0) > 0]
        if asset_results:
            best = max(asset_results, key=lambda r: r["ic_ir"])
            print(f"{symbol}: {best['factor']} {best['lookback']}d — IC={best['mean_ic']:.4f}, IR={best['ic_ir']:.2f}, Hit={best['ic_hit_rate']:.1%}")
        else:
            # All IC negative — find least negative
            asset_all = [r for r in all_results if r["symbol"] == symbol]
            if asset_all:
                best = max(asset_all, key=lambda r: r["ic_ir"])
                print(f"{symbol}: NO POSITIVE IC — least negative: {best['factor']} {best['lookback']}d (IC={best['mean_ic']:.4f}, IR={best['ic_ir']:.2f})")

    # Regime analysis
    print(f"\n{'='*80}")
    print("REGIME-CONDITIONAL IC")
    print(f"{'='*80}")

    for r in all_results:
        rcs = r.get("regime_ics", {})
        if rcs and len(rcs) > 1:
            regimes_str = ", ".join(f"{k}={v:.4f}" for k, v in sorted(rcs.items()))
            if any(v > 0.02 for v in rcs.values()):
                print(f"  {r['symbol']} {r['factor']} {r['lookback']}d: {regimes_str}")

    # Decision gate
    print(f"\n{'='*80}")
    print("DECISION GATE")
    print(f"{'='*80}")

    positive_ic = [r for r in all_results if r.get("ic_ir", 0) > 0.5 and r.get("mean_ic", 0) > 0.02]
    if positive_ic:
        print(f"[PASS] {len(positive_ic)} combinations passed IC mean > 0.02 AND IC IR > 0.5")
        for r in positive_ic:
            print(f"  {r['symbol']} {r['factor']} {r['lookback']}d — IC={r['mean_ic']:.4f}, IR={r['ic_ir']:.2f}")
    else:
        print("[FAIL] No combination passed IC mean > 0.02 AND IC IR > 0.5")
        print("Multi-factor approach also shows no edge on this data")

    # Save results
    results_df = pd.DataFrame([{k: v for k, v in r.items() if k != "regime_ics"} for r in all_results])
    output_path = PROJECT_ROOT / "reports" / "multifactor_research.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    results_df.to_csv(output_path, index=False)
    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
