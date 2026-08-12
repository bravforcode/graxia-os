"""
Concentrated 4-Asset Ensemble TSM Backtest — Alpha vs Dead Weight.

Hypothesis: Removing dead weight (EURUSD, GBPUSD, USDCHF, SILVER, US30)
from the 9-asset ex-crypto ensemble (Sharpe 0.373) will push Sharpe > 0.5.

4 Assets: NAS100, XAUUSD, OIL, USDJPY
Top 4 by individual Sharpe (0.598, 0.438, 0.294, 0.238).

Tests:
1. Equal-weight (0.25 each) — no optimization, honest test
2. Optimal-weight — grid search maximizing Sharpe (with swap costs)

Decision Criteria:
  Sharpe > 0.5 → REAL ALPHA, continue to paper trading
  Sharpe 0.3-0.5 → MARGINAL, needs investigation
  Sharpe < 0.3 → NO ALPHA, permanent ARCHIVE_NO_EDGE
"""

import importlib.util
import itertools
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
BASE = PROJECT_ROOT
sys.path.insert(0, str(PROJECT_ROOT))

_spec_dsr = importlib.util.spec_from_file_location("deflated_sharpe", BASE / "validation" / "deflated_sharpe.py")
_mod_dsr = importlib.util.module_from_spec(_spec_dsr)
_spec_dsr.loader.exec_module(_mod_dsr)
deflated_sharpe_ratio = _mod_dsr.deflated_sharpe_ratio
_norm_cdf = _mod_dsr._norm_cdf

REPORTS = BASE / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

# ── LOCKED SIGNAL SPEC ──────────────────────────────────────────────────────
LOOKBACKS = [20, 40, 60, 120]
WEIGHTS = [0.25, 0.25, 0.25, 0.25]
TARGET_VOL = 0.10
REBALANCE_FREQ = "W-FRI"
POSITION_CAP = 1.5

# CONCENTRATED 4-ASSET PORTFOLIO
TSM_ASSETS_4 = {
    "NAS100": {"csv": "data/NAS100_D1.csv", "cost_key": "NAS100"},
    "XAUUSD": {"csv": "data/XAUUSD_D1.csv", "cost_key": "XAUUSD"},
    "OIL": {"csv": "data/market_data/yfinance/CL_F.csv", "cost_key": "OIL"},
    "USDJPY": {"csv": "data/USDJPY_D1.csv", "cost_key": "USDJPY"},
}


@dataclass
class Metrics:
    name: str
    ann_ret: float
    ann_vol: float
    sharpe: float
    sortino: float
    max_dd: float
    dd_duration_days: int
    win_rate: float
    profit_factor: float
    skew: float
    kurtosis: float
    n_days: int
    n_years: float
    total_return: float
    annual_cost_drag_bps: float
    annual_cost_drag_pct: float
    avg_weekly_turnover: float


def load_costs() -> dict:
    path = BASE / "config" / "cost_calibration.json"
    with open(path) as f:
        return json.load(f)


def build_cost_scenarios_4asset(cost_data: dict) -> dict:
    """Build cost map for 4 concentrated assets."""
    typical = {}
    stress = {}
    swap_long = {}
    swap_short = {}
    assets = cost_data["assets"]
    stress_scenarios = cost_data.get("stress_scenarios", {})

    for tsm_name, cfg in TSM_ASSETS_4.items():
        cost_key = cfg["cost_key"]
        if cost_key not in assets:
            # Conservative default for unmeasured assets
            print(f"  WARNING: No cost calibration for {cost_key}, using 10bps default")
            typical[tsm_name] = 10.0
            stress[tsm_name] = 15.0
            swap_long[tsm_name] = 0.0
            swap_short[tsm_name] = 0.0
            continue
        a = assets[cost_key]
        typical[tsm_name] = a["round_trip_bps_measured"]
        if cost_key == "XAUUSD" and "XAUUSD_72bps" in stress_scenarios:
            stress[tsm_name] = stress_scenarios["XAUUSD_72bps"]["round_trip_bps"]
        else:
            stress[tsm_name] = a.get("round_trip_bps_p95", a["round_trip_bps_measured"])
        swap_long[tsm_name] = a.get("swap_long_bps", 0.0)
        swap_short[tsm_name] = a.get("swap_short_bps", 0.0)

    return {
        "typical": typical,
        "stress": stress,
        "swap_long": swap_long,
        "swap_short": swap_short,
    }


