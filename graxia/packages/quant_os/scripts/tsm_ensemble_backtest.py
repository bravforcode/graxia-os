"""
Ensemble TSM Backtest — Last Hypothesis Test Before Wind-Down.

Equal-weight mixture of ALL lookbacks (20, 40, 60, 120).
NO selection after seeing results. N=1 trial.
This is how real CTA funds operate (Baz et al. 2015 EMAC).

If DSR not significant at N=1 → PERMANENT ARCHIVE_NO_EDGE.

Usage:
    python scripts/tsm_ensemble_backtest.py
"""

import importlib.util
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
_mod_dsr = importlib.util.module_from_spec(_spec_dsr)  # type: ignore[arg-type]
_spec_dsr.loader.exec_module(_mod_dsr)  # type: ignore[union-attr]
deflated_sharpe_ratio = _mod_dsr.deflated_sharpe_ratio
_norm_cdf = _mod_dsr._norm_cdf

_spec_pbo = importlib.util.spec_from_file_location(
    "probability_overfitting", BASE / "validation" / "probability_overfitting.py"
)
_mod_pbo = importlib.util.module_from_spec(_spec_pbo)  # type: ignore[arg-type]
_spec_pbo.loader.exec_module(_mod_pbo)  # type: ignore[union-attr]
calculate_pbo = _mod_pbo.calculate_pbo

REPORTS = BASE / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

# ── LOCKED SIGNAL SPEC ──────────────────────────────────────────────────────
LOOKBACKS = [20, 40, 60, 120]
WEIGHTS = [0.25, 0.25, 0.25, 0.25]  # equal-weight, decided BEFORE seeing results
TARGET_VOL = 0.10
REBALANCE_FREQ = "W-FRI"
POSITION_CAP = 1.5  # max position size (modest leverage allowed)

