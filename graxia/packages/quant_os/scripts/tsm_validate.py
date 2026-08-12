"""
Phase 3: Statistical Validation — Walk-Forward + PBO for TSM Strategy.

Implements:
  1. Expanding-window walk-forward validation (60/20/20 split)
  2. Rolling-window walk-forward (500-day train, 200-day test)
  3. PBO via Combinatorial Symmetric Cross-Validation (CSCV)
  4. Deflated Sharpe ratio (Bailey & Lopez de Prado 2014)
  5. Multi-lookback testing: 20, 40, 60, 120 days

Signal: sign(lookback_return) — simplest TSM, fewest params.
target_vol = 0.10, cost = 5 bps, weekly rebalance.

Usage:
    python scripts/tsm_validate.py
"""

import json
import itertools
import warnings
from pathlib import Path
from datetime import datetime, UTC

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)

BASE = Path(__file__).resolve().parent.parent
ARTIFACTS = BASE / "artifacts" / "portfolio"
ARTIFACTS.mkdir(parents=True, exist_ok=True)

# ── Config ──────────────────────────────────────────────────────────────
TARGET_VOL = 0.10
COST_BPS = 5
LOOKBACK_WINDOWS = [20, 40, 60, 120]
REBALANCE_FREQ = "W-FRI"
ASSETS = [
    "XAUUSD", "EURUSD_YF", "GBPUSD_YF", "USDJPY",
    "BTC_YF", "ETH_YF", "SILVER", "OIL",
]
N_CSCV_SUBSETS = 10  # S = 10, use S/2 = 5 for train/test


# ── Data Loading ────────────────────────────────────────────────────────

def load_data() -> pd.DataFrame:
    path = ARTIFACTS / "d1_multi_asset.parquet"
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index, utc=True)
    return df.sort_index()


# ── Signal & Backtest ───────────────────────────────────────────────────

def compute_tsm_signal(close: pd.Series, lookback: int) -> pd.Series:
    """TSM signal: sign of lookback-period return."""
    ret = close.pct_change(lookback, fill_method=None)
    return np.sign(ret)


def backtest_single_asset(
    close: pd.Series, lookback: int, target_vol: float, cost_bps: float
) -> pd.DataFrame:
    """Backtest TSM on a single asset. Returns daily strategy returns."""
    df = pd.DataFrame({"close": close})
    df["ret"] = df["close"].pct_change(1, fill_method=None)

    # Signal & vol-targeted weight
    signal = compute_tsm_signal(close, lookback)
    rvol = df["ret"].rolling(20).std() * np.sqrt(252)
    rvol = rvol.replace(0, np.nan)
    weight = signal * target_vol / rvol
    weight = weight.clip(-1, 1)

    # Weekly rebalance
    weekly_w = weight.resample(REBALANCE_FREQ).last()
    weekly_w = weekly_w.reindex(df.index, method="ffill")
    df["weight"] = weekly_w

    # Strategy return (lagged weight)
    df["strat_ret"] = df["weight"].shift(1) * df["ret"]

    # Transaction costs
    df["wchange"] = df["weight"].diff().abs()
    df["cost"] = df["wchange"] * cost_bps / 10_000
    df["strat_ret_net"] = df["strat_ret"] - df["cost"]

    return df


def portfolio_backtest(
    data: pd.DataFrame, assets: list, lookback: int,
    target_vol: float, cost_bps: float
) -> pd.Series:
    """Multi-asset TSM portfolio with inverse-vol weighting. Returns portfolio daily returns."""
    asset_rets = {}
    for asset in assets:
        col = f"{asset}_close"
        if col not in data.columns:
            continue
        close = data[col].dropna()
        if len(close) < lookback + 60:
            continue
        bt = backtest_single_asset(close, lookback, target_vol, cost_bps)
        asset_rets[asset] = bt["strat_ret_net"]

    if not asset_rets:
        return pd.Series(dtype=float)

    ret_df = pd.DataFrame(asset_rets)

    # Inverse-vol weighting
    rvol = ret_df.rolling(60).std()
    inv_rvol = 1.0 / rvol.replace(0, np.nan)
    inv_rvol = inv_rvol.div(inv_rvol.sum(axis=1), axis=0)

    portfolio_ret = (ret_df * inv_rvol).sum(axis=1)
    return portfolio_ret.dropna()