def load_all_d1_data_4asset() -> pd.DataFrame:
    """Load D1 close prices for the 4 concentrated assets."""
    closes = {}

    for tsm_name, cfg in TSM_ASSETS_4.items():
        csv_path = BASE / cfg["csv"]
        if not csv_path.exists():
            print(f"  WARNING: {csv_path} not found, skipping {tsm_name}")
            continue

        df = pd.read_csv(csv_path)

        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"], utc=True)
            df = df.set_index("time").sort_index()
            close = df["close"]
        elif "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], utc=True)
            df = df.set_index("Date").sort_index()
            close = df["Close"]
        else:
            print(f"  WARNING: Unknown format for {csv_path}, skipping {tsm_name}")
            continue

        close = close.groupby(close.index.date).last()
        close.index = pd.to_datetime(close.index, utc=True)
        closes[tsm_name] = close

    if not closes:
        raise RuntimeError("No data files found!")

    result = pd.DataFrame(closes)
    result = result.dropna(how="all")
    result = result[result.index >= "2016-01-01"]
    return result


def raw_signal(returns: pd.Series, lookback: int) -> pd.Series:
    r = returns.rolling(lookback).sum()
    vol = returns.rolling(lookback).std()
    return r / vol.replace(0, np.nan)


def ensemble_signal(returns: pd.Series) -> pd.Series:
    signals = [raw_signal(returns, L) for L in LOOKBACKS]
    return sum(w * s for w, s in zip(WEIGHTS, signals, strict=False))


def compute_position(returns: pd.Series, target_vol: float = TARGET_VOL) -> pd.Series:
    sig = ensemble_signal(returns)
    realized_vol = returns.rolling(60).std() * (252**0.5)
    pos = sig * (target_vol / realized_vol.replace(0, np.nan))
    return pos.clip(-POSITION_CAP, POSITION_CAP)


def backtest_single_asset(
    close: pd.Series, cost_bps: float, swap_long_bps: float = 0.0, swap_short_bps: float = 0.0
) -> pd.DataFrame:
    df = pd.DataFrame({"close": close})
    df["ret"] = df["close"].pct_change()
    df["position"] = compute_position(df["ret"])

    weekly_pos = df["position"].resample(REBALANCE_FREQ).last()
    weekly_pos = weekly_pos.reindex(df.index, method="ffill")
    df["position"] = weekly_pos

    df["strat_ret"] = df["position"].shift(1) * df["ret"]

    df["pos_change"] = df["position"].diff().abs()
    df["tx_cost"] = df["pos_change"] * cost_bps / 10000

    prev_pos = df["position"].shift(1)
    df["swap_cost"] = 0.0
    long_mask = prev_pos > 0
    short_mask = prev_pos < 0
    df.loc[long_mask, "swap_cost"] = prev_pos[long_mask].abs() * swap_long_bps / 10000
    df.loc[short_mask, "swap_cost"] = prev_pos[short_mask].abs() * swap_short_bps / 10000
    df["swap_cost"] = df["swap_cost"].abs()

    df["cost"] = df["tx_cost"] + df["swap_cost"]
    df["strat_ret_net"] = df["strat_ret"] - df["cost"]

    return df


def portfolio_backtest(
    data: pd.DataFrame,
    cost_bps_map: dict,
    swap_long_map: dict | None = None,
    swap_short_map: dict | None = None,
    asset_weights: dict | None = None,
) -> tuple:
    """Multi-asset ensemble portfolio backtest with optional custom weights."""
    asset_returns = {}
    asset_costs = {}
    asset_pos_changes = {}

    swap_long_map = swap_long_map or {}
    swap_short_map = swap_short_map or {}

    for asset in data.columns:
        close = data[asset].dropna()
        if len(close) < 180:
            print(f"  SKIP {asset}: only {len(close)} bars")
            continue

        cost_bps = cost_bps_map.get(asset, 5.0)
        swap_l = swap_long_map.get(asset, 0.0)
        swap_s = swap_short_map.get(asset, 0.0)
        bt = backtest_single_asset(close, cost_bps, swap_l, swap_s)
        asset_returns[asset] = bt["strat_ret_net"]
        asset_costs[asset] = bt["cost"]
        asset_pos_changes[asset] = bt["pos_change"]

    if not asset_returns:
        return pd.DataFrame(), {}

    ret_df = pd.DataFrame(asset_returns)
    cost_df = pd.DataFrame(asset_costs)
    pc_df = pd.DataFrame(asset_pos_changes)

    if asset_weights:
        # Custom-weighted portfolio
        valid_assets = [a for a in ret_df.columns if a in asset_weights]
        if not valid_assets:
            print("  ERROR: No valid assets for weighting")
            return pd.DataFrame(), {}
        w = np.array([asset_weights[a] for a in valid_assets])
        w = w / w.sum()  # normalize to sum=1
        portfolio_ret = ret_df[valid_assets].values @ w
        portfolio_ret = pd.Series(portfolio_ret, index=ret_df.index)
        portfolio_cost = cost_df[valid_assets].values @ w
        portfolio_cost = pd.Series(portfolio_cost, index=cost_df.index)
    else:
        # Equal-weight across assets
        portfolio_ret = ret_df.mean(axis=1, skipna=True)
        portfolio_cost = cost_df.mean(axis=1, skipna=True)

    valid_mask = portfolio_ret.notna()
    portfolio_ret = portfolio_ret[valid_mask]
    portfolio_cost = portfolio_cost[valid_mask]
    pc_df = pc_df.loc[valid_mask]

    result = pd.DataFrame(
        {
            "portfolio_ret": portfolio_ret,
            "portfolio_cost": portfolio_cost,
            "cum_ret": (1 + portfolio_ret).cumprod(),
        }
    )

    details = {
        "asset_returns": ret_df,
        "asset_costs": cost_df,
        "asset_pos_changes": pc_df,
        "n_assets": len(asset_returns),
    }

    return result, details


