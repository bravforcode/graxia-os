#!/usr/bin/env python3
"""
Run IC/IR analysis on actual TSM signal data.

Loads D1 data, computes TSM signals, and runs SignalValidator
to determine if the signal has real predictive power.

Usage:
    python scripts/run_tsm_ic_analysis.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Allow running from repo root
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import signal_validator directly — bypass validation/__init__.py (broken native_runner chain)
import types
# Create a minimal validation package that only has signal_validator
_validation_pkg = types.ModuleType("validation")
_validation_pkg.__path__ = [str(PROJECT_ROOT / "validation")]
sys.modules["validation"] = _validation_pkg

from validation.signal_validator import SignalValidator, SignalValidatorConfig  # noqa: E402


# ── Config ──────────────────────────────────────────────────────────────

LOOKBACKS = [20, 40, 60, 120]  # TSM lookbacks in days
ASSETS = {
    "XAUUSD": "data/XAUUSD_D1.csv",
    "NAS100": "data/NAS100_D1.csv",
    "OIL": "data/market_data/yfinance/CL_F.csv",
    "USDJPY": "data/USDJPY_D1.csv",
}

# ── Helpers ─────────────────────────────────────────────────────────────

def compute_returns(close: pd.Series, period: int = 1) -> pd.Series:
    """Compute simple returns with honest missing-bar handling."""
    return close.pct_change(periods=period).shift(-period)  # shift(-period) = forward return


def compute_tsm_signal(close: pd.Series, lookback: int) -> pd.Series:
    """TSM signal: sign of lookback-period return."""
    ret = close.pct_change(lookback)
    return np.sign(ret)


# ── Main ────────────────────────────────────────────────────────────────

def analyze_asset(symbol: str, csv_path: Path, lookback: int) -> dict | None:
    """Run IC/IR analysis for a single asset + lookback."""
    if not csv_path.exists():
        print(f"  SKIP {symbol}: {csv_path} not found")
        return None

    df = pd.read_csv(csv_path)
    # Find close column
    close_col = None
    for col in ["close", "Close", "ClosePrice", "close_price"]:
        if col in df.columns:
            close_col = col
            break
    if close_col is None:
        print(f"  SKIP {symbol}: no close column found in {csv_path}")
        return None

    # Find time column
    time_col = None
    for col in ["time", "Time", "timestamp", "date", "Date"]:
        if col in df.columns:
            time_col = col
            break
    if time_col:
        df = df.set_index(pd.to_datetime(df[time_col]))
    else:
        df = df.set_index(pd.to_datetime(df.iloc[:, 0]))
    close = df[close_col].astype(float).dropna()

    if len(close) < lookback + 100:
        print(f"  SKIP {symbol}: only {len(close)} bars, need {lookback + 100}")
        return None

    # Compute signal: sign of lookback-period return
    signal = compute_tsm_signal(close, lookback)

    # Compute forward returns (what actually happened next day)
    forward_returns = close.pct_change().shift(-1)  # 1-day forward return

    # Align signal and forward returns
    aligned = pd.DataFrame({"signal": signal, "fwd_ret": forward_returns}).dropna()

    if len(aligned) < 60:
        print(f"  SKIP {symbol}: only {len(aligned)} aligned observations")
        return None

    # Run IC analysis
    validator = SignalValidator(SignalValidatorConfig(
        ic_window=60,
        min_mean_ic=0.02,
        min_ic_ir=0.5,
    ))

    report = validator.evaluate(
        signal=aligned["signal"].values,
        forward_returns=aligned["fwd_ret"].values,
        strategy_id=f"{symbol}_TSM_{lookback}d",
    )

    return {
        "symbol": symbol,
        "lookback": lookback,
        "n_obs": len(aligned),
        "mean_ic": report.ic_report.mean_ic if report.ic_report else 0.0,
        "ic_std": report.ic_report.ic_std if report.ic_report else 0.0,
        "ic_ir": report.ic_report.ic_ir if report.ic_report else 0.0,
        "ic_hit_rate": report.ic_report.ic_hit_rate if report.ic_report else 0.0,
        "verdict": report.verdict,
        "score": report.score,
        "decay_sharpe_early": report.decay_report.early_sharpe if report.decay_report else 0.0,
        "decay_sharpe_late": report.decay_report.late_sharpe if report.decay_report else 0.0,
        "decay_detected": report.decay_report.has_sharpe_decayed if report.decay_report else False,
    }


def main():
    print("=" * 70)
    print("TSM Signal Validation — IC/IR Analysis on Actual Data")
    print("=" * 70)

    all_results = []

    for symbol, csv_rel in ASSETS.items():
        csv_path = PROJECT_ROOT / csv_rel
        for lookback in LOOKBACKS:
            result = analyze_asset(symbol, csv_path, lookback)
            if result:
                all_results.append(result)

    if not all_results:
        print("\nNo results. Check data files exist.")
        return

    # Print results table
    print(f"\n{'='*70}")
    print(f"{'Symbol':<8} {'LB':>4} {'N':>6} {'IC':>7} {'IC_IR':>7} {'Hit%':>6} {'Early':>6} {'Late':>6} {'Decay':>6} {'Verdict':<15}")
    print(f"{'-'*8} {'-'*4} {'-'*6} {'-'*7} {'-'*7} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*15}")

    for r in all_results:
        decay_flag = "YES" if r["decay_detected"] else "no"
        print(
            f"{r['symbol']:<8} {r['lookback']:>4} {r['n_obs']:>6} "
            f"{r['mean_ic']:>7.4f} {r['ic_ir']:>7.2f} {r['ic_hit_rate']:>5.1%} "
            f"{r['decay_sharpe_early']:>6.2f} {r['decay_sharpe_late']:>6.2f} {decay_flag:>6} "
            f"{r['verdict']:<15}"
        )

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")

    n_proceed = sum(1 for r in all_results if r["verdict"] == "PROCEED")
    n_conditional = sum(1 for r in all_results if r["verdict"] == "CONDITIONAL")
    n_no_go = sum(1 for r in all_results if r["verdict"] == "NO_GO")

    print(f"Total combinations: {len(all_results)}")
    print(f"  PROCEED (edge confirmed): {n_proceed}")
    print(f"  CONDITIONAL (edge marginal): {n_conditional}")
    print(f"  NO_GO (edge not confirmed): {n_no_go}")

    # Best result
    best = max(all_results, key=lambda r: abs(r["ic_ir"]))
    print(f"\nBest IC IR: {best['symbol']} {best['lookback']}d = {best['ic_ir']:.2f}")

    # Worst IC
    worst_ic = min(all_results, key=lambda r: r["mean_ic"])
    print(f"Worst IC: {worst_ic['symbol']} {worst_ic['lookback']}d = {worst_ic['mean_ic']:.4f}")

    # Alpha decay
    n_decay = sum(1 for r in all_results if r["decay_detected"])
    print(f"Alpha decay detected: {n_decay}/{len(all_results)} combinations")

    # Decision gate
    print(f"\n{'='*70}")
    print("DECISION GATE")
    print(f"{'='*70}")

    gate_results = [r for r in all_results if r["ic_ir"] >= 0.5 and r["mean_ic"] >= 0.02]
    if gate_results:
        print("[PASS] IC mean > 0.02 AND IC IR > 0.5")
        print("   Edge confirmed - proceed to paper trading")
    else:
        print("[FAIL] No combination passed IC mean > 0.02 AND IC IR > 0.5")
        print("   Edge NOT confirmed - do NOT trade live")

    # Save results to CSV
    results_df = pd.DataFrame(all_results)
    output_path = PROJECT_ROOT / "reports" / "tsm_ic_analysis.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    results_df.to_csv(output_path, index=False)
    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