# ── Metrics ─────────────────────────────────────────────────────────────

def sharpe_ratio(ret: pd.Series) -> float:
    """Annualized Sharpe ratio."""
    ret = ret.dropna()
    if len(ret) < 30:
        return np.nan
    ann_ret = ret.mean() * 252
    ann_vol = ret.std() * np.sqrt(252)
    return ann_ret / ann_vol if ann_vol > 0 else 0.0


def compute_metrics(ret: pd.Series) -> dict:
    """Full metrics for a return series."""
    ret = ret.dropna()
    if len(ret) < 30:
        return {"sharpe": np.nan, "ann_ret": np.nan, "ann_vol": np.nan,
                "max_dd": np.nan, "win_rate": np.nan, "n_days": len(ret)}
    ann_ret = ret.mean() * 252
    ann_vol = ret.std() * np.sqrt(252)
    sr = ann_ret / ann_vol if ann_vol > 0 else 0.0
    cum = (1 + ret).cumprod()
    max_dd = ((cum - cum.cummax()) / cum.cummax()).min()
    return {
        "sharpe": sr,
        "ann_ret": ann_ret,
        "ann_vol": ann_vol,
        "max_dd": max_dd,
        "win_rate": (ret > 0).mean(),
        "n_days": len(ret),
    }


# ── Walk-Forward Validation ────────────────────────────────────────────

def expanding_walk_forward(
    data: pd.DataFrame, assets: list, lookback: int,
    target_vol: float, cost_bps: float,
    train_pct: float = 0.6, test_pct: float = 0.2
) -> dict:
    """Expanding-window WF: train on first 60%, test on next 20%, validate on last 20%."""
    n = len(data)
    train_end = int(n * train_pct)
    test_end = int(n * (train_pct + test_pct))

    slices = {
        "train": data.iloc[:train_end],
        "test": data.iloc[train_end:test_end],
        "validate": data.iloc[test_end:],
    }

    results = {}
    for name, sl in slices.items():
        ret = portfolio_backtest(sl, assets, lookback, target_vol, cost_bps)
        m = compute_metrics(ret)
        results[name] = m

    return results


def rolling_walk_forward(
    data: pd.DataFrame, assets: list, lookback: int,
    target_vol: float, cost_bps: float,
    train_window: int = 500, test_window: int = 200
) -> dict:
    """Rolling-window walk-forward: 500-day train, 200-day test, rolling forward."""
    n = len(data)
    folds = []
    fold_idx = 0
    start = 0

    while start + train_window + test_window <= n:
        train_data = data.iloc[start:start + train_window]
        test_data = data.iloc[start + train_window:start + train_window + test_window]

        train_ret = portfolio_backtest(train_data, assets, lookback, target_vol, cost_bps)
        test_ret = portfolio_backtest(test_data, assets, lookback, target_vol, cost_bps)

        train_sr = sharpe_ratio(train_ret)
        test_sr = sharpe_ratio(test_ret)

        folds.append({
            "fold": fold_idx,
            "train_start": str(train_data.index[0].date()),
            "train_end": str(train_data.index[-1].date()),
            "test_start": str(test_data.index[0].date()),
            "test_end": str(test_data.index[-1].date()),
            "train_sharpe": train_sr,
            "test_sharpe": test_sr,
            "train_n": len(train_ret),
            "test_n": len(test_ret),
        })

        fold_idx += 1
        start += test_window  # step forward by test_window

    # Summary
    if not folds:
        return {"folds": [], "summary": {}}

    train_sharpes = [f["train_sharpe"] for f in folds if not np.isnan(f["train_sharpe"])]
    test_sharpes = [f["test_sharpe"] for f in folds if not np.isnan(f["test_sharpe"])]

    summary = {
        "n_folds": len(folds),
        "mean_train_sharpe": np.mean(train_sharpes) if train_sharpes else np.nan,
        "mean_test_sharpe": np.mean(test_sharpes) if test_sharpes else np.nan,
        "std_test_sharpe": np.std(test_sharpes) if test_sharpes else np.nan,
        "min_test_sharpe": np.min(test_sharpes) if test_sharpes else np.nan,
        "max_test_sharpe": np.max(test_sharpes) if test_sharpes else np.nan,
        "stability": (np.mean(test_sharpes) / np.std(test_sharpes)
                      if test_sharpes and np.std(test_sharpes) > 0 else np.nan),
        "train_test_corr": (np.corrcoef(train_sharpes, test_sharpes)[0, 1]
                            if len(train_sharpes) == len(test_sharpes) and len(train_sharpes) > 1
                            else np.nan),
    }

    return {"folds": folds, "summary": summary}


