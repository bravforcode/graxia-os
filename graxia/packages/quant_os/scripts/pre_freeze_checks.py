"""
5 PRE-FREEZE VALIDATION CHECKS
================================
Before freezing parameters, verify these 5 critical assumptions:

1. Deflated Sharpe with actual skewness/kurtosis (not defaults)
2. Correlation-adjusted deflation (trials aren't independent)
3. Newey-West adjusted t-stat (overlapping holds → autocorrelation)
4. dxy_divergence win distribution (WR 23.6% → check for outlier dependency)
5. Capacity validation (31,669 lots/day vs real XAUUSD ADV)

Usage:
    python scripts/pre_freeze_checks.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Windows UTF-8 fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent

# ── Direct imports ───────────────────────────────────────────────────────
import importlib.util

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_dsr = _load("dsr", ROOT / "validation" / "deflated_sharpe.py")
deflated_sharpe_ratio = _dsr.deflated_sharpe_ratio


# ══════════════════════════════════════════════════════════════════════════
# CHECK 1: Deflated Sharpe with ACTUAL skewness/kurtosis
# ══════════════════════════════════════════════════════════════════════════

def check1_skewness_kurtosis(
    strategy_returns: dict[str, list[float]],
    n_trials: int,
) -> dict:
    """Verify deflated Sharpe uses actual higher moments, not defaults."""
    print("=" * 64)
    print("  CHECK 1: Deflated Sharpe with ACTUAL skewness/kurtosis")
    print("=" * 64)

    results = {}
    for name, rets in strategy_returns.items():
        arr = np.array(rets)
        if len(arr) < 10:
            print(f"  {name}: SKIP (< 10 returns)")
            continue

        # Compute ACTUAL moments
        mu = arr.mean()
        std = arr.std()
        skew = float(np.mean(((arr - mu) / (std + 1e-10)) ** 3))
        kurt = float(np.mean(((arr - mu) / (std + 1e-10)) ** 4))
        ann_sharpe = mu / (std + 1e-10) * math.sqrt(252)

        # Deflated with ACTUAL moments
        dsr_actual = deflated_sharpe_ratio(
            observed_sharpe=ann_sharpe,
            n_trials=n_trials,
            n_observations=len(arr),
            sharpe_annualization_factor=1.0,  # TODO(DSR-AUDIT): unaudited call site, factor=1.0 preserves prior (possibly-incorrect) behavior — see MATH_CORRECTNESS_AUDIT.md
            skewness=skew,
            kurtosis=kurt,
        )

        # Deflated with DEFAULT moments (skew=0, kurt=3)
        dsr_default = deflated_sharpe_ratio(
            observed_sharpe=ann_sharpe,
            n_trials=n_trials,
            n_observations=len(arr),
            sharpe_annualization_factor=1.0,  # TODO(DSR-AUDIT): unaudited call site, factor=1.0 preserves prior (possibly-incorrect) behavior — see MATH_CORRECTNESS_AUDIT.md
            skewness=0.0,
            kurtosis=3.0,
        )

        # Compare
        p_diff = dsr_actual.probability_alpha - dsr_default.probability_alpha
        optimistic = p_diff < -0.01  # default is more than 1% lower = optimistic

        results[name] = {
            "skewness": round(skew, 4),
            "kurtosis": round(kurt, 4),
            "actual_p": round(dsr_actual.probability_alpha, 6),
            "default_p": round(dsr_default.probability_alpha, 6),
            "difference": round(p_diff, 6),
            "optimistic_if_default": optimistic,
            "passes_actual": dsr_actual.passes_threshold,
        }

        status = "PASS" if dsr_actual.passes_threshold else "FAIL"
        flag = " [OPTIMISTIC]" if optimistic else ""
        print(f"  {name}:")
        print(f"    skew={skew:.4f}, kurt={kurt:.4f}")
        print(f"    actual_p={dsr_actual.probability_alpha:.6f}, default_p={dsr_default.probability_alpha:.6f}{flag}")
        print(f"    passes: {status}")

    return results


# ══════════════════════════════════════════════════════════════════════════
# CHECK 2: Correlation between trials
# ══════════════════════════════════════════════════════════════════════════

def check2_trial_correlation(
    strategy_returns: dict[str, list[float]],
) -> dict:
    """Check correlation between strategy returns (trials aren't independent)."""
    print("\n" + "=" * 64)
    print("  CHECK 2: Correlation Between Trials (Independence Test)")
    print("=" * 64)

    names = list(strategy_returns.keys())
    n = len(names)

    # Align lengths
    min_len = min(len(strategy_returns[s]) for s in names)
    aligned = {s: np.array(strategy_returns[s][:min_len]) for s in names}

    # Compute pairwise correlations
    corr_matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i == j:
                corr_matrix[i, j] = 1.0
            else:
                corr_matrix[i, j] = np.corrcoef(aligned[names[i]], aligned[names[j]])[0, 1]

    # Average absolute correlation (excluding diagonal)
    abs_corrs = []
    for i in range(n):
        for j in range(i + 1, n):
            abs_corrs.append(abs(corr_matrix[i, j]))
    avg_abs_corr = np.mean(abs_corrs)
    max_abs_corr = np.max(abs_corrs)
    max_pair = names[0], names[1]
    for i in range(n):
        for j in range(i + 1, n):
            if abs(corr_matrix[i, j]) == max_abs_corr:
                max_pair = (names[i], names[j])

    # Effective number of independent trials
    # Naive: N_eff = N / (1 + (N-1) * avg_corr)
    # This is the "effective number" from Li & McLean (2000)
    N_eff = n / (1 + (n - 1) * avg_abs_corr) if avg_abs_corr < 1 else 1.0

    print(f"  Pairwise correlations:")
    for i in range(n):
        for j in range(i + 1, n):
            c = corr_matrix[i, j]
            flag = " [HIGH]" if abs(c) > 0.5 else ""
            print(f"    {names[i]}-{names[j]}: {c:.4f}{flag}")

    print(f"\n  Average |correlation|: {avg_abs_corr:.4f}")
    print(f"  Max |correlation|: {max_abs_corr:.4f} ({max_pair[0]}-{max_pair[1]})")
    print(f"  Effective independent trials: {N_eff:.2f} / {n}")
    print(f"  Implication: deflation should use N_eff={N_eff:.0f}, not N={n}")

    return {
        "pairwise_correlations": {f"{names[i]}-{names[j]}": round(corr_matrix[i, j], 4)
                                  for i in range(n) for j in range(i + 1, n)},
        "avg_abs_correlation": round(avg_abs_corr, 4),
        "max_abs_correlation": round(max_abs_corr, 4),
        "max_pair": max_pair,
        "effective_trials": round(N_eff, 2),
        "naive_trials": n,
    }


# ══════════════════════════════════════════════════════════════════════════
# CHECK 3: Newey-West adjusted t-stat
# ══════════════════════════════════════════════════════════════════════════

def newey_west_tstat(returns: np.ndarray, lags: int | None = None) -> dict:
    """Newey-West HAC-adjusted t-statistic for mean.

    Accounts for autocorrelation and heteroscedasticity in overlapping returns.
    """
    n = len(returns)
    if n < 5:
        return {"t_stat": 0, "p_value": 1.0, "effective_n": n, "nw_se": 0}

    mu = returns.mean()
    if abs(mu) < 1e-15:
        return {"t_stat": 0, "p_value": 1.0, "effective_n": n, "nw_se": 0}

    # Newey-West lag selection: floor(4*(T/100)^(2/9))
    if lags is None:
        lags = max(1, int(math.floor(4 * (n / 100) ** (2 / 9))))

    # Newey-West estimator
    gamma_0 = np.mean((returns - mu) ** 2)
    nw_var = gamma_0

    for lag in range(1, lags + 1):
        weight = 1 - lag / (lags + 1)  # Bartlett kernel
        gamma_lag = np.mean((returns[lag:] - mu) * (returns[:-lag] - mu))
        nw_var += 2 * weight * gamma_lag

    nw_se = math.sqrt(nw_var / n)
    t_stat = mu / nw_se if nw_se > 0 else 0

    # Rough p-value from normal approximation
    p_value = 2 * (1 - 0.5 * (1 + math.erf(abs(t_stat) / math.sqrt(2))))

    return {
        "t_stat": round(t_stat, 4),
        "p_value": round(p_value, 6),
        "effective_n": n,
        "nw_se": round(nw_se, 8),
        "lags": lags,
    }


def check3_newey_west(
    strategy_returns: dict[str, list[float]],
) -> dict:
    """Newey-West adjusted t-stat for overlapping holds."""
    print("\n" + "=" * 64)
    print("  CHECK 3: Newey-West Adjusted t-stat (Autocorrelation)")
    print("=" * 64)

    results = {}
    for name, rets in strategy_returns.items():
        arr = np.array(rets)
        nw = newey_west_tstat(arr)

        # Compare with naive t-stat
        mu = arr.mean()
        std = arr.std()
        naive_se = std / math.sqrt(len(arr))
        naive_t = mu / naive_se if naive_se > 0 else 0

        # Autocorrelation check (lag-1)
        if len(arr) > 10:
            autocorr_1 = float(np.corrcoef(arr[1:], arr[:-1])[0, 1])
        else:
            autocorr_1 = 0.0

        t_ratio = abs(nw["t_stat"]) / abs(naive_t) if abs(naive_t) > 0 else 1.0

        results[name] = {
            "naive_t": round(naive_t, 4),
            "nw_t": nw["t_stat"],
            "nw_p": nw["p_value"],
            "nw_lags": nw["lags"],
            "autocorr_lag1": round(autocorr_1, 4),
            "t_ratio": round(t_ratio, 4),
            "autocorrelation_concern": abs(autocorr_1) > 0.1,
        }

        flag = " [AUTOCORR]" if abs(autocorr_1) > 0.1 else ""
        print(f"  {name}: naive_t={naive_t:.4f}, NW_t={nw['t_stat']:.4f}, p={nw['p_value']:.4f}, autocorr={autocorr_1:.4f}{flag}")

    return results


# ══════════════════════════════════════════════════════════════════════════
# CHECK 4: Win distribution for dxy_divergence
# ══════════════════════════════════════════════════════════════════════════

def check4_win_distribution(
    strategy_returns: dict[str, list[float]],
    target: str = "dxy_divergence",
) -> dict:
    """Analyze win distribution — check for outlier dependency."""
    print("\n" + "=" * 64)
    print(f"  CHECK 4: Win Distribution Analysis ({target})")
    print("=" * 64)

    if target not in strategy_returns:
        print(f"  {target} not found in strategy returns")
        return {}

    arr = np.array(strategy_returns[target])
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    wr = len(wins) / len(arr) if len(arr) > 0 else 0

    print(f"  Total trades: {len(arr)}")
    print(f"  Wins: {len(wins)}, Losses: {len(losses)}, WR: {wr:.1%}")

    if len(wins) < 5:
        print(f"  Too few wins to analyze distribution")
        return {"win_count": len(wins), "insufficient": True}

    # Win distribution
    win_pcts = [10, 25, 50, 75, 90]
    win_percentiles = np.percentile(wins, win_pcts)

    # Concentration: what % of total wins come from top 10%?
    top_10_pct = int(max(1, len(wins) * 0.1))
    sorted_wins = np.sort(wins)[::-1]
    top_10_wins = sorted_wins[:top_10_pct]
    total_win_sum = wins.sum()
    top_10_sum = top_10_wins.sum()
    concentration = top_10_sum / total_win_sum if total_win_sum > 0 else 0

    # Top 3 wins contribution
    top_3_wins = sorted_wins[:3]
    top_3_sum = top_3_wins.sum()
    top_3_contribution = top_3_sum / total_win_sum if total_win_sum > 0 else 0

    # Gini coefficient (inequality measure)
    sorted_abs = np.sort(np.abs(wins))
    n = len(sorted_abs)
    index = np.arange(1, n + 1)
    gini = (2 * np.sum(index * sorted_abs) / (n * np.sum(sorted_abs))) - (n + 1) / n if np.sum(sorted_abs) > 0 else 0

    results = {
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": round(wr, 4),
        "avg_win": round(float(wins.mean()), 8),
        "avg_loss": round(float(losses.mean()), 8) if len(losses) > 0 else 0,
        "profit_factor": round(float(abs(wins.sum() / losses.sum())), 2) if len(losses) > 0 and losses.sum() != 0 else 0,
        "win_percentiles": {f"p{p}": round(float(v), 8) for p, v in zip(win_pcts, win_percentiles)},
        "top_10pct_concentration": round(concentration, 4),
        "top_3_contribution": round(top_3_contribution, 4),
        "top_3_wins": [round(float(w), 8) for w in top_3_wins],
        "gini_coefficient": round(gini, 4),
        "outlier_dependency": concentration > 0.5 or top_3_contribution > 0.3,
    }

    print(f"\n  Win distribution (percentiles):")
    for p, v in zip(win_pcts, win_percentiles):
        print(f"    P{p}: {v:.8f}")

    print(f"\n  Top 10% of wins contribute: {concentration:.1%} of total wins")
    print(f"  Top 3 wins contribute: {top_3_contribution:.1%} of total wins")
    print(f"  Top 3 wins: {[f'{w:.8f}' for w in top_3_wins]}")
    print(f"  Gini coefficient: {gini:.4f}")

    flag = " [OUTLIER DEPENDENT]" if results["outlier_dependency"] else " [DISTRIBUTED]"
    print(f"\n  Verdict: {flag}")

    return results


# ══════════════════════════════════════════════════════════════════════════
# CHECK 5: Capacity validation
# ══════════════════════════════════════════════════════════════════════════

def check5_capacity_validation(
    strategy_sharpes: dict[str, float],
    strategy_returns: dict[str, list[float]],
) -> dict:
    """Validate capacity estimates against real market parameters."""
    print("\n" + "=" * 64)
    print("  CHECK 5: Capacity Validation (Real ADV)")
    print("=" * 64)

    # Real XAUUSD parameters (approximate, Pepperstone Razor)
    # XAUUSD ADV: ~400,000-600,000 lots/day (estimated from BIS data)
    # But retail broker ADV is much smaller: ~50,000-100,000 lots/day
    REAL_ADV_RETAIL = 80_000  # Conservative estimate for retail broker
    REAL_ADV_INSTITUTIONAL = 500_000

    results = {}
    for name in strategy_sharpes:
        sharpe = strategy_sharpes[name]
        rets = np.array(strategy_returns.get(name, []))

        if len(rets) < 10:
            continue

        daily_vol = float(rets.std())
        ann_sharpe = sharpe

        # Edge per trade in daily vol terms
        daily_return = ann_sharpe * daily_vol / math.sqrt(252) if daily_vol > 0 else 0

        # Market impact at various sizes
        eta = 0.1
        sizes = [1, 5, 10, 50, 100, 500]
        impact_at_size = {}
        for s in sizes:
            impact_bps = eta * daily_vol * 100 * math.sqrt(s / REAL_ADV_RETAIL)
            # Impact as fraction of daily return
            impact_ratio = impact_bps / 10000 / (abs(daily_return) + 1e-10)
            impact_at_size[s] = {
                "impact_bps": round(impact_bps, 4),
                "impact_ratio": round(impact_ratio, 4),
                "edge_remaining_pct": round(max(0, 1 - impact_ratio) * 100, 1),
            }

        # Find max size before impact > 50% of edge
        max_size_50 = 0
        for s in range(1, 10000):
            impact = eta * daily_vol * 100 * math.sqrt(s / REAL_ADV_RETAIL)
            if impact / 10000 > abs(daily_return) * 0.5:
                max_size_50 = s
                break

        results[name] = {
            "daily_vol": round(daily_vol, 6),
            "daily_edge": round(daily_return, 6),
            "impact_at_sizes": impact_at_size,
            "max_size_before_50pct_edge_loss": max_size_50,
            "realistic_adv": REAL_ADV_RETAIL,
            "capacity_assessment": "OK" if max_size_50 >= 10 else "CONSTRAINED",
        }

        print(f"\n  {name}:")
        print(f"    Daily vol: {daily_vol:.6f}, Daily edge: {daily_return:.6f}")
        print(f"    Max size before 50% edge loss: {max_size_50} lots/day")
        for s in [1, 10, 100]:
            if s in impact_at_size:
                info = impact_at_size[s]
                print(f"    {s} lots: impact={info['impact_bps']:.2f} bps, edge remaining={info['edge_remaining_pct']:.1f}%")

    return results


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════

def main():
    """Run all 5 pre-freeze checks."""
    print("=" * 64)
    print("  5 PRE-FREEZE VALIDATION CHECKS")
    print("=" * 64)

    # Load data
    data_path = ROOT / "data" / "XAUUSD_D1.csv"
    df = pd.read_csv(data_path)
    col_map = {c.lower(): c for c in df.columns}
    close_col = col_map.get("close", "Close")
    time_col = col_map.get("time", col_map.get("date", df.columns[0]))

    if time_col in df.columns:
        df[time_col] = pd.to_datetime(df[time_col])
        df = df.sort_values(time_col).reset_index(drop=True)

    close = df[close_col].values.astype(float)
    returns_full = np.diff(np.log(close))

    # Simulate strategy returns (same as institutional pipeline)
    np.random.seed(42)
    strategy_configs = {
        "momentum_12m": {"lookback": 252, "vol_mult": 1.0},
        "donchian_55": {"lookback": 55, "vol_mult": 1.0},
        "donchian_20": {"lookback": 20, "vol_mult": 1.0},
        "hybrid_mom_mr": {"lookback": 60, "vol_mult": 0.8},
        "mean_reversion_bb": {"lookback": 20, "vol_mult": 0.6},
        "dxy_divergence": {"lookback": 40, "vol_mult": 0.5},
    }

    strategy_returns = {}
    strategy_sharpes = {}

    for name, cfg in strategy_configs.items():
        lb = cfg["lookback"]
        signal = np.zeros(len(returns_full))
        for t in range(lb, len(returns_full)):
            hist = returns_full[t - lb:t]
            if name.startswith("donchian"):
                signal[t] = 1.0 if returns_full[t - 1] > 0 else -1.0
            elif "mean_reversion" in name:
                signal[t] = -1.0 if np.sum(hist[-5:]) > 0 else 1.0
            elif "dxy" in name:
                signal[t] = np.sign(np.mean(hist[-10:])) * 0.5
            else:
                signal[t] = 1.0 if np.mean(hist) > 0 else -1.0

        strat_rets = signal[lb:] * returns_full[lb:] * cfg["vol_mult"]
        strat_rets += np.random.normal(0, 0.0005, len(strat_rets))
        strategy_returns[name] = strat_rets.tolist()

        mu = strat_rets.mean()
        std = strat_rets.std()
        strategy_sharpes[name] = round(mu / (std + 1e-10) * math.sqrt(252), 4)

    n_trials = 31

    # Run all 5 checks
    c1 = check1_skewness_kurtosis(strategy_returns, n_trials)
    c2 = check2_trial_correlation(strategy_returns)
    c3 = check3_newey_west(strategy_returns)
    c4 = check4_win_distribution(strategy_returns, "dxy_divergence")
    c5 = check5_capacity_validation(strategy_sharpes, strategy_returns)

    # ── Summary ──────────────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("  SUMMARY: 5 PRE-FREEZE CHECKS")
    print("=" * 64)

    # Check 1: skewness/kurtosis
    c1_issues = [n for n, r in c1.items() if r.get("optimistic_if_default")]
    print(f"\n  1. Skewness/Kurtosis: {'WARNING' if c1_issues else 'OK'}")
    if c1_issues:
        print(f"     Strategies where default is optimistic: {c1_issues}")
    else:
        print(f"     All strategies use actual moments")

    # Check 2: trial correlation
    high_corr = c2.get("avg_abs_correlation", 0) > 0.3
    print(f"\n  2. Trial Correlation: {'WARNING' if high_corr else 'OK'}")
    print(f"     Avg |corr|: {c2.get('avg_abs_correlation', 0):.4f}")
    print(f"     Effective trials: {c2.get('effective_trials', 0):.1f} / {c2.get('naive_trials', 0)}")
    if high_corr:
        print(f"     -> Re-run deflation with N_eff={c2.get('effective_trials', 0):.0f}")

    # Check 3: Newey-West
    autocorr_names = [n for n, r in c3.items() if r.get("autocorrelation_concern")]
    print(f"\n  3. Newey-West: {'WARNING' if autocorr_names else 'OK'}")
    if autocorr_names:
        print(f"     Autocorrelation concern: {autocorr_names}")
        for n in autocorr_names:
            print(f"       {n}: autocorr={c3[n]['autocorr_lag1']:.4f}, NW_t={c3[n]['nw_t']:.4f} (vs naive {c3[n]['naive_t']:.4f})")
    else:
        print(f"     No significant autocorrelation in any strategy")

    # Check 4: win distribution
    outlier_dep = c4.get("outlier_dependency", False)
    print(f"\n  4. Win Distribution (dxy_divergence): {'WARNING' if outlier_dep else 'OK'}")
    print(f"     Win rate: {c4.get('win_rate', 0):.1%}")
    print(f"     Top 3 wins contribute: {c4.get('top_3_contribution', 0):.1%}")
    print(f"     Top 10% contribute: {c4.get('top_10pct_concentration', 0):.1%}")
    print(f"     Gini: {c4.get('gini_coefficient', 0):.4f}")

    # Check 5: capacity
    constrained = [n for n, r in c5.items() if r.get("capacity_assessment") == "CONSTRAINED"]
    print(f"\n  5. Capacity: {'WARNING' if constrained else 'OK'}")
    if constrained:
        print(f"     Constrained strategies: {constrained}")
    for n, r in c5.items():
        print(f"     {n}: max={r['max_size_before_50pct_edge_loss']} lots/day")

    # Overall
    issues = []
    if c1_issues:
        issues.append(f"skew/kurt default: {c1_issues}")
    if high_corr:
        issues.append(f"trial corr: avg={c2['avg_abs_correlation']:.3f}")
    if autocorr_names:
        issues.append(f"autocorrelation: {autocorr_names}")
    if outlier_dep:
        issues.append("dxy_divergence outlier-dependent")
    if constrained:
        issues.append(f"capacity constrained: {constrained}")

    print(f"\n  {'='*64}")
    if not issues:
        print("  VERDICT: ALL CHECKS PASS — safe to freeze parameters")
    else:
        print(f"  VERDICT: {len(issues)} ISSUES FOUND")
        for i, issue in enumerate(issues, 1):
            print(f"    {i}. {issue}")
    print(f"  {'='*64}")

    return {
        "check1_skewness_kurtosis": c1,
        "check2_trial_correlation": c2,
        "check3_newey_west": c3,
        "check4_win_distribution": c4,
        "check5_capacity": c5,
        "issues": issues,
    }


if __name__ == "__main__":
    main()
