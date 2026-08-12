"""
TSM Backtest with Real Measured Costs (Pepperstone Razor).

Applies per-asset measured spreads from config/cost_calibration.json
to the academic time-series momentum strategy.

Scenarios:
  - Typical: median measured round-trip cost per asset
  - Stress: P95 round-trip cost (or 72bps XAUUSD worst-case)

Decision gate (spec Section 3):
  - DSR significant at both typical AND stress → EDGE_CANDIDATE
  - DSR significant only at typical → Marginal, reduce size
  - DSR not significant even at typical → ARCHIVE_NO_EDGE

Usage:
    python scripts/tsm_backtest_real_costs.py
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import importlib.util

from core.returns import compute_returns

# Import deflated_sharpe directly to avoid validation/__init__.py dependency chain
_spec = importlib.util.spec_from_file_location("deflated_sharpe", BASE / "validation" / "deflated_sharpe.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
deflated_sharpe_ratio = _mod.deflated_sharpe_ratio
ARTIFACTS = BASE / "artifacts"
OUT_DIR = ARTIFACTS / "portfolio"
REPORTS = BASE / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

# ── Config ──
TARGET_VOL = 0.10
LOOKBACK_WINDOWS = [20, 40, 60, 120]
REBALANCE_FREQ = "W-FRI"

ASSETS = [
    "XAUUSD",
    "EURUSD_YF",
    "GBPUSD_YF",
    "USDJPY",
    "BTC_YF",
    "ETH_YF",
    "SILVER",
    "OIL",
]

# Map TSM asset names → cost_calibration keys
ASSET_COST_MAP = {
    "XAUUSD": "XAUUSD",
    "EURUSD_YF": "EURUSD",
    "GBPUSD_YF": "GBPUSD",
    "USDJPY": "USDJPY",
    "BTC_YF": "BTCUSD",
    "ETH_YF": "ETHUSD",
    "SILVER": "SILVER",
    "OIL": "OIL",
}


def load_costs() -> dict:
    path = BASE / "config" / "cost_calibration.json"
    with open(path) as f:
        return json.load(f)


def build_cost_scenarios(cost_data: dict) -> dict:
    """Build per-asset cost scenarios from calibration data.

    Returns:
        {
            "typical": {"XAUUSD": 0.72, "EURUSD_YF": 7.0, ...},
            "stress":  {"XAUUSD": 72.0, "EURUSD_YF": 7.0, ...},
        }
    """
    typical = {}
    stress = {}

    assets = cost_data["assets"]
    stress_scenarios = cost_data.get("stress_scenarios", {})

    for tsm_name, cost_key in ASSET_COST_MAP.items():
        if cost_key not in assets:
            continue
        a = assets[cost_key]
        typical[tsm_name] = a["round_trip_bps_measured"]

        # Stress: P95 for most assets, 72bps worst-case for XAUUSD
        if cost_key == "XAUUSD" and "XAUUSD_72bps" in stress_scenarios:
            stress[tsm_name] = stress_scenarios["XAUUSD_72bps"]["round_trip_bps"]
        else:
            stress[tsm_name] = a.get("round_trip_bps_p95", a["round_trip_bps_measured"])

    return {"typical": typical, "stress": stress}


def load_data() -> pd.DataFrame:
    path = OUT_DIR / "d1_multi_asset.parquet"
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index, utc=True)
    return df.sort_index()


def compute_tsm_signal(close: pd.Series, lookback: int) -> pd.Series:
    ret = compute_returns(close, lookback)
    return np.sign(ret)


def compute_vol_target_weight(close: pd.Series, lookback: int, target_vol: float, rvol_window: int = 20) -> pd.Series:
    signal = compute_tsm_signal(close, lookback)
    daily_ret = compute_returns(close, 1)
    rvol = daily_ret.rolling(rvol_window).std() * np.sqrt(252)
    rvol = rvol.replace(0, np.nan)
    weight = signal * target_vol / rvol
    return weight.clip(-1, 1)


def backtest_single_asset(close: pd.Series, lookback: int, target_vol: float, cost_bps: float) -> pd.DataFrame:
    df = pd.DataFrame({"close": close})
    df["ret"] = compute_returns(df["close"], lookback=1)
    df["weight"] = compute_vol_target_weight(close, lookback, target_vol)

    # Rebalance weekly
    weekly_weight = df["weight"].resample(REBALANCE_FREQ).last()
    weekly_weight = weekly_weight.reindex(df.index, method="ffill")
    df["weight"] = weekly_weight

    # Strategy return
    df["strat_ret"] = df["weight"].shift(1) * df["ret"]

    # Transaction costs proportional to weight change
    df["weight_change"] = df["weight"].diff().abs()
    df["cost"] = df["weight_change"] * cost_bps / 10000
    df["strat_ret_net"] = df["strat_ret"] - df["cost"]

    df["cum_ret"] = (1 + df["strat_ret_net"]).cumprod()
    return df


def portfolio_backtest(data: pd.DataFrame, assets: list, lookback: int, target_vol: float, cost_bps_map: dict) -> tuple:
    """Multi-asset TSM portfolio with per-asset costs.

    Args:
        cost_bps_map: {asset_name: round_trip_bps} for per-asset costs

    Returns:
        (portfolio_df, per_asset_details_dict)
    """
    asset_returns = {}
    asset_weights = {}
    asset_costs = {}
    asset_weight_changes = {}

    for asset in assets:
        col = f"{asset}_close"
        if col not in data.columns:
            continue
        close = data[col].dropna()
        if len(close) < lookback + 60:
            continue

        cost_bps = cost_bps_map.get(asset, 5.0)
        bt = backtest_single_asset(close, lookback, target_vol, cost_bps)
        asset_returns[asset] = bt["strat_ret_net"]
        asset_weights[asset] = bt["weight"]
        asset_costs[asset] = bt["cost"]
        asset_weight_changes[asset] = bt["weight_change"]

    if not asset_returns:
        return pd.DataFrame(), {}

    ret_df = pd.DataFrame(asset_returns)
    weight_df = pd.DataFrame(asset_weights)
    cost_df = pd.DataFrame(asset_costs)
    wc_df = pd.DataFrame(asset_weight_changes)

    # Inverse-vol weighting across assets
    asset_rvol = ret_df.rolling(60).std()
    inv_rvol = 1.0 / asset_rvol.replace(0, np.nan)
    inv_rvol = inv_rvol.div(inv_rvol.sum(axis=1), axis=0)

    portfolio_ret = (ret_df * inv_rvol).sum(axis=1)
    portfolio_cost = (cost_df * inv_rvol).sum(axis=1)

    result = pd.DataFrame(
        {
            "portfolio_ret": portfolio_ret,
            "portfolio_cost": portfolio_cost,
            "cum_ret": (1 + portfolio_ret).cumprod(),
        }
    )

    details = {
        "asset_returns": ret_df,
        "asset_weights": weight_df,
        "asset_costs": cost_df,
        "asset_weight_changes": wc_df,
        "inv_rvol": inv_rvol,
        "n_assets": len(asset_returns),
    }

    return result, details


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
    n_days: float
    n_years: float
    total_return: float
    annual_cost_drag_bps: float
    annual_cost_drag_pct: float
    total_turnover: float
    avg_weekly_turnover: float


def compute_metrics(ret: pd.Series, cost_series: pd.Series, weight_changes: pd.DataFrame, name: str = "") -> Metrics:
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
            n_days=0,
            n_years=0,
            total_return=0,
            annual_cost_drag_bps=0,
            annual_cost_drag_pct=0,
            total_turnover=0,
            avg_weekly_turnover=0,
        )

    n_days = len(ret)
    n_years = n_days / 252

    ann_ret = ret.mean() * 252
    ann_vol = ret.std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0

    # Sortino
    downside = ret[ret < 0]
    downside_vol = downside.std() * np.sqrt(252) if len(downside) > 0 else 1e-10
    sortino = ann_ret / downside_vol if downside_vol > 0 else 0

    # Max drawdown and duration
    cum = (1 + ret).cumprod()
    peak = cum.cummax()
    dd = (cum - peak) / peak
    max_dd = dd.min()

    # DD duration (longest streak below peak)
    is_dd = dd < 0
    dd_groups = (~is_dd).cumsum()
    if is_dd.any():
        dd_duration_days = is_dd.groupby(dd_groups).sum().max()
    else:
        dd_duration_days = 0

    # Win rate
    win_rate = (ret > 0).mean()

    # Profit factor
    gains = ret[ret > 0].sum()
    losses = abs(ret[ret < 0].sum())
    profit_factor = gains / losses if losses > 0 else float("inf")

    # Total return
    total_return = cum.iloc[-1] - 1

    # Annual cost drag
    total_cost = cost_series.dropna().sum()
    annual_cost_drag_pct = total_cost / n_years if n_years > 0 else 0
    annual_cost_drag_bps = annual_cost_drag_pct * 10000

    # Turnover: sum of absolute weight changes per asset per week
    if weight_changes is not None and not weight_changes.empty:
        weekly_wc = weight_changes.resample("W-FRI").sum()
        total_turnover = weekly_wc.sum().sum()
        n_weeks = len(weekly_wc)
        avg_weekly_turnover = total_turnover / n_weeks if n_weeks > 0 else 0
    else:
        total_turnover = 0
        avg_weekly_turnover = 0

    skew = ret.skew()

    return Metrics(
        name=name,
        ann_ret=ann_ret,
        ann_vol=ann_vol,
        sharpe=sharpe,
        sortino=sortino,
        max_dd=max_dd,
        dd_duration_days=int(dd_duration_days),
        win_rate=win_rate,
        profit_factor=profit_factor,
        skew=skew,
        n_days=n_days,
        n_years=n_years,
        total_return=total_return,
        annual_cost_drag_bps=annual_cost_drag_bps,
        annual_cost_drag_pct=annual_cost_drag_pct,
        total_turnover=total_turnover,
        avg_weekly_turnover=avg_weekly_turnover,
    )


def run_scenario(
    data: pd.DataFrame, assets: list, lookback: int, target_vol: float, cost_bps_map: dict, scenario_name: str
) -> tuple:
    """Run one cost scenario, return (metrics, dsr_result)."""
    bt, details = portfolio_backtest(data, assets, lookback, target_vol, cost_bps_map)

    if bt.empty:
        return None, None

    m = compute_metrics(
        bt["portfolio_ret"],
        bt["portfolio_cost"],
        details.get("asset_weight_changes"),
        name=scenario_name,
    )

    # DSR: 4 lookbacks × 2 signal types = 8 trials (same as original)
    n_trials = len(LOOKBACK_WINDOWS) * 2
    dsr = deflated_sharpe_ratio(
        observed_sharpe=m.sharpe,
        n_trials=n_trials,
        n_observations=int(m.n_days),
        skewness=m.skew,
        kurtosis=3.0,
        confidence_level=0.95,
    )

    return m, dsr


def format_metrics_table(metrics: dict, label: str) -> str:
    lines = [f"### {label}\n"]
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total Return | {metrics.total_return:.2%} |")
    lines.append(f"| Annualized Return | {metrics.ann_ret:.2%} |")
    lines.append(f"| Annualized Vol | {metrics.ann_vol:.2%} |")
    lines.append(f"| Sharpe Ratio | {metrics.sharpe:.3f} |")
    lines.append(f"| Sortino Ratio | {metrics.sortino:.3f} |")
    lines.append(f"| Max Drawdown | {metrics.max_dd:.2%} |")
    lines.append(f"| DD Duration | {metrics.dd_duration_days} days |")
    lines.append(f"| Win Rate | {metrics.win_rate:.1%} |")
    lines.append(f"| Profit Factor | {metrics.profit_factor:.2f} |")
    lines.append(f"| Skewness | {metrics.skew:.3f} |")
    lines.append(f"| Observation Days | {metrics.n_days:.0f} |")
    lines.append(f"| Observation Years | {metrics.n_years:.1f} |")
    lines.append(f"| Annual Cost Drag (bps) | {metrics.annual_cost_drag_bps:.1f} |")
    lines.append(f"| Annual Cost Drag (%) | {metrics.annual_cost_drag_pct:.2%} |")
    lines.append(f"| Avg Weekly Turnover | {metrics.avg_weekly_turnover:.3f} |")
    lines.append("")
    return "\n".join(lines)


def format_dsr_table(dsr, label: str) -> str:
    lines = [f"### DSR: {label}\n"]
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Observed Sharpe | {dsr.observed_sharpe:.3f} |")
    lines.append(f"| Expected Max Sharpe (null) | {dsr.multiple_testing_adjustment:.3f} |")
    lines.append(f"| Deflated Sharpe | {dsr.deflated_sharpe:.3f} |")
    lines.append(f"| P(alpha) | {dsr.probability_alpha:.4f} |")
    lines.append(f"| Significant (95%) | {'YES' if dsr.passes_threshold else 'NO'} |")
    lines.append("")
    return "\n".join(lines)


def format_cost_breakdown(cost_data: dict, cost_scenarios: dict) -> str:
    lines = ["## Per-Asset Cost Breakdown (Round-Trip bps)\n"]
    lines.append("| Asset | Typical (median) | Stress (P95/worst) | Source |")
    lines.append("|-------|------------------|--------------------|--------|")

    for tsm_name, cost_key in ASSET_COST_MAP.items():
        if cost_key not in cost_data["assets"]:
            continue
        a = cost_data["assets"][cost_key]
        typical = cost_scenarios["typical"].get(tsm_name, 0)
        stress_val = cost_scenarios["stress"].get(tsm_name, 0)
        source = a.get("notes", "")
        lines.append(f"| {cost_key} | {typical:.2f} | {stress_val:.2f} | {source} |")

    lines.append("")
    return "\n".join(lines)


def format_annual_cost_math(cost_scenarios: dict, n_assets: int) -> str:
    """Show the annual cost drag calculation explicitly."""
    lines = ["## Annual Cost Drag Calculation\n"]
    lines.append("Formula: `n_assets x rebalances_per_year x avg_turnover_per_rebalance x cost_bps x 2`")
    lines.append("")
    lines.append("Assumptions:")
    lines.append(f"- Assets: {n_assets}")
    lines.append("- Rebalances per year: 52 (weekly)")
    lines.append("- Each rebalance: weight_change × cost_bps / 10000")
    lines.append("")

    for scenario_name, cost_map in cost_scenarios.items():
        avg_cost = np.mean(list(cost_map.values()))
        lines.append(f"**{scenario_name.title()}**: avg round-trip cost = {avg_cost:.1f} bps")
    lines.append("")
    return "\n".join(lines)


def main():
    print("=== TSM Backtest with Real Measured Costs (Pepperstone) ===\n")

    # Load data and costs
    data = load_data()
    cost_data = load_costs()
    cost_scenarios = build_cost_scenarios(cost_data)

    n_assets_available = sum(1 for a in ASSETS if f"{a}_close" in data.columns)
    print(f"Data: {len(data)} rows, {data.index.min()} to {data.index.max()}")
    print(f"Assets available: {n_assets_available}")
    print()

    print("Cost scenarios (round-trip bps):")
    for scenario_name, cost_map in cost_scenarios.items():
        print(f"  {scenario_name}: {cost_map}")
    print()

    # Run all lookbacks × scenarios
    all_results = {}

    for lookback in LOOKBACK_WINDOWS:
        print(f"--- Lookback: {lookback} days ---")
        lb_results = {}

        for scenario_name, cost_map in cost_scenarios.items():
            m, dsr = run_scenario(data, ASSETS, lookback, TARGET_VOL, cost_map, scenario_name)
            if m is None:
                print(f"  {scenario_name}: No data")
                continue

            lb_results[scenario_name] = {"metrics": m, "dsr": dsr}

            sig = "SIG" if dsr.passes_threshold else "NOT-SIG"
            print(
                f"  {scenario_name.title():>10}: Sharpe={m.sharpe:.3f}  Ret={m.ann_ret:.2%}  "
                f"MaxDD={m.max_dd:.2%}  CostDrag={m.annual_cost_drag_bps:.0f}bps  DSR={sig}"
            )

        all_results[lookback] = lb_results
        print()

    # Decision gate: use lookback=60 as primary (most common in literature)
    primary_lb = 60
    if primary_lb not in all_results:
        primary_lb = LOOKBACK_WINDOWS[0]

    print("=" * 60)
    print("DECISION GATE (lookback=60)")
    print("=" * 60)

    primary = all_results.get(primary_lb, {})
    typical_dsr = primary.get("typical", {}).get("dsr")
    stress_dsr = primary.get("stress", {}).get("dsr")

    if typical_dsr and stress_dsr:
        if typical_dsr.passes_threshold and stress_dsr.passes_threshold:
            verdict = "EDGE_CANDIDATE"
            verdict_detail = "DSR significant at both typical AND stress costs. Proceed to Fix #4."
        elif typical_dsr.passes_threshold and not stress_dsr.passes_threshold:
            verdict = "MARGINAL"
            verdict_detail = "DSR significant at typical but NOT stress. Reduce position size."
        else:
            verdict = "ARCHIVE_NO_EDGE"
            verdict_detail = "DSR not significant even at typical costs. TSM momentum has no edge after real costs."
    else:
        verdict = "ERROR"
        verdict_detail = "Could not compute DSR."

    print(f"Verdict: {verdict}")
    print(f"Detail:  {verdict_detail}")
    print()

    # Generate report
    report_lines = [
        "# TSM Momentum Backtest — Real Measured Costs (Pepperstone Razor)",
        "",
        "**Date:** 2026-07-03",
        "**Strategy:** Academic Time-Series Momentum (TSM)",
        "**Signal:** sign(lookback_return) × vol_target / realized_vol",
        "**Rebalance:** Weekly (Friday close)",
        f"**Vol Target:** {TARGET_VOL:.0%} annualized",
        f"**Data:** {data.index.min().strftime('%Y-%m-%d')} to {data.index.max().strftime('%Y-%m-%d')} ({len(data)} days)",
        f"**Assets:** {', '.join(ASSETS)}",
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

    # Cost breakdown
    report_lines.append(format_cost_breakdown(cost_data, cost_scenarios))
    report_lines.append(format_annual_cost_math(cost_scenarios, n_assets_available))

    # Per-lookback results
    for lb in LOOKBACK_WINDOWS:
        if lb not in all_results:
            continue
        report_lines.append(f"## Lookback = {lb} days\n")

        for scenario_name in ["typical", "stress"]:
            if scenario_name not in all_results[lb]:
                continue
            m = all_results[lb][scenario_name]["metrics"]
            dsr = all_results[lb][scenario_name]["dsr"]
            report_lines.append(format_metrics_table(m, scenario_name.title()))
            report_lines.append(format_dsr_table(dsr, scenario_name.title()))

    # Summary comparison
    report_lines.append("## Summary Comparison\n")
    report_lines.append("| Lookback | Scenario | Sharpe | Ann Ret | Max DD | Cost Drag (bps) | DSR Sig |")
    report_lines.append("|----------|----------|--------|---------|--------|-----------------|---------|")

    for lb in LOOKBACK_WINDOWS:
        if lb not in all_results:
            continue
        for scenario_name in ["typical", "stress"]:
            if scenario_name not in all_results[lb]:
                continue
            m = all_results[lb][scenario_name]["metrics"]
            dsr = all_results[lb][scenario_name]["dsr"]
            sig = "YES" if dsr.passes_threshold else "NO"
            report_lines.append(
                f"| {lb} | {scenario_name.title()} | {m.sharpe:.3f} | {m.ann_ret:.2%} | "
                f"{m.max_dd:.2%} | {m.annual_cost_drag_bps:.0f} | {sig} |"
            )
    report_lines.append("")

    # Cost threshold analysis
    report_lines.append("## Cost Threshold Analysis\n")
    report_lines.append("What Sharpe ratio is needed to cover annual costs?\n")
    report_lines.append("| Scenario | Avg RT Cost (bps) | Annual Cost at 52 rebal/yr | Min Sharpe to Cover |")
    report_lines.append("|----------|-------------------|---------------------------|---------------------|")

    for scenario_name, cost_map in cost_scenarios.items():
        avg_cost = np.mean(list(cost_map.values()))
        # Rough: 8 assets × 52 weeks × avg_weight_change × cost
        # At 10% vol target with ~0.5 avg weight, turnover ≈ 0.5/week/asset
        est_annual_cost_pct = avg_cost / 10000 * 8 * 52 * 0.3  # conservative turnover estimate
        min_sharpe = est_annual_cost_pct / 0.10  # divide by vol target
        report_lines.append(
            f"| {scenario_name.title()} | {avg_cost:.1f} | {est_annual_cost_pct:.2%} | {min_sharpe:.3f} |"
        )
    report_lines.append("")

    # Methodology notes
    report_lines.append("## Methodology Notes\n")
    report_lines.append("- Costs applied per-asset using measured Pepperstone Razor spreads")
    report_lines.append("- Typical = median measured round-trip; Stress = P95 (XAUUSD uses 72bps worst-case)")
    report_lines.append("- DSR: Bailey & Lopez de Prado (2014), 8 trials (4 lookbacks × 2 signal types)")
    report_lines.append("- Vol targeting: 10% annualized, capped at 1.0 (no leverage)")
    report_lines.append("- Inverse-vol weighting across assets, 60-day rolling window")
    report_lines.append("- Weekly rebalance (Friday close), cost = |Δweight| × cost_bps / 10000")
    report_lines.append("")

    # Write report
    report_path = REPORTS / "tsm_backtest_real_costs.md"
    report_content = "\n".join(report_lines)
    report_path.write_text(report_content, encoding="utf-8")
    print(f"\nReport written to: {report_path}")

    # Print final verdict
    print("\n" + "=" * 60)
    print(f"FINAL VERDICT: {verdict}")
    print(f"  {verdict_detail}")
    print("=" * 60)

    return verdict


if __name__ == "__main__":
    main()