# ── PBO via CSCV ───────────────────────────────────────────────────────

def pbo_cscv(
    data: pd.DataFrame, assets: list, lookbacks: list,
    target_vol: float, cost_bps: float, n_subsets: int = 10
) -> dict:
    """
    Probability of Backtest Overfitting via Combinatorial Symmetric CV.
    
    Bailey, Borwein, Lopez de Prado, Zhu (2014):
    1. Split data into S equal subsets.
    2. For each combination of S/2 subsets as in-sample (C(S, S/2) combos):
       a. Remaining S/2 subsets = out-of-sample.
       b. For each lookback, compute in-sample Sharpe.
       c. Find the lookback with highest in-sample Sharpe (best config).
       d. Check if that config is worst out-of-sample.
    3. PBO = fraction of combinations where in-sample best is OOS worst.
    
    Returns PBO and per-combination details.
    """
    n = len(data)
    subset_size = n // n_subsets
    # Trim to exact multiple
    usable_n = subset_size * n_subsets
    data_trimmed = data.iloc[:usable_n]

    # Pre-compute returns for each lookback on each subset
    # subset_returns[lb_idx][subset_idx] = Series of daily returns
    print(f"  CSCV: {n_subsets} subsets, {subset_size} days each, "
          f"{len(lookbacks)} lookbacks, C({n_subsets},{n_subsets//2})="
          f"{len(list(itertools.combinations(range(n_subsets), n_subsets//2)))} combos")

    subset_returns = {}
    for lb_idx, lb in enumerate(lookbacks):
        subset_returns[lb_idx] = {}
        for s in range(n_subsets):
            s_start = s * subset_size
            s_end = s_start + subset_size
            subset_data = data_trimmed.iloc[s_start:s_end]
            ret = portfolio_backtest(subset_data, assets, lb, target_vol, cost_bps)
            subset_returns[lb_idx][s] = ret

    # For each combination of S/2 subsets
    half = n_subsets // 2
    all_combos = list(itertools.combinations(range(n_subsets), half))
    n_overfit = 0
    n_valid = 0
    combo_details = []

    for combo in all_combos:
        in_sample_subs = set(combo)
        out_sample_subs = set(range(n_subsets)) - in_sample_subs

        # Compute in-sample and OOS Sharpe for each lookback
        is_sharpes = {}
        oos_sharpes = {}

        for lb_idx, lb in enumerate(lookbacks):
            # Concatenate in-sample subsets
            is_ret_parts = [subset_returns[lb_idx][s] for s in sorted(in_sample_subs)
                           if len(subset_returns[lb_idx][s]) > 0]
            oos_ret_parts = [subset_returns[lb_idx][s] for s in sorted(out_sample_subs)
                             if len(subset_returns[lb_idx][s]) > 0]

            if is_ret_parts:
                is_ret = pd.concat(is_ret_parts)
                is_sharpes[lb_idx] = sharpe_ratio(is_ret)
            else:
                is_sharpes[lb_idx] = np.nan

            if oos_ret_parts:
                oos_ret = pd.concat(oos_ret_parts)
                oos_sharpes[lb_idx] = sharpe_ratio(oos_ret)
            else:
                oos_sharpes[lb_idx] = np.nan

        # Find best in-sample config
        valid_lbs = [lb for lb in is_sharpes if not np.isnan(is_sharpes[lb])]
        if len(valid_lbs) < 2:
            continue

        n_valid += 1
        best_is = max(valid_lbs, key=lambda lb: is_sharpes[lb])
        worst_oos = min(valid_lbs, key=lambda lb: oos_sharpes.get(lb, np.nan))

        # Check if in-sample best is OOS worst
        is_overfit = (best_is == worst_oos)
        if is_overfit:
            n_overfit += 1

        combo_details.append({
            "in_sample": sorted(in_sample_subs),
            "best_is_lb": lookbacks[best_is],
            "best_is_sharpe": is_sharpes[best_is],
            "worst_oos_lb": lookbacks[worst_oos],
            "worst_oos_sharpe": oos_sharpes.get(worst_oos, np.nan),
            "overfit": is_overfit,
        })

    pbo = n_overfit / n_valid if n_valid > 0 else np.nan

    return {
        "pbo": pbo,
        "n_combos_total": len(all_combos),
        "n_combos_valid": n_valid,
        "n_overfit": n_overfit,
        "n_subsets": n_subsets,
        "subset_size": subset_size,
        "lookbacks": lookbacks,
    }