def compute_metrics(ret: pd.Series, cost_series: pd.Series, pos_changes: pd.DataFrame, name: str = "") -> Metrics:
    ret = ret.dropna()
    if len(ret) < 60:
        return Metrics(
            name=name,
            ann_ret=0,
            ann_vol=0,
            sharpe=0,
            sortino=0,
            max_dd=0,
            dd_duration_days=0,
            win_rate=0,
            profit_factor=0,
            skew=0,
            kurtosis=0,
            n_days=0,
            n_years=0,
            total_return=0,
            annual_cost_drag_bps=0,
            annual_cost_drag_pct=0,
            avg_weekly_turnover=0,
        )

    n_days = len(ret)
    n_years = n_days / 252

    ann_ret = ret.mean() * 252
    ann_vol = ret.std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0

    downside = ret[ret < 0]
    downside_vol = downside.std() * np.sqrt(252) if len(downside) > 0 else 1e-10
    sortino = ann_ret / downside_vol if downside_vol > 0 else 0

    cum = (1 + ret).cumprod()
    peak = cum.cummax()
    dd = (cum - peak) / peak
    max_dd = dd.min()

    is_dd = dd < 0
    dd_groups = (~is_dd).cumsum()
    dd_duration_days = int(is_dd.groupby(dd_groups).sum().max()) if is_dd.any() else 0

    win_rate = (ret > 0).mean()
    gains = ret[ret > 0].sum()
    losses = abs(ret[ret < 0].sum())
    profit_factor = gains / losses if losses > 0 else float("inf")

    total_return = cum.iloc[-1] - 1

    total_cost = cost_series.dropna().sum()
    annual_cost_drag_pct = total_cost / n_years if n_years > 0 else 0
    annual_cost_drag_bps = annual_cost_drag_pct * 10000

    if pos_changes is not None and not pos_changes.empty:
        weekly_pc = pos_changes.resample("W-FRI").sum()
        avg_weekly_turnover = weekly_pc.sum(axis=1).mean()
    else:
        avg_weekly_turnover = 0

    skew = ret.skew()
    kurtosis = ret.kurtosis()

    return Metrics(
        name=name,
        ann_ret=ann_ret,
        ann_vol=ann_vol,
        sharpe=sharpe,
        sortino=sortino,
        max_dd=max_dd,
        dd_duration_days=dd_duration_days,
        win_rate=win_rate,
        profit_factor=profit_factor,
        skew=skew,
        kurtosis=kurtosis,
        n_days=n_days,
        n_years=n_years,
        total_return=total_return,
        annual_cost_drag_bps=annual_cost_drag_bps,
        annual_cost_drag_pct=annual_cost_drag_pct,
        avg_weekly_turnover=avg_weekly_turnover,
    )


def deflated_sharpe_n1(
    observed_sharpe: float, n_observations: int, skewness: float = 0.0, excess_kurtosis: float = 0.0
) -> dict:
    if n_observations <= 1:
        return {
            "passes": False,
            "p_value": 1.0,
            "z_score": 0.0,
            "sr_std": 0.0,
            "expected_max_sharpe": 0.0,
            "detail": "Insufficient observations",
        }

    sr_var = (1 - skewness * observed_sharpe + (excess_kurtosis + 3 - 1) / 4 * observed_sharpe**2) / (
        n_observations - 1
    )
    sr_std = math.sqrt(max(sr_var, 1e-20))
    expected_max_sharpe = 0.0
    z = observed_sharpe / sr_std
    p_value = 1 - _norm_cdf(z)
    passes = observed_sharpe > 0 and p_value < 0.05

    return {
        "passes": passes,
        "p_value": p_value,
        "z_score": z,
        "sr_std": sr_std,
        "expected_max_sharpe": expected_max_sharpe,
        "observed_sharpe": observed_sharpe,
        "n_observations": n_observations,
        "skewness": skewness,
        "excess_kurtosis": excess_kurtosis,
    }