# TSM symbols and their CSV file names + cost calibration keys
TSM_ASSETS = {
    "XAUUSD": {"csv": "data/XAUUSD_D1.csv", "cost_key": "XAUUSD"},
    "EURUSD": {"csv": "data/EURUSD_D1.csv", "cost_key": "EURUSD"},
    "GBPUSD": {"csv": "data/GBPUSD_D1.csv", "cost_key": "GBPUSD"},
    "USDJPY": {"csv": "data/USDJPY_D1.csv", "cost_key": "USDJPY"},
    "BTCUSD": {"csv": "data/BTCUSD_D1.csv", "cost_key": "BTCUSD"},
    "ETHUSD": {"csv": "data/ETHUSD_D1.csv", "cost_key": "ETHUSD"},
    "SILVER": {"csv": "data/XAGUSD_D1.csv", "cost_key": "SILVER"},
    "OIL": {"csv": "data/market_data/yfinance/CL_F.csv", "cost_key": "OIL"},
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
    kurtosis: float  # excess kurtosis
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


def build_cost_scenarios(cost_data: dict) -> dict:
    typical = {}
    stress = {}
    swap_long = {}
    swap_short = {}
    assets = cost_data["assets"]
    stress_scenarios = cost_data.get("stress_scenarios", {})

    for tsm_name, cfg in TSM_ASSETS.items():
        cost_key = cfg["cost_key"]
        if cost_key not in assets:
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


def load_all_d1_data() -> pd.DataFrame:
    """Load D1 close prices for all TSM symbols, deduplicated to 1 bar/day."""
    closes = {}

    for tsm_name, cfg in TSM_ASSETS.items():
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

        # CRITICAL: Deduplicate — keep only last bar per calendar day
        close = close.groupby(close.index.date).last()
        close.index = pd.to_datetime(close.index, utc=True)
        closes[tsm_name] = close

    if not closes:
        raise RuntimeError("No data files found!")

    result = pd.DataFrame(closes)
    result = result.dropna(how="all")

    # Filter to 2016+ for crypto inclusion
    result = result[result.index >= "2016-01-01"]

    return result


def raw_signal(returns: pd.Series, lookback: int) -> pd.Series:
    """Vol-scaled continuous signal."""
    r = returns.rolling(lookback).sum()
    vol = returns.rolling(lookback).std()
    return r / vol.replace(0, np.nan)


def ensemble_signal(returns: pd.Series) -> pd.Series:
    """Equal-weight mixture of all lookback signals."""
    signals = [raw_signal(returns, L) for L in LOOKBACKS]
    return sum(w * s for w, s in zip(WEIGHTS, signals, strict=False))


def compute_position(returns: pd.Series, target_vol: float = TARGET_VOL) -> pd.Series:
    """Compute position size with vol targeting, capped."""
    sig = ensemble_signal(returns)
    realized_vol = returns.rolling(60).std() * (252**0.5)
    pos = sig * (target_vol / realized_vol.replace(0, np.nan))
    return pos.clip(-POSITION_CAP, POSITION_CAP)


def backtest_single_asset(
    close: pd.Series, cost_bps: float, swap_long_bps: float = 0.0, swap_short_bps: float = 0.0
) -> pd.DataFrame:
    """Backtest ensemble signal on a single asset.

    Applies both transaction costs (on position changes) and daily swap costs
    (for positions held overnight). Swap costs compound significantly over
    multi-week holds (TSM holds 20-120 days).
    """
    df = pd.DataFrame({"close": close})
    df["ret"] = df["close"].pct_change()
    df["position"] = compute_position(df["ret"])

    # Rebalance weekly
    weekly_pos = df["position"].resample(REBALANCE_FREQ).last()
    weekly_pos = weekly_pos.reindex(df.index, method="ffill")
    df["position"] = weekly_pos

    # Strategy return (position from yesterday)
    df["strat_ret"] = df["position"].shift(1) * df["ret"]

    # Transaction costs (one-time on position changes)
    df["pos_change"] = df["position"].diff().abs()
    df["tx_cost"] = df["pos_change"] * cost_bps / 10000

    # Daily swap costs (applied every day position is non-zero)
    # Positive position → long swap rate; negative position → short swap rate
    prev_pos = df["position"].shift(1)
    df["swap_cost"] = 0.0
    long_mask = prev_pos > 0
    short_mask = prev_pos < 0
    df.loc[long_mask, "swap_cost"] = prev_pos[long_mask].abs() * swap_long_bps / 10000
    df.loc[short_mask, "swap_cost"] = prev_pos[short_mask].abs() * swap_short_bps / 10000
    # Swap is a cost (negative return), so take absolute value
    df["swap_cost"] = df["swap_cost"].abs()

    df["cost"] = df["tx_cost"] + df["swap_cost"]
    df["strat_ret_net"] = df["strat_ret"] - df["cost"]

    return df


def portfolio_backtest(
    data: pd.DataFrame, cost_bps_map: dict, swap_long_map: dict | None = None, swap_short_map: dict | None = None
) -> tuple:
    """Multi-asset ensemble portfolio backtest."""
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

    # Equal-weight across assets: average only non-NaN values per row
    portfolio_ret = ret_df.mean(axis=1, skipna=True)
    portfolio_cost = cost_df.mean(axis=1, skipna=True)

    # Drop leading NaN
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

    # Weekly turnover
    if pos_changes is not None and not pos_changes.empty:
        weekly_pc = pos_changes.resample("W-FRI").sum()
        avg_weekly_turnover = weekly_pc.sum(axis=1).mean()
    else:
        avg_weekly_turnover = 0

    skew = ret.skew()
    kurtosis = ret.kurtosis()  # excess kurtosis

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
    """Test if observed Sharpe is significant at N=1 (single hypothesis).

    With N=1 there is NO multiple testing penalty.
    We simply test H0: SR <= 0 using the standard error of the Sharpe ratio.

    SR ~ N(true_SR, SE^2) under mild assumptions.
    SE^2 = (1 - skew*SR + (kurt-1)/4 * SR^2) / (T-1)
    z = SR / SE
    P(SR > 0) = 1 - Phi(-z) = Phi(z)   [one-sided test]
    """
    if n_observations <= 1:
        return {
            "passes": False,
            "p_value": 1.0,
            "z_score": 0.0,
            "sr_std": 0.0,
            "expected_max_sharpe": 0.0,
            "detail": "Insufficient observations",
        }

    # Standard error of Sharpe ratio (Mertens 2003 / Bailey & Lopez de Prado 2014)
    sr_var = (1 - skewness * observed_sharpe + (excess_kurtosis + 3 - 1) / 4 * observed_sharpe**2) / (
        n_observations - 1
    )
    sr_std = math.sqrt(max(sr_var, 1e-20))

    # With N=1, expected max Sharpe under null = 0 (no selection bias)
    expected_max_sharpe = 0.0

    # One-sided z-test: H0: true_SR <= 0
    z = observed_sharpe / sr_std
    p_value = 1 - _norm_cdf(z)  # P(Z > z)

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
    """Run CSCV-based PBO on ensemble returns.

    CSCV (Combinatorial Symmetric Cross-Validation):
    1. Split return series into S equal partitions.
    2. For each C(S, S/2) combination:
       - Use half as IS (in-sample), half as OOS (out-of-sample)
       - Each partition is a "pseudo-strategy" with its own Sharpe
       - Find the IS-best partition (highest IS Sharpe)
       - Check if IS-best ranks in bottom half OOS
    3. PBO = fraction where IS-best underperforms OOS
    """
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

    # Split into S equal partitions
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

    # Enumerate C(S, S/2) combinations, cap at 512
    total_combos = comb(n_partitions, half)
    max_combos = min(total_combos, 512)
    indices = list(range(n_partitions))

    overfit_count = 0
    tested = 0

    for is_indices in combinations(indices, half):
        if tested >= max_combos:
            break
        oos_indices = [i for i in indices if i not in is_indices]

        # Compute Sharpe per partition on IS and OOS
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

        # Find IS-best partition
        best_is_idx = max(is_sharpes, key=lambda k: is_sharpes[k])

        # Get IS-best's OOS Sharpe
        best_is_oos_sharpe = _sharpe(partitions[best_is_idx])

        # Rank: fraction of OOS partitions that beat IS-best
        n_better = sum(1 for s in oos_sharpes.values() if s > best_is_oos_sharpe)
        rank_fraction = n_better / len(oos_sharpes)

        # Overfit if IS-best is in bottom 50% OOS
        if rank_fraction >= 0.5:
            overfit_count += 1

        tested += 1

    pbo = overfit_count / tested if tested > 0 else 1.0

    return {
        "pbo": round(pbo, 6),
        "n_partitions": n_partitions,
        "n_combinations_tested": tested,
        "passes_threshold": pbo < 0.50,  # 50% threshold per spec
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
    print("ENSEMBLE TSM BACKTEST — Last Hypothesis Test")
    print("=" * 70)
    print()

    # Load data and costs
    print("Loading data...")
    data = load_all_d1_data()
    cost_data = load_costs()
    cost_scenarios = build_cost_scenarios(cost_data)

    print(f"Data: {len(data)} rows, {data.index.min().date()} to {data.index.max().date()}")
    print(f"Assets: {list(data.columns)}")
    print("Per-asset bar counts:")
    for col in data.columns:
        print(f"  {col}: {data[col].notna().sum()} bars")
    print()

    # Run scenarios
    results = {}
    dsr_results = {}
    pbo_results = {}

    # Run typical and stress scenarios (transaction costs only, as before)
    for scenario_name in ["typical", "stress"]:
        cost_map = cost_scenarios[scenario_name]
        print(f"--- {scenario_name.upper()} COSTS ---")
        bt, details = portfolio_backtest(data, cost_map)

        if bt.empty:
            print("  ERROR: No backtest results")
            continue

        # Compute metrics
        m = compute_metrics(
            bt["portfolio_ret"],
            bt["portfolio_cost"],
            details.get("asset_pos_changes"),
            name=scenario_name,
        )
        results[scenario_name] = m

        # DSR with N=1 trial (single pre-registered hypothesis)
        dsr = deflated_sharpe_n1(
            observed_sharpe=m.sharpe,
            n_observations=m.n_days,
            skewness=m.skew,
            excess_kurtosis=m.kurtosis,
        )
        dsr_results[scenario_name] = dsr

        # PBO
        pbo = run_cscv_pbo(bt["portfolio_ret"])
        pbo_results[scenario_name] = pbo

        sig = "SIG" if dsr["passes"] else "NOT-SIG"
        print(
            f"  Sharpe={m.sharpe:.3f}  Ret={m.ann_ret:.2%}  MaxDD={m.max_dd:.2%}  "
            f"CostDrag={m.annual_cost_drag_bps:.0f}bps  DSR={sig}  PBO={pbo['pbo']:.3f}"
        )
        print()

    # Run "typical + swap" scenario — transaction costs AND daily swap costs
    print("--- TYPICAL + SWAP COSTS ---")
    swap_long_map = cost_scenarios.get("swap_long", {})
    swap_short_map = cost_scenarios.get("swap_short", {})
    bt_swap, details_swap = portfolio_backtest(data, cost_scenarios["typical"], swap_long_map, swap_short_map)

    if not bt_swap.empty:
        m_swap = compute_metrics(
            bt_swap["portfolio_ret"],
            bt_swap["portfolio_cost"],
            details_swap.get("asset_pos_changes"),
            name="typical+swap",
        )
        results["typical+swap"] = m_swap

        dsr_swap = deflated_sharpe_n1(
            observed_sharpe=m_swap.sharpe,
            n_observations=m_swap.n_days,
            skewness=m_swap.skew,
            excess_kurtosis=m_swap.kurtosis,
        )
        dsr_results["typical+swap"] = dsr_swap

        pbo_swap = run_cscv_pbo(bt_swap["portfolio_ret"])
        pbo_results["typical+swap"] = pbo_swap

        sig = "SIG" if dsr_swap["passes"] else "NOT-SIG"
        print(
            f"  Sharpe={m_swap.sharpe:.3f}  Ret={m_swap.ann_ret:.2%}  MaxDD={m_swap.max_dd:.2%}  "
            f"CostDrag={m_swap.annual_cost_drag_bps:.0f}bps  DSR={sig}  PBO={pbo_swap['pbo']:.3f}"
        )
        print()

    # Print swap impact comparison
    if "typical" in results and "typical+swap" in results:
        m_base = results["typical"]
        m_swap = results["typical+swap"]
        sharpe_delta = m_swap.sharpe - m_base.sharpe
        dd_delta = m_swap.max_dd - m_base.max_dd
        drag_delta = m_swap.annual_cost_drag_bps - m_base.annual_cost_drag_bps
        print("--- SWAP IMPACT ---")
        print(f"  Sharpe: {m_base.sharpe:.3f} -> {m_swap.sharpe:.3f} (delta: {sharpe_delta:+.3f})")
        print(f"  MaxDD:  {m_base.max_dd:.2%} -> {m_swap.max_dd:.2%} (delta: {dd_delta:+.2%})")
        print(
            f"  Cost Drag: {m_base.annual_cost_drag_bps:.0f}"
            f" -> {m_swap.annual_cost_drag_bps:.0f} bps"
            f" (+{drag_delta:.0f} bps)"
        )
        print()

    # Decision gate
    print("=" * 70)
    print("DECISION GATE")
    print("=" * 70)

    typical_dsr = dsr_results.get("typical")
    stress_dsr = dsr_results.get("stress")
    swap_dsr = dsr_results.get("typical+swap")
    typical_pbo = pbo_results.get("typical", {})

    # Use typical+swap as the primary gate if available (more realistic)
    primary_dsr = swap_dsr if swap_dsr else typical_dsr

    if primary_dsr and stress_dsr:
        dsr_pass = primary_dsr["passes"] and stress_dsr["passes"]
        pbo_pass = typical_pbo.get("passes_threshold", False)

        if dsr_pass and pbo_pass:
            verdict = "EDGE_CONFIRMED"
            verdict_detail = (
                "DSR significant at N=1 (with swap costs) AND PBO < 50%. "
                "Proceed to Phase 5 (paper trading) confirmation."
            )
        elif dsr_pass and not pbo_pass:
            verdict = "MARGINAL"
            verdict_detail = "DSR significant but PBO elevated. " "Needs further investigation before paper trading."
        else:
            verdict = "ARCHIVE_NO_EDGE"
            verdict_detail = (
                "DSR not significant even at N=1 trial (with swap costs). "
                "PERMANENT — no more tests, no pivots, no alternatives. "
                "TSM momentum has no edge after real costs including swap."
            )
    else:
        verdict = "ERROR"
        verdict_detail = "Could not compute DSR."

    print(f"Verdict: {verdict}")
    print(f"Detail:  {verdict_detail}")
    print()

    # Generate report
    report_lines = [
        "# Ensemble TSM Backtest — Last Hypothesis Test",
        "",
        "**Date:** 2026-07-03",
        "**Strategy:** Ensemble Time-Series Momentum (equal-weight mixture)",
        "**Signal:** Equal-weight of vol-scaled returns at lookbacks [20, 40, 60, 120]",
        "**Rebalance:** Weekly (Friday close)",
        "**Vol Target:** 10% annualized",
        f"**Data:** {data.index.min().date()} to {data.index.max().date()} ({len(data)} days)",
        f"**Assets:** {', '.join(data.columns)}",
        "**Hypothesis:** Ensemble TSM produces risk-adjusted edge after real costs",
        "**Trial Count:** N=1 (single pre-registered hypothesis, no multiple testing)",
        "",
        "---",
        "",
        "## Verdict",
        "",
        f"**{verdict}** — {verdict_detail}",
        "",
        "---",
        "",
    ]

    # Signal specification
    report_lines.extend(
        [
            "## Signal Specification (LOCKED)\n",
            "```python",
            "LOOKBACKS = [20, 40, 60, 120]",
            "WEIGHTS = [0.25, 0.25, 0.25, 0.25]  # equal-weight",
            "",
            "def raw_signal(returns, lookback):",
            "    r = returns.rolling(lookback).sum()",
            "    vol = returns.rolling(lookback).std()",
            "    return r / vol  # vol-scaled continuous signal",
            "",
            "def ensemble_signal(returns):",
            "    signals = [raw_signal(returns, L) for L in LOOKBACKS]",
            "    return sum(w * s for w, s in zip(WEIGHTS, signals))",
            "```",
            "",
        ]
    )

    # Per-asset cost breakdown
    report_lines.extend(
        [
            "## Per-Asset Cost Breakdown (Round-Trip bps)\n",
            "| Asset | Typical (median) | Stress (P95/worst) | Swap Long (bps/day) | Swap Short (bps/day) | Source |",
            "|-------|------------------|--------------------|---------------------|----------------------|--------|",
        ]
    )
    for tsm_name, cfg in TSM_ASSETS.items():
        cost_key = cfg["cost_key"]
        if cost_key not in cost_data["assets"]:
            continue
        a = cost_data["assets"][cost_key]
        typical = cost_scenarios["typical"].get(tsm_name, 0)
        stress_val = cost_scenarios["stress"].get(tsm_name, 0)
        swap_l = cost_scenarios["swap_long"].get(tsm_name, 0)
        swap_s = cost_scenarios["swap_short"].get(tsm_name, 0)
        source = a.get("notes", "")
        report_lines.append(
            f"| {cost_key} | {typical:.2f} | {stress_val:.2f} | {swap_l:.2f} | {swap_s:.2f} | {source} |"
        )
    report_lines.append("")

    # Results per scenario
    for scenario_name in ["typical", "stress", "typical+swap"]:
        if scenario_name not in results:
            continue
        m = results[scenario_name]
        dsr = dsr_results[scenario_name]
        pbo = pbo_results[scenario_name]

        report_lines.append(f"## {scenario_name.title()} Cost Scenario\n")
        report_lines.append(format_metrics_table(m, scenario_name.title()))
        report_lines.append(format_dsr_n1_table(dsr, scenario_name.title()))

        report_lines.extend(
            [
                f"### PBO: {scenario_name.title()}\n",
                "| Metric | Value |",
                "|--------|-------|",
                f"| PBO | {pbo['pbo']:.4f} |",
                f"| N Partitions | {pbo['n_partitions']} |",
                f"| Combinations Tested | {pbo['n_combinations_tested']} |",
                f"| PBO < 5% | {'YES' if pbo['passes_threshold'] else 'NO'} |",
                "",
            ]
        )

    # DSR intermediate values
    report_lines.extend(
        [
            "## DSR Intermediate Values (Reproducibility)\n",
            "With N=1 (single pre-registered hypothesis), there is NO multiple testing penalty.",
            "We use a one-sided z-test: H0: true_SR <= 0.\n",
        ]
    )
    for scenario_name in ["typical", "stress"]:
        if scenario_name not in dsr_results:
            continue
        dsr = dsr_results[scenario_name]
        # Compute variance term for logging
        var_term = (
            1
            - dsr["skewness"] * dsr["observed_sharpe"]
            + (dsr["excess_kurtosis"] + 3 - 1) / 4 * dsr["observed_sharpe"] ** 2
        ) / (dsr["n_observations"] - 1)
        report_lines.extend(
            [
                f"### {scenario_name.title()}\n",
                f"- T (observation count): {dsr['n_observations']}",
                f"- Observed Sharpe: {dsr['observed_sharpe']:.6f}",
                "- N trials: 1 (single pre-registered hypothesis)",
                f"- Skewness: {dsr['skewness']:.6f}",
                f"- Excess Kurtosis: {dsr['excess_kurtosis']:.6f}",
                f"- Variance term: {var_term:.10f}",
                f"- SR std error: {dsr['sr_std']:.10f}",
                f"- Z-score: {dsr['z_score']:.6f}",
                f"- P-value (one-sided): {dsr['p_value']:.10f}",
                f"- Expected max Sharpe (null, N=1): {dsr['expected_max_sharpe']:.6f}",
                f"- Significant (95%): {'YES' if dsr['passes'] else 'NO'}",
                "",
            ]
        )

    # Comparison table
    report_lines.extend(
        [
            "## Comparison: Ensemble vs Best-of-8 vs Academic Baseline\n",
            "| Strategy | Sharpe (Typical) | Sharpe (Stress) | DSR @ N=1 | PBO | Verdict |",
            "|----------|------------------|-----------------|-----------|-----|---------|",
        ]
    )
    for scenario_name in ["typical", "stress"]:
        if scenario_name not in results:
            continue
        m = results[scenario_name]
        dsr = dsr_results[scenario_name]
        pbo = pbo_results[scenario_name]
        sig = "YES" if dsr["passes"] else "NO"
        pbo_pass = "YES" if pbo["passes_threshold"] else "NO"
        report_lines.append(f"| Ensemble ({scenario_name}) | {m.sharpe:.3f} | - | {sig} | {pbo_pass} | {verdict} |")
    report_lines.extend(
        [
            "| Best-of-8 LB=120 (typical) | 1.059 | 1.059 | NO (N=8) | - | ARCHIVE_NO_EDGE |",
            "| Academic TSM baseline | ~0.4 | ~0.4 | - | - | Reference |",
            "",
        ]
    )

    # Key insight
    report_lines.extend(
        [
            "## Key Insight\n",
            "The critical difference between this test and the previous Best-of-8:",
            "- **Best-of-8**: Selected the best lookback AFTER seeing results → N=8 trials → DSR penalized → NO",
            "- **Ensemble**: Pre-registered equal-weight mixture → N=1 trial → no selection bias → fair test",
            "",
            "This is how real CTA funds operate (Baz et al. 2015 EMAC).",
            "",
        ]
    )

    # Decision gate
    report_lines.extend(
        [
            "## Decision Gate\n",
            "| Result | Action |",
            "|--------|--------|",
            "| DSR significant (95%) at N=1, PBO < 50% | EDGE_CONFIRMED |",
            "| DSR not significant | ARCHIVE_NO_EDGE — permanent, no more tests |",
            "",
            f"**Result: {verdict}**",
            "",
        ]
    )

    if verdict == "EDGE_CONFIRMED":
        report_lines.extend(
            [
                "> **EDGE_CONFIRMED** — This needs Phase 5 (paper trading) confirmation before live.",
                "> The ensemble signal shows statistical edge after real costs, but must be validated",
                "> in live paper trading before any real capital deployment.",
                "",
            ]
        )
    elif verdict == "ARCHIVE_NO_EDGE":
        report_lines.extend(
            [
                "> **PERMANENT ARCHIVE_NO_EDGE** — This is the end.",
                "> No more tests, no pivots, no alternatives.",
                "> TSM momentum has no edge after real costs.",
                "",
            ]
        )
    elif verdict == "MARGINAL":
        report_lines.extend(
            [
                "> **MARGINAL** — DSR significant but PBO elevated.",
                "> The ensemble shows promise but PBO suggests possible overfitting.",
                "> Further investigation needed: walk-forward validation, regime analysis.",
                "",
            ]
        )

    # Swap Impact Comparison
    if "typical" in results and "typical+swap" in results:
        m_base = results["typical"]
        m_swap = results["typical+swap"]
        sharpe_delta = m_swap.sharpe - m_base.sharpe
        dd_delta = m_swap.max_dd - m_base.max_dd
        drag_delta = m_swap.annual_cost_drag_bps - m_base.annual_cost_drag_bps
        report_lines.extend(
            [
                "## Swap Cost Impact Analysis\n",
                "TSM holds positions for 20-120 days. "
                "Swap/rollover costs compound significantly "
                "over multi-week holds.\n",
                "| Metric | Without Swap | With Swap | Delta |",
                "|--------|-------------|-----------|-------|",
                f"| Sharpe Ratio | {m_base.sharpe:.3f}" f" | {m_swap.sharpe:.3f} | {sharpe_delta:+.3f} |",
                f"| Annualized Return | {m_base.ann_ret:.2%}"
                f" | {m_swap.ann_ret:.2%}"
                f" | {m_swap.ann_ret - m_base.ann_ret:+.2%} |",
                f"| Max Drawdown | {m_base.max_dd:.2%}" f" | {m_swap.max_dd:.2%} | {dd_delta:+.2%} |",
                f"| Annual Cost Drag (bps) | {m_base.annual_cost_drag_bps:.0f}"
                f" | {m_swap.annual_cost_drag_bps:.0f}"
                f" | +{drag_delta:.0f} |",
                f"| Total Return | {m_base.total_return:.2%}"
                f" | {m_swap.total_return:.2%}"
                f" | {m_swap.total_return - m_base.total_return:+.2%} |",
                "",
                "### Per-Asset Swap Rate Source\n",
                "Swap rates derived from Pepperstone published overnight rates (July 2026):\n",
                "- **XAUUSD**: ~$0.50/lot/night long (you pay), ~$0.20/lot/night short (you receive)",
                "- **BTCUSD/ETHUSD**: ~0.01%/night funding rate (perpetual swap equivalent)",
                "- **FX pairs**: ±LIBOR differential (USD rates higher than EUR/GBP → longs pay)",
                "- **OIL**: ~$0.50/lot/night contango premium",
                "",
            ]
        )

    # Methodology
    report_lines.extend(
        [
            "## Methodology Notes\n",
            "- Ensemble: equal-weight (0.25 each) of vol-scaled signals at lookbacks [20, 40, 60, 120]",
            "- NO selection after seeing results — weights decided BEFORE backtest",
            "- N=1 trial: single pre-registered hypothesis, no multiple testing penalty",
            "- DSR: one-sided z-test of H0: true_SR <= 0 (no multiple testing adjustment needed at N=1)",
            "- PBO: Combinatorial Symmetric Cross-Validation (CSCV)",
            "- Transaction Costs: per-asset measured Pepperstone Razor spreads from config/cost_calibration.json",
            "- Swap Costs: daily rollover charges applied to overnight positions (from Pepperstone published schedule)",
            "- Vol targeting: 10% annualized, 60-day realized vol window, position capped at 1.5x",
            "- Weekly rebalance (Friday close)",
            "- Equal-weight across assets (simple diversification)",
            "- Data: 2016-01-01 to 2026-07-01 (all 8 assets available)",
            "",
        ]
    )

    # Write report
    report_path = REPORTS / "tsm_ensemble_backtest.md"
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