# ── Deflated Sharpe Ratio ──────────────────────────────────────────────

def deflated_sharpe_ratio(
    sharpe: float, n_obs: int, n_trials: int,
    skew: float = 0.0, kurtosis: float = 3.0
) -> dict:
    """
    Deflated Sharpe Ratio — Bailey & Lopez de Prado (2014).
    
    Accounts for multiple testing / non-normal returns.
    Uses the expected maximum Sharpe under n_trials independent trials.
    """
    if np.isnan(sharpe) or n_obs < 30:
        return {"dsr": np.nan, "p_value": np.nan, "significant": False}

    # Sharpe standard error (accounting for skew/kurtosis)
    se = np.sqrt(
        (1 + 0.5 * sharpe**2 - skew * sharpe + (kurtosis - 3) / 4 * sharpe**2)
        / (n_obs - 1)
    )
    if se == 0:
        return {"dsr": np.nan, "p_value": np.nan, "significant": False}

    z = sharpe / se

    # Expected max z-score from n_trials random strategies
    # Using inverse of E[max of n_trials standard normals]
    # Approximation: E[max] ≈ sqrt(2 * ln(n_trials)) - (ln(ln(n_trials)) + ln(4π)) / (2 * sqrt(2 * ln(n_trials)))
    if n_trials > 1:
        log_n = np.log(n_trials)
        e_max_z = np.sqrt(2 * log_n) - (np.log(log_n) + np.log(4 * np.pi)) / (2 * np.sqrt(2 * log_n))
    else:
        e_max_z = 0

    # Deflated Sharpe = Sharpe - E[max_SR] * SE
    deflated_sr = sharpe - e_max_z * se

    # P-value: probability that a random strategy would produce Sharpe >= observed
    p_value = 1 - stats.norm.cdf(z)

    # Probability that observed Sharpe is the true best (not overfit)
    # Using the deflated test: compare z to expected max
    p_deflated = 1 - stats.norm.cdf(z - e_max_z)

    return {
        "sharpe": sharpe,
        "deflated_sharpe": deflated_sr,
        "z_score": z,
        "se": se,
        "p_value_single": p_value,
        "p_value_deflated": p_deflated,
        "e_max_z": e_max_z,
        "n_trials": n_trials,
        "significant_5pct": p_deflated > 0.05,  # Higher = better (prob of being real)
    }