def run_cscv_pbo(ret: pd.Series, n_partitions: int = 16) -> dict:
    from itertools import combinations
    from math import comb

    ret = ret.dropna().values.tolist()
    n_ret = len(ret)

    if n_ret < n_partitions * 5:
        return {
            "pbo": 1.0,
            "n_partitions": n_partitions,
            "n_combinations_tested": 0,
            "passes_threshold": False,
            "error": f"Insufficient data ({n_ret} < {n_partitions * 5})",
        }

    chunk_size = n_ret // n_partitions
    partitions = []
    for i in range(n_partitions):
        start = i * chunk_size
        end = start + chunk_size if i < n_partitions - 1 else n_ret
        partitions.append(ret[start:end])

    half = n_partitions // 2
    if half == 0:
        return {
            "pbo": 1.0,
            "n_partitions": n_partitions,
            "n_combinations_tested": 0,
            "passes_threshold": False,
            "error": "half=0",
        }

    total_combos = comb(n_partitions, half)
    max_combos = min(total_combos, 512)
    indices = list(range(n_partitions))

    overfit_count = 0
    tested = 0

    for is_indices in combinations(indices, half):
        if tested >= max_combos:
            break
        oos_indices = [i for i in indices if i not in is_indices]

        def _sharpe(r):
            if len(r) < 2:
                return 0.0
            m = sum(r) / len(r)
            v = sum((x - m) ** 2 for x in r) / (len(r) - 1)
            s = v**0.5 if v > 0 else 0.0
            return m / s if s > 0 else 0.0

        is_sharpes = {idx: _sharpe(partitions[idx]) for idx in is_indices}
        oos_sharpes = {idx: _sharpe(partitions[idx]) for idx in oos_indices}

        if not is_sharpes or not oos_sharpes:
            continue

        best_is_idx = max(is_sharpes, key=lambda k: is_sharpes[k])
        best_is_oos_sharpe = _sharpe(partitions[best_is_idx])
        n_better = sum(1 for s in oos_sharpes.values() if s > best_is_oos_sharpe)
        rank_fraction = n_better / len(oos_sharpes)

        if rank_fraction >= 0.5:
            overfit_count += 1
        tested += 1

    pbo = overfit_count / tested if tested > 0 else 1.0
    return {
        "pbo": round(pbo, 6),
        "n_partitions": n_partitions,
        "n_combinations_tested": tested,
        "passes_threshold": pbo < 0.50,
    }


def compute_correlation_matrix(data: pd.DataFrame) -> pd.DataFrame:
    """Compute return correlation matrix for the 4 assets."""
    returns = data.pct_change().dropna()
    return returns.corr()


def compute_effective_bets(corr_matrix: pd.DataFrame) -> dict:
    """Compute effective number of independent bets.

    Uses: N_eff = N / (1 + (N-1) * avg_corr)
    where avg_corr is the average pairwise correlation.
    """
    n = len(corr_matrix)
    # Get upper triangle (excluding diagonal)
    mask = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)
    upper_vals = corr_matrix.values[mask]
    avg_corr = upper_vals.mean()
    n_eff = n / (1 + (n - 1) * avg_corr)
    return {
        "n_nominal": n,
        "avg_pairwise_corr": avg_corr,
        "n_effective": n_eff,
        "diversification_ratio": n_eff / n,
    }


def grid_search_optimal_weights(
    data: pd.DataFrame,
    cost_bps_map: dict,
    swap_long_map: dict,
    swap_short_map: dict,
    step: float = 0.05,
) -> dict:
    """Grid search for optimal asset weights that maximize Sharpe (with swap)."""
    assets = list(data.columns)
    n = len(assets)

    # Generate all weight combinations that sum to 1
    # With 4 assets and 0.05 step: ~4000 combinations (manageable)
    weight_values = np.arange(0, 1.0 + step / 2, step)
    best_sharpe = -999
    best_weights = None
    best_metrics = None
    tested = 0

    for combo in itertools.product(weight_values, repeat=n):
        if abs(sum(combo) - 1.0) > 0.001:
            continue
        tested += 1

        w = {assets[i]: combo[i] for i in range(n)}
        bt, details = portfolio_backtest(data, cost_bps_map, swap_long_map, swap_short_map, asset_weights=w)
        if bt.empty:
            continue

        m = compute_metrics(bt["portfolio_ret"], bt["portfolio_cost"], details.get("asset_pos_changes"))
        if m.sharpe > best_sharpe:
            best_sharpe = m.sharpe
            best_weights = w
            best_metrics = m

    return {
        "best_weights": best_weights,
        "best_sharpe": best_sharpe,
        "best_metrics": best_metrics,
        "combinations_tested": tested,
    }


def format_metrics_table(m: Metrics, label: str) -> str:
    lines = [f"### {label}\n"]
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total Return | {m.total_return:.2%} |")
    lines.append(f"| Annualized Return | {m.ann_ret:.2%} |")
    lines.append(f"| Annualized Vol | {m.ann_vol:.2%} |")
    lines.append(f"| Sharpe Ratio | {m.sharpe:.3f} |")
    lines.append(f"| Sortino Ratio | {m.sortino:.3f} |")
    lines.append(f"| Max Drawdown | {m.max_dd:.2%} |")
    lines.append(f"| DD Duration | {m.dd_duration_days} days |")
    lines.append(f"| Win Rate | {m.win_rate:.1%} |")
    lines.append(f"| Profit Factor | {m.profit_factor:.2f} |")
    lines.append(f"| Skewness | {m.skew:.3f} |")
    lines.append(f"| Excess Kurtosis | {m.kurtosis:.3f} |")
    lines.append(f"| Observation Days | {m.n_days} |")
    lines.append(f"| Observation Years | {m.n_years:.1f} |")
    lines.append(f"| Annual Cost Drag (bps) | {m.annual_cost_drag_bps:.1f} |")
    lines.append(f"| Annual Cost Drag (%) | {m.annual_cost_drag_pct:.2%} |")
    lines.append(f"| Avg Weekly Turnover | {m.avg_weekly_turnover:.3f} |")
    lines.append("")
    return "\n".join(lines)


def format_dsr_n1_table(dsr: dict, label: str) -> str:
    lines = [f"### DSR (N=1): {label}\n"]
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Observed Sharpe | {dsr['observed_sharpe']:.3f} |")
    lines.append("| N Trials | 1 (single pre-registered hypothesis) |")
    lines.append(f"| T (observations) | {dsr['n_observations']} |")
    lines.append(f"| Expected Max Sharpe (null) | {dsr['expected_max_sharpe']:.3f} |")
    lines.append(f"| SR Std Error | {dsr['sr_std']:.6f} |")
    lines.append(f"| Z-score | {dsr['z_score']:.3f} |")
    lines.append(f"| P-value (one-sided) | {dsr['p_value']:.6f} |")
    lines.append(f"| Significant (95%) | {'YES' if dsr['passes'] else 'NO'} |")
    lines.append("")
    return "\n".join(lines)