# ── Main ────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print(    "PHASE 3: Statistical Validation - Walk-Forward + PBO")
    print("=" * 70)
    print()

    data = load_data()
    print(f"Data: {len(data)} rows, {data.index.min().date()} to {data.index.max().date()}")
    available = [a for a in ASSETS if f"{a}_close" in data.columns]
    print(f"Assets: {available}")
    print()

    all_results = {}

    # ── 1. Per-lookback analysis ────────────────────────────────────────
    for lb in LOOKBACK_WINDOWS:
        print(f"{'-' * 50}")
        print(f"LOOKBACK = {lb} days")
        print(f"{'-' * 50}")

        lb_result = {"lookback": lb}

        # Full-period backtest
        full_ret = portfolio_backtest(data, available, lb, TARGET_VOL, COST_BPS)
        full_metrics = compute_metrics(full_ret)
        lb_result["full_period"] = full_metrics
        print(f"  Full-period Sharpe:  {full_metrics['sharpe']:.3f}")
        print(f"  Full-period Ann Ret: {full_metrics['ann_ret']:.2%}")
        print(f"  Full-period Max DD:  {full_metrics['max_dd']:.2%}")

        # Expanding walk-forward
        expanding_wf = expanding_walk_forward(data, available, lb, TARGET_VOL, COST_BPS)
        lb_result["expanding_wf"] = expanding_wf
        print("\n  Expanding WF:")
        for split in ["train", "test", "validate"]:
            sr = expanding_wf[split]["sharpe"]
            print(f"    {split:>10} Sharpe: {sr:.3f}")

        # Rolling walk-forward
        rolling_wf = rolling_walk_forward(data, available, lb, TARGET_VOL, COST_BPS)
        lb_result["rolling_wf"] = rolling_wf["summary"]
        lb_result["rolling_wf_folds"] = rolling_wf["folds"]
        s = rolling_wf["summary"]
        print("\n  Rolling WF (500/200):")
        print(f"    Folds:              {s.get('n_folds', 0)}")
        print(f"    Mean train Sharpe:  {s.get('mean_train_sharpe', np.nan):.3f}")
        print(f"    Mean test Sharpe:   {s.get('mean_test_sharpe', np.nan):.3f}")
        print(f"    Test Sharpe std:    {s.get('std_test_sharpe', np.nan):.3f}")
        print(f"    Stability:          {s.get('stability', np.nan):.3f}")
        print(f"    Train-Test corr:    {s.get('train_test_corr', np.nan):.3f}")

        # Per-fold detail
        if rolling_wf["folds"]:
            print(f"\n    {'Fold':>4} {'Train SR':>10} {'Test SR':>10} {'Test Period':>25}")
            for f in rolling_wf["folds"]:
                print(f"    {f['fold']:>4} {f['train_sharpe']:>10.3f} "
                      f"{f['test_sharpe']:>10.3f} "
                      f"{f['test_start']:>12} → {f['test_end']}")

        # Deflated Sharpe
        n_configs = len(LOOKBACK_WINDOWS)
        dsr = deflated_sharpe_ratio(
            full_metrics["sharpe"], full_metrics["n_days"], n_configs,
            skew=full_ret.skew(), kurtosis=full_ret.kurtosis()
        )
        lb_result["deflated_sharpe"] = dsr
        print("\n  Deflated Sharpe:")
        print(f"    Sharpe:           {dsr['sharpe']:.3f}")
        print(f"    Deflated Sharpe:  {dsr['deflated_sharpe']:.3f}")
        print(f"    P-value (single): {dsr['p_value_single']:.4f}")
        print(f"    P-value (deflated): {dsr['p_value_deflated']:.4f}")
        print(f"    E[max_z]:         {dsr['e_max_z']:.3f}")
        print(f"    Significant (5%): {'YES' if dsr['significant_5pct'] else 'NO'}")

        all_results[f"lb{lb}"] = lb_result
        print()

    # ── 2. PBO via CSCV ────────────────────────────────────────────────
    print("=" * 70)
    print("PBO — Combinatorial Symmetric Cross-Validation")
    print("=" * 70)
    print()

    pbo_result = pbo_cscv(
        data, available, LOOKBACK_WINDOWS, TARGET_VOL, COST_BPS,
        n_subsets=N_CSCV_SUBSETS
    )
    all_results["pbo"] = pbo_result

    print("\n  PBO Results:")
    print(f"    Subsets (S):     {pbo_result['n_subsets']}")
    print(f"    Subset size:     {pbo_result['subset_size']} days")
    print(f"    Valid combos:    {pbo_result['n_combos_valid']}")
    print(f"    Overfit combos:  {pbo_result['n_overfit']}")
    print(f"    PBO:             {pbo_result['pbo']:.4f} ({pbo_result['pbo']:.1%})")
    print(f"    Lookbacks tested: {pbo_result['lookbacks']}")
    print()

    if pbo_result["pbo"] < 0.20:
        print("    [OK] PBO < 20% -- LOW overfitting risk")
    elif pbo_result["pbo"] < 0.50:
        print("    [!!] PBO 20-50% -- MODERATE overfitting risk")
    else:
        print("    [XX] PBO > 50% -- HIGH overfitting risk")

    # ── 3. Aggregate Deflated Sharpe across all lookbacks ──────────────
    print()
    print("=" * 70)
    print("AGGREGATE: Deflated Sharpe (all lookbacks as trials)")
    print("=" * 70)
    print()

    # Use the best lookback's Sharpe, deflated by number of lookbacks tested
    best_lb = max(LOOKBACK_WINDOWS,
                  key=lambda lb: all_results[f"lb{lb}"]["full_period"]["sharpe"])
    best_metrics = all_results[f"lb{best_lb}"]["full_period"]
    best_ret = portfolio_backtest(data, available, best_lb, TARGET_VOL, COST_BPS)

    agg_dsr = deflated_sharpe_ratio(
        best_metrics["sharpe"], best_metrics["n_days"], len(LOOKBACK_WINDOWS),
        skew=best_ret.skew(), kurtosis=best_ret.kurtosis()
    )
    all_results["aggregate"] = {
        "best_lookback": best_lb,
        **agg_dsr,
    }

    print(f"  Best lookback:     {best_lb} days")
    print(f"  Sharpe:            {agg_dsr['sharpe']:.3f}")
    print(f"  Deflated Sharpe:   {agg_dsr['deflated_sharpe']:.3f}")
    print(f"  P-value (deflated): {agg_dsr['p_value_deflated']:.4f}")
    print(f"  Significant (5%):  {'YES' if agg_dsr['significant_5pct'] else 'NO'}")

    # ── 4. Summary Table ────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("SUMMARY TABLE")
    print("=" * 70)
    print()
    print(f"{'LB':>4} {'Sharpe':>8} {'Deflated':>9} {'Exp Train':>10} {'Exp Test':>9} "
          f"{'Exp Val':>8} {'Roll Train':>11} {'Roll Test':>10} {'Stability':>10}")
    print(f"{'-'*4:>4} {'-'*8:>8} {'-'*9:>9} {'-'*10:>10} {'-'*9:>9} "
          f"{'-'*8:>8} {'-'*11:>11} {'-'*10:>10} {'-'*10:>10}")

    for lb in LOOKBACK_WINDOWS:
        r = all_results[f"lb{lb}"]
        fm = r["full_period"]
        ewf = r["expanding_wf"]
        rwf = r["rolling_wf"]
        dsr = r["deflated_sharpe"]
        print(f"{lb:>4} {fm['sharpe']:>8.3f} {dsr['deflated_sharpe']:>9.3f} "
              f"{ewf['train']['sharpe']:>10.3f} {ewf['test']['sharpe']:>9.3f} "
              f"{ewf['validate']['sharpe']:>8.3f} "
              f"{rwf.get('mean_train_sharpe', np.nan):>11.3f} "
              f"{rwf.get('mean_test_sharpe', np.nan):>10.3f} "
              f"{rwf.get('stability', np.nan):>10.3f}")

    print()
    print(f"PBO: {pbo_result['pbo']:.4f} ({pbo_result['pbo']:.1%})")

    # ── 5. Save results ────────────────────────────────────────────────
    # Convert numpy types for JSON serialization
    def to_serializable(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, pd.Timestamp):
            return str(obj)
        return obj

    def clean_for_json(d):
        if isinstance(d, dict):
            return {k: clean_for_json(v) for k, v in d.items()}
        if isinstance(d, list):
            return [clean_for_json(v) for v in d]
        if isinstance(d, float) and np.isnan(d):
            return None
        return to_serializable(d)

    output = {
        "generated_at": datetime.now(UTC).isoformat(),
        "config": {
            "target_vol": TARGET_VOL,
            "cost_bps": COST_BPS,
            "lookbacks": LOOKBACK_WINDOWS,
            "assets": available,
            "data_rows": len(data),
            "data_range": f"{data.index.min().date()} to {data.index.max().date()}",
        },
        "results": clean_for_json(all_results),
    }

    out_path = ARTIFACTS / "tsm_validation_results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\nResults saved to: {out_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