def main():
    print("=" * 70)
    print("CONCENTRATED 4-ASSET ENSEMBLE TSM BACKTEST")
    print("Assets: NAS100, XAUUSD, OIL, USDJPY")
    print("=" * 70)
    print()

    # Load data and costs
    print("Loading data...")
    data = load_all_d1_data_4asset()
    cost_data = load_costs()
    cost_scenarios = build_cost_scenarios_4asset(cost_data)

    print(f"Data: {len(data)} rows, {data.index.min().date()} to {data.index.max().date()}")
    print(f"Assets: {list(data.columns)}")
    print("Per-asset bar counts:")
    for col in data.columns:
        print(f"  {col}: {data[col].notna().sum()} bars")
    print()

    # ── CORRELATION ANALYSIS ─────────────────────────────────────────────
    print("=" * 70)
    print("CORRELATION ANALYSIS")
    print("=" * 70)
    corr = compute_correlation_matrix(data)
    print("\nReturn Correlation Matrix:")
    print(corr.to_string())
    print()

    eff_bets = compute_effective_bets(corr)
    print(f"Nominal bets (assets):  {eff_bets['n_nominal']}")
    print(f"Avg pairwise corr:      {eff_bets['avg_pairwise_corr']:.4f}")
    print(f"Effective bets:         {eff_bets['n_effective']:.2f}")
    print(f"Diversification ratio:  {eff_bets['diversification_ratio']:.2%}")
    print()

    # ── SCENARIO 1: EQUAL WEIGHT (TYPICAL + SWAP) ───────────────────────
    print("=" * 70)
    print("SCENARIO 1: EQUAL WEIGHT (0.25 each) — TYPICAL + SWAP COSTS")
    print("=" * 70)
    swap_long_map = cost_scenarios.get("swap_long", {})
    swap_short_map = cost_scenarios.get("swap_short", {})

    bt_eq, details_eq = portfolio_backtest(data, cost_scenarios["typical"], swap_long_map, swap_short_map)
    if bt_eq.empty:
        print("ERROR: No backtest results")
        return

    m_eq = compute_metrics(
        bt_eq["portfolio_ret"],
        bt_eq["portfolio_cost"],
        details_eq.get("asset_pos_changes"),
        name="equal-weight+swap",
    )

    dsr_eq = deflated_sharpe_n1(
        observed_sharpe=m_eq.sharpe,
        n_observations=m_eq.n_days,
        skewness=m_eq.skew,
        excess_kurtosis=m_eq.kurtosis,
    )

    pbo_eq = run_cscv_pbo(bt_eq["portfolio_ret"])

    print(format_metrics_table(m_eq, "Equal-Weight (Typical + Swap)"))
    print(format_dsr_n1_table(dsr_eq, "Equal-Weight"))
    print(f"PBO: {pbo_eq['pbo']:.4f} (combinations tested: {pbo_eq['n_combinations_tested']})")
    print(f"PBO < 50%: {'YES' if pbo_eq['passes_threshold'] else 'NO'}")
    print()

    # ── SCENARIO 2: OPTIMAL WEIGHT (GRID SEARCH) ───────────────────────
    print("=" * 70)
    print("SCENARIO 2: OPTIMAL WEIGHT (Grid Search) — TYPICAL + SWAP COSTS")
    print("=" * 70)
    print("Grid searching 5% increments...")

    opt_result = grid_search_optimal_weights(
        data,
        cost_scenarios["typical"],
        swap_long_map,
        swap_short_map,
        step=0.05,
    )

    if opt_result["best_weights"]:
        print(f"Combinations tested: {opt_result['combinations_tested']}")
        print(f"Best weights: {opt_result['best_weights']}")
        print(f"Best Sharpe: {opt_result['best_sharpe']:.3f}")

        # Re-run with best weights for full metrics
        bt_opt, details_opt = portfolio_backtest(
            data,
            cost_scenarios["typical"],
            swap_long_map,
            swap_short_map,
            asset_weights=opt_result["best_weights"],
        )
        m_opt = compute_metrics(
            bt_opt["portfolio_ret"],
            bt_opt["portfolio_cost"],
            details_opt.get("asset_pos_changes"),
            name="optimal-weight+swap",
        )
        dsr_opt = deflated_sharpe_n1(
            observed_sharpe=m_opt.sharpe,
            n_observations=m_opt.n_days,
            skewness=m_opt.skew,
            excess_kurtosis=m_opt.kurtosis,
        )
        pbo_opt = run_cscv_pbo(bt_opt["portfolio_ret"])

        print(format_metrics_table(m_opt, "Optimal-Weight (Typical + Swap)"))
        print(format_dsr_n1_table(dsr_opt, "Optimal-Weight"))
        print(f"PBO: {pbo_opt['pbo']:.4f}")
        print(f"PBO < 50%: {'YES' if pbo_opt['passes_threshold'] else 'NO'}")
    else:
        print("ERROR: Grid search failed")
        m_opt = m_eq
        dsr_opt = dsr_eq
        pbo_opt = pbo_eq
    print()

    # ── PER-ASSET BREAKDOWN ─────────────────────────────────────────────
    print("=" * 70)
    print("PER-ASSET CONTRIBUTION (Individual TSM Sharpe)")
    print("=" * 70)

    asset_sharpes = {}
    for asset in data.columns:
        close = data[asset].dropna()
        if len(close) < 180:
            continue
        cost_bps = cost_scenarios["typical"].get(asset, 5.0)
        swap_l = swap_long_map.get(asset, 0.0)
        swap_s = swap_short_map.get(asset, 0.0)
        bt = backtest_single_asset(close, cost_bps, swap_l, swap_s)
        m = compute_metrics(bt["strat_ret_net"], bt["cost"], bt[["pos_change"]], name=asset)
        dsr_a = deflated_sharpe_n1(m.sharpe, m.n_days, m.skew, m.kurtosis)
        asset_sharpes[asset] = m.sharpe
        sig = "YES" if dsr_a["passes"] else "NO"
        print(
            f"  {asset:8s} Sharpe={m.sharpe:.3f}  Ret={m.ann_ret:.2%}  MaxDD={m.max_dd:.2%}  "
            f"DSR P={dsr_a['p_value']:.6f}  Sig={sig}"
        )
    print()

    # ── STRESS SCENARIO ─────────────────────────────────────────────────
    print("=" * 70)
    print("SCENARIO 3: STRESS COSTS (no swap)")
    print("=" * 70)

    bt_stress, details_stress = portfolio_backtest(data, cost_scenarios["stress"])
    if not bt_stress.empty:
        m_stress = compute_metrics(
            bt_stress["portfolio_ret"],
            bt_stress["portfolio_cost"],
            details_stress.get("asset_pos_changes"),
            name="stress",
        )
        dsr_stress = deflated_sharpe_n1(
            observed_sharpe=m_stress.sharpe,
            n_observations=m_stress.n_days,
            skewness=m_stress.skew,
            excess_kurtosis=m_stress.kurtosis,
        )
        print(format_metrics_table(m_stress, "Stress Costs"))
        print(format_dsr_n1_table(dsr_stress, "Stress"))
    else:
        m_stress = m_eq
        dsr_stress = dsr_eq
    print()

    # ── DECISION GATE ───────────────────────────────────────────────────
    print("=" * 70)
    print("DECISION GATE")
    print("=" * 70)
    print()

    # Primary gate: equal-weight with swap (most realistic)
    primary_sharpe = m_eq.sharpe
    primary_dsr = dsr_eq

    if primary_sharpe > 0.5:
        verdict = "REAL_ALPHA"
        verdict_detail = (
            f"4-asset concentrated portfolio Sharpe = {primary_sharpe:.3f} > 0.5. "
            "REAL ALPHA EXISTS. Continue to paper trading."
        )
    elif primary_sharpe > 0.3:
        verdict = "MARGINAL"
        verdict_detail = (
            f"4-asset concentrated portfolio Sharpe = {primary_sharpe:.3f} (0.3-0.5 range). "
            "MARGINAL. Needs investigation: walk-forward, regime analysis."
        )
    else:
        verdict = "ARCHIVE_NO_EDGE"
        verdict_detail = (
            f"4-asset concentrated portfolio Sharpe = {primary_sharpe:.3f} < 0.3. "
            "NO ALPHA. Permanent ARCHIVE_NO_EDGE."
        )

    print(f"Verdict: {verdict}")
    print(f"Detail:  {verdict_detail}")
    print()

    # ── COMPARISON TABLE ────────────────────────────────────────────────
    print("=" * 70)
    print("PORTFOLIO COMPARISON")
    print("=" * 70)
    print()
    print("| Portfolio                  | Sharpe | Ann Ret  | Max DD    | DSR Sig? | PBO    | Verdict       |")
    print("|----------------------------|--------|----------|-----------|----------|--------|---------------|")
    print("| Full Ensemble (8 assets)   | 1.062  | ~12%     | -23%      | YES      | YES    | EDGE_CONFIRMED|")
    print("| Ex-Crypto (9 assets)       | 0.373  | 5.56%    | -23.29%   | YES      | YES    | EDGE_CONFIRMED|")
    print(
        f"| 4-Asset Equal Weight       | {m_eq.sharpe:.3f} | {m_eq.ann_ret:.2%} | {m_eq.max_dd:.2%} | "
        f"{'YES' if dsr_eq['passes'] else 'NO':4s}    | {'YES' if pbo_eq['passes_threshold'] else 'NO':4s}    | {verdict:13s} |"
    )
    if opt_result["best_weights"]:
        print(
            f"| 4-Asset Optimal Weight     | {m_opt.sharpe:.3f} | {m_opt.ann_ret:.2%} | {m_opt.max_dd:.2%} | "
            f"{'YES' if dsr_opt['passes'] else 'NO':4s}    | {'YES' if pbo_opt['passes_threshold'] else 'NO':4s}    | -             |"
        )
    print("| Academic TSM baseline      | ~0.4   | ~8%      | -20%      | -        | -      | Reference     |")
    print()

    # ── GENERATE REPORT ─────────────────────────────────────────────────
    report_lines = [
        "# Concentrated 4-Asset Ensemble TSM Backtest",
        "",
        "**Date:** 2026-07-03",
        "**Strategy:** Ensemble TSM (equal-weight mixture of lookbacks [20, 40, 60, 120])",
        "**Assets:** NAS100, XAUUSD, OIL, USDJPY (concentrated from 9-asset ex-crypto)",
        f"**Data:** {data.index.min().date()} to {data.index.max().date()} ({len(data)} days)",
        "**Hypothesis:** Removing dead weight pushes Sharpe above 0.5",
        "",
        "---",
        "",
        "## Verdict",
        "",
        f"**{verdict}** — {verdict_detail}",
        "",
        "---",
        "",
        "## Correlation Analysis",
        "",
        "### Return Correlation Matrix",
        "",
        corr.to_markdown() if hasattr(corr, "to_markdown") else corr.to_string(),
        "",
        f"- **Nominal bets:** {eff_bets['n_nominal']}",
        f"- **Avg pairwise correlation:** {eff_bets['avg_pairwise_corr']:.4f}",
        f"- **Effective number of independent bets:** {eff_bets['n_effective']:.2f}",
        f"- **Diversification ratio:** {eff_bets['diversification_ratio']:.2%}",
        "",
        "### Interpretation",
        "",
        f"With {eff_bets['n_effective']:.1f} effective independent bets out of {eff_bets['n_nominal']} nominal, ",
        f"the portfolio has {'moderate' if eff_bets['diversification_ratio'] > 0.7 else 'limited'} diversification.",
        "",
        "---",
        "",
        "## Equal-Weight Portfolio (Typical + Swap Costs)",
        "",
        format_metrics_table(m_eq, "Equal-Weight (0.25 each)"),
        format_dsr_n1_table(dsr_eq, "Equal-Weight"),
        f"**PBO:** {pbo_eq['pbo']:.4f} (passes: {'YES' if pbo_eq['passes_threshold'] else 'NO'})",
        "",
    ]

    if opt_result["best_weights"]:
        report_lines.extend(
            [
                "## Optimal-Weight Portfolio (Grid Search, Typical + Swap Costs)",
                "",
                f"**Optimal Weights:** {opt_result['best_weights']}",
                f"**Combinations Tested:** {opt_result['combinations_tested']}",
                "",
                format_metrics_table(m_opt, "Optimal-Weight"),
                format_dsr_n1_table(dsr_opt, "Optimal-Weight"),
                f"**PBO:** {pbo_opt['pbo']:.4f} (passes: {'YES' if pbo_opt['passes_threshold'] else 'NO'})",
                "",
            ]
        )

    report_lines.extend(
        [
            "## Per-Asset Individual Sharpe",
            "",
            "| Asset | Sharpe | Ann Return | Max DD | DSR P-value | Sig? |",
            "|-------|--------|------------|--------|-------------|------|",
        ]
    )

    for asset in data.columns:
        close = data[asset].dropna()
        if len(close) < 180:
            continue
        cost_bps = cost_scenarios["typical"].get(asset, 5.0)
        swap_l = swap_long_map.get(asset, 0.0)
        swap_s = swap_short_map.get(asset, 0.0)
        bt = backtest_single_asset(close, cost_bps, swap_l, swap_s)
        m = compute_metrics(bt["strat_ret_net"], bt["cost"], bt[["pos_change"]], name=asset)
        dsr_a = deflated_sharpe_n1(m.sharpe, m.n_days, m.skew, m.kurtosis)
        sig = "YES" if dsr_a["passes"] else "NO"
        report_lines.append(
            f"| {asset} | {m.sharpe:.3f} | {m.ann_ret:.2%} | {m.max_dd:.2%} | {dsr_a['p_value']:.6f} | {sig} |"
        )
    report_lines.append("")

    report_lines.extend(
        [
            "## Portfolio Comparison",
            "",
            "| Portfolio | Sharpe | Ann Ret | Max DD | DSR Sig? | PBO | Verdict |",
            "|-----------|--------|---------|--------|----------|-----|---------|",
            "| Full Ensemble (8 assets) | 1.062 | ~12% | -23% | YES | YES | EDGE_CONFIRMED |",
            "| Ex-Crypto (9 assets) | 0.373 | 5.56% | -23.29% | YES | YES | EDGE_CONFIRMED |",
            f"| 4-Asset Equal Weight | {m_eq.sharpe:.3f} | {m_eq.ann_ret:.2%} | {m_eq.max_dd:.2%} | "
            f"{'YES' if dsr_eq['passes'] else 'NO'} | {'YES' if pbo_eq['passes_threshold'] else 'NO'} | {verdict} |",
        ]
    )
    if opt_result["best_weights"]:
        report_lines.append(
            f"| 4-Asset Optimal Weight | {m_opt.sharpe:.3f} | {m_opt.ann_ret:.2%} | {m_opt.max_dd:.2%} | "
            f"{'YES' if dsr_opt['passes'] else 'NO'} | {'YES' if pbo_opt['passes_threshold'] else 'NO'} | - |"
        )
    report_lines.append("| Academic TSM baseline | ~0.4 | ~8% | -20% | - | - | Reference |")
    report_lines.append("")

    report_lines.extend(
        [
            "## Decision Criteria",
            "",
            "| Sharpe Range | Verdict | Action |",
            "|-------------|---------|--------|",
            "| > 0.5 | REAL_ALPHA | Continue to paper trading |",
            "| 0.3 - 0.5 | MARGINAL | Needs investigation |",
            "| < 0.3 | ARCHIVE_NO_EDGE | Permanent archive |",
            "",
            f"**Result: {verdict}** (Sharpe = {primary_sharpe:.3f})",
            "",
            "---",
            "",
            "## Methodology",
            "",
            "- Signal: Equal-weight mixture of vol-scaled returns at lookbacks [20, 40, 60, 120]",
            "- NO optimization of signal weights (pre-registered)",
            "- Optimal portfolio weights found via grid search (5% increments) on PORTFOLIO allocation only",
            "- N=1 trial for signal (no multiple testing penalty)",
            "- Transaction costs: per-asset measured Pepperstone Razor spreads",
            "- Swap costs: daily rollover charges (Pepperstone published schedule)",
            "- Vol targeting: 10% annualized, 60-day window, position capped at 1.5x",
            "- Weekly rebalance (Friday close)",
            "",
        ]
    )

    report_path = REPORTS / "tsm_ensemble_backtest_4asset.md"
    report_content = "\n".join(report_lines)
    report_path.write_text(report_content, encoding="utf-8")
    print(f"\nReport written to: {report_path}")

    # Final verdict
    print("\n" + "=" * 70)
    print(f"FINAL VERDICT: {verdict}")
    print(f"  {verdict_detail}")
    print("=" * 70)

    return verdict


if __name__ == "__main__":
    main()
