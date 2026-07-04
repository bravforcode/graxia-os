"""
Ensemble TSM Backtest — EX-CRYPTO (BTC + ETH excluded).

Hypothesis: The ensemble TSM strategy (Sharpe 1.062) exists because BTC went from
$400 to $70,000+. Without BTC+ETH, the edge should disappear if it's just crypto beta.

This script:
1. Runs ensemble TSM on FX + commodities only (no crypto)
2. Reports per-asset Sharpe breakdown
3. Compares with full ensemble results
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

# Import validation modules
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

# EX-CRYPTO assets only (no BTCUSD, no ETHUSD)
TSM_ASSETS_EXCRYPTO = {
    "XAUUSD": {"csv": "data/XAUUSD_D1.csv", "cost_key": "XAUUSD"},
    "EURUSD": {"csv": "data/EURUSD_D1.csv", "cost_key": "EURUSD"},
    "GBPUSD": {"csv": "data/GBPUSD_D1.csv", "cost_key": "GBPUSD"},
    "USDJPY": {"csv": "data/USDJPY_D1.csv", "cost_key": "USDJPY"},
    "USDCHF": {"csv": "data/USDCHF_D1.csv", "cost_key": "USDCHF"},
    "SILVER": {"csv": "data/XAGUSD_D1.csv", "cost_key": "SILVER"},
    "OIL": {"csv": "data/market_data/yfinance/CL_F.csv", "cost_key": "OIL"},
    "US30": {"csv": "data/US30_D1.csv", "cost_key": "US30"},
    "NAS100": {"csv": "data/NAS100_D1.csv", "cost_key": "NAS100"},
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


def build_cost_scenarios_excrypto(cost_data: dict) -> dict:
    """Build cost map for ex-crypto assets only."""
    typical = {}
    stress = {}
    assets = cost_data["assets"]
    stress_scenarios = cost_data.get("stress_scenarios", {})

    for tsm_name, cfg in TSM_ASSETS_EXCRYPTO.items():
        cost_key = cfg["cost_key"]
        # Use default costs for assets not in calibration
        if cost_key not in assets:
            print(f"  WARNING: No cost calibration for {cost_key}, using 10bps default")
            typical[tsm_name] = 10.0
            stress[tsm_name] = 15.0
            continue
        a = assets[cost_key]
        typical[tsm_name] = a["round_trip_bps_measured"]
        if cost_key == "XAUUSD" and "XAUUSD_72bps" in stress_scenarios:
            stress[tsm_name] = stress_scenarios["XAUUSD_72bps"]["round_trip_bps"]
        else:
            stress[tsm_name] = a.get("round_trip_bps_p95", a["round_trip_bps_measured"])

    return {"typical": typical, "stress": stress}


def load_all_d1_data_excrypto() -> pd.DataFrame:
    """Load D1 close prices for EX-CRYPTO assets only."""
    closes = {}

    for tsm_name, cfg in TSM_ASSETS_EXCRYPTO.items():
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


def backtest_single_asset(close: pd.Series, cost_bps: float) -> pd.DataFrame:
    df = pd.DataFrame({"close": close})
    df["ret"] = df["close"].pct_change()
    df["position"] = compute_position(df["ret"])
    weekly_pos = df["position"].resample(REBALANCE_FREQ).last()
    weekly_pos = weekly_pos.reindex(df.index, method="ffill")
    df["position"] = weekly_pos
    df["strat_ret"] = df["position"].shift(1) * df["ret"]
    df["pos_change"] = df["position"].diff().abs()
    df["cost"] = df["pos_change"] * cost_bps / 10000
    df["strat_ret_net"] = df["strat_ret"] - df["cost"]
    return df


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
        if isinstance(weekly_pc, pd.DataFrame):
            avg_weekly_turnover = weekly_pc.sum(axis=1).mean()
        else:
            avg_weekly_turnover = weekly_pc.mean()
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


def deflated_sharpe_n1(observed_sharpe, n_observations, skewness=0.0, excess_kurtosis=0.0):
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


def portfolio_backtest(data: pd.DataFrame, cost_bps_map: dict) -> tuple:
    asset_returns = {}
    asset_costs = {}
    asset_pos_changes = {}
    asset_bt_details = {}

    for asset in data.columns:
        close = data[asset].dropna()
        if len(close) < 180:
            print(f"  SKIP {asset}: only {len(close)} bars")
            continue
        cost_bps = cost_bps_map.get(asset, 10.0)
        bt = backtest_single_asset(close, cost_bps)
        asset_returns[asset] = bt["strat_ret_net"]
        asset_costs[asset] = bt["cost"]
        asset_pos_changes[asset] = bt["pos_change"]
        asset_bt_details[asset] = bt

    if not asset_returns:
        return pd.DataFrame(), {}, {}

    ret_df = pd.DataFrame(asset_returns)
    cost_df = pd.DataFrame(asset_costs)
    pc_df = pd.DataFrame(asset_pos_changes)
    portfolio_ret = ret_df.mean(axis=1, skipna=True)
    portfolio_cost = cost_df.mean(axis=1, skipna=True)
    valid_mask = portfolio_ret.notna()
    portfolio_ret = portfolio_ret[valid_mask]
    portfolio_cost = portfolio_cost[valid_mask]
    pc_df = pc_df.loc[valid_mask]

    result = pd.DataFrame(
        {"portfolio_ret": portfolio_ret, "portfolio_cost": portfolio_cost, "cum_ret": (1 + portfolio_ret).cumprod()}
    )
    details = {
        "asset_returns": ret_df,
        "asset_costs": cost_df,
        "asset_pos_changes": pc_df,
        "n_assets": len(asset_returns),
        "asset_bt_details": asset_bt_details,
    }
    return result, details


def main():
    print("=" * 80)
    print("ENSEMBLE TSM BACKTEST — EX-CRYPTO (BTC + ETH excluded)")
    print("Hypothesis: Without crypto, the ensemble Sharpe collapses")
    print("=" * 80)
    print()

    print("Loading data (ex-crypto only)...")
    data = load_all_d1_data_excrypto()
    cost_data = load_costs()
    cost_scenarios = build_cost_scenarios_excrypto(cost_data)

    print(f"Data: {len(data)} rows, {data.index.min().date()} to {data.index.max().date()}")
    print(f"Assets: {list(data.columns)}")
    print("Per-asset bar counts:")
    for col in data.columns:
        print(f"  {col}: {data[col].notna().sum()} bars")
    print()

    # ── PER-ASSET SHARPE BREAKDOWN ──────────────────────────────────────────
    print("=" * 80)
    print("PER-ASSET SHARPE BREAKDOWN")
    print("=" * 80)
    per_asset_results = {}

    for asset in data.columns:
        close = data[asset].dropna()
        if len(close) < 180:
            print(f"  SKIP {asset}: insufficient data")
            continue
        cost_bps = cost_scenarios["typical"].get(asset, 10.0)
        bt = backtest_single_asset(close, cost_bps)
        m = compute_metrics(bt["strat_ret_net"], bt["cost"], bt["pos_change"], name=asset)
        dsr = deflated_sharpe_n1(m.sharpe, m.n_days, m.skew, m.kurtosis)
        per_asset_results[asset] = {"metrics": m, "dsr": dsr}
        sig = "SIG" if dsr["passes"] else "NOT-SIG"
        print(
            f"  {asset:8s}: Sharpe={m.sharpe:7.3f}  Ret={m.ann_ret:7.2%}  "
            f"MaxDD={m.max_dd:7.2%}  DSR={sig:8s}  p={dsr['p_value']:.6f}"
        )

    print()

    # ── PORTFOLIO BACKTEST (EX-CRYPTO) ──────────────────────────────────────
    results = {}
    dsr_results = {}
    pbo_results = {}

    for scenario_name, cost_map in cost_scenarios.items():
        print(f"--- {scenario_name.upper()} COSTS (EX-CRYPTO) ---")
        bt, details = portfolio_backtest(data, cost_map)

        if bt.empty:
            print("  ERROR: No backtest results")
            continue

        m = compute_metrics(
            bt["portfolio_ret"], bt["portfolio_cost"], details.get("asset_pos_changes"), name=scenario_name
        )
        results[scenario_name] = m
        dsr = deflated_sharpe_n1(m.sharpe, m.n_days, m.skew, m.kurtosis)
        dsr_results[scenario_name] = dsr
        pbo = run_cscv_pbo(bt["portfolio_ret"])
        pbo_results[scenario_name] = pbo

        sig = "SIG" if dsr["passes"] else "NOT-SIG"
        print(
            f"  Sharpe={m.sharpe:.3f}  Ret={m.ann_ret:.2%}  MaxDD={m.max_dd:.2%}  "
            f"CostDrag={m.annual_cost_drag_bps:.0f}bps  DSR={sig}  PBO={pbo['pbo']:.3f}"
        )
        print()

    # ── DECISION GATE ───────────────────────────────────────────────────────
    print("=" * 80)
    print("DECISION GATE — EX-CRYPTO ENSEMBLE")
    print("=" * 80)

    typical = results.get("typical")
    stress = results.get("stress")
    typical_dsr = dsr_results.get("typical")
    stress_dsr = dsr_results.get("stress")
    typical_pbo = pbo_results.get("typical", {})

    if typical_dsr and stress_dsr:
        dsr_pass = typical_dsr["passes"] and stress_dsr["passes"]
        pbo_pass = typical_pbo.get("passes_threshold", False)
        if dsr_pass and pbo_pass:
            verdict = "EDGE_CONFIRMED_EXCRYPTO"
            detail = "DSR significant at N=1 AND PBO < 50%. Real alpha exists without crypto."
        elif dsr_pass and not pbo_pass:
            verdict = "MARGINAL_EXCRYPTO"
            detail = "DSR significant but PBO elevated."
        else:
            verdict = "ARCHIVE_NO_EDGE_EXCRYPTO"
            detail = "DSR not significant without crypto. Ensemble was riding crypto beta."
    else:
        verdict = "ERROR"
        detail = "Could not compute DSR."

    print(f"Verdict: {verdict}")
    print(f"Detail:  {detail}")
    print()

    # ── COMPARISON: FULL vs EX-CRYPTO ───────────────────────────────────────
    print("=" * 80)
    print("COMPARISON: FULL ENSEMBLE vs EX-CRYPTO")
    print("=" * 80)
    print("  Full Ensemble (all 8 assets):     Sharpe = 1.062")
    if typical:
        print(f"  Ex-Crypto Ensemble (typical):     Sharpe = {typical.sharpe:.3f}")
    if stress:
        print(f"  Ex-Crypto Ensemble (stress):      Sharpe = {stress.sharpe:.3f}")
    print()

    # ── ALPHA ATTRIBUTION ───────────────────────────────────────────────────
    print("=" * 80)
    print("ALPHA ATTRIBUTION — Who contributes vs who rides crypto beta?")
    print("=" * 80)
    for asset, res in sorted(per_asset_results.items(), key=lambda x: x[1]["metrics"].sharpe, reverse=True):
        m = res["metrics"]
        dsr = res["dsr"]
        sig = "ALPHA" if dsr["passes"] else "NO-ALPHA"
        print(f"  {asset:8s}: Sharpe={m.sharpe:7.3f}  [{sig}]")
    print()

    # ── WRITE REPORT ────────────────────────────────────────────────────────
    report_lines = [
        "# Ensemble TSM Backtest — EX-CRYPTO (Hypothesis Test)",
        "",
        "**Date:** 2026-07-03",
        "**Strategy:** Ensemble Time-Series Momentum (equal-weight mixture)",
        "**Signal:** Equal-weight of vol-scaled returns at lookbacks [20, 40, 60, 120]",
        "**Rebalance:** Weekly (Friday close)",
        "**Vol Target:** 10% annualized",
        f"**Data:** {data.index.min().date()} to {data.index.max().date()} ({len(data)} days)",
        f"**Assets (EX-CRYPTO):** {', '.join(data.columns)}",
        "**Excluded:** BTCUSD, ETHUSD",
        "**Hypothesis:** Without BTC+ETH, ensemble Sharpe collapses (crypto beta only)",
        "",
        "---",
        "",
        "## Verdict",
        "",
        f"**{verdict}** — {detail}",
        "",
        "---",
        "",
    ]

    # Per-asset Sharpe breakdown
    report_lines.extend(
        [
            "## Per-Asset Sharpe Breakdown\n",
            "| Asset | Sharpe | Ann Return | Max DD | DSR P-value | Sig? | Verdict |",
            "|-------|--------|------------|--------|-------------|------|---------|",
        ]
    )
    for asset, res in sorted(per_asset_results.items(), key=lambda x: x[1]["metrics"].sharpe, reverse=True):
        m = res["metrics"]
        dsr = res["dsr"]
        sig = "YES" if dsr["passes"] else "NO"
        v = "ALPHA" if dsr["passes"] else "NO-ALPHA"
        report_lines.append(
            f"| {asset} | {m.sharpe:.3f} | {m.ann_ret:.2%} | {m.max_dd:.2%} | {dsr['p_value']:.6f} | {sig} | {v} |"
        )
    report_lines.append("")

    # Portfolio metrics
    for scenario_name in ["typical", "stress"]:
        if scenario_name not in results:
            continue
        m = results[scenario_name]
        dsr = dsr_results[scenario_name]
        pbo = pbo_results[scenario_name]
        report_lines.extend(
            [
                f"## {scenario_name.title()} Cost Scenario (EX-CRYPTO Portfolio)\n",
                "| Metric | Value |",
                "|--------|-------|",
                f"| Total Return | {m.total_return:.2%} |",
                f"| Annualized Return | {m.ann_ret:.2%} |",
                f"| Annualized Vol | {m.ann_vol:.2%} |",
                f"| Sharpe Ratio | {m.sharpe:.3f} |",
                f"| Sortino Ratio | {m.sortino:.3f} |",
                f"| Max Drawdown | {m.max_dd:.2%} |",
                f"| DD Duration | {m.dd_duration_days} days |",
                f"| Win Rate | {m.win_rate:.1%} |",
                f"| Profit Factor | {m.profit_factor:.2f} |",
                f"| Skewness | {m.skew:.3f} |",
                f"| Excess Kurtosis | {m.kurtosis:.3f} |",
                f"| Observation Days | {m.n_days} |",
                f"| Observation Years | {m.n_years:.1f} |",
                f"| Annual Cost Drag (bps) | {m.annual_cost_drag_bps:.1f} |",
                f"| Avg Weekly Turnover | {m.avg_weekly_turnover:.3f} |",
                "",
                f"### DSR (N=1): {scenario_name.title()}\n",
                "| Metric | Value |",
                "|--------|-------|",
                f"| Observed Sharpe | {dsr['observed_sharpe']:.3f} |",
                f"| T (observations) | {dsr['n_observations']} |",
                f"| SR Std Error | {dsr['sr_std']:.6f} |",
                f"| Z-score | {dsr['z_score']:.3f} |",
                f"| P-value (one-sided) | {dsr['p_value']:.6f} |",
                f"| Significant (95%) | {'YES' if dsr['passes'] else 'NO'} |",
                "",
                f"### PBO: {scenario_name.title()}\n",
                "| Metric | Value |",
                "|--------|-------|",
                f"| PBO | {pbo['pbo']:.4f} |",
                f"| Combinations Tested | {pbo['n_combinations_tested']} |",
                f"| PBO < 50% | {'YES' if pbo['passes_threshold'] else 'NO'} |",
                "",
            ]
        )

    # Comparison
    report_lines.extend(
        [
            "## Comparison: Full Ensemble vs Ex-Crypto\n",
            "| Ensemble | Sharpe (Typical) | Sharpe (Stress) | DSR @ N=1 | PBO | Verdict |",
            "|----------|------------------|-----------------|-----------|-----|---------|",
            "| Full (8 assets) | 1.062 | 1.029 | YES | YES | EDGE_CONFIRMED |",
        ]
    )
    if typical and stress:
        sig_t = "YES" if typical_dsr["passes"] else "NO"
        sig_s = "YES" if stress_dsr["passes"] else "NO"
        pbo_t = "YES" if typical_pbo.get("passes_threshold", False) else "NO"
        report_lines.append(f"| Ex-Crypto (typical) | {typical.sharpe:.3f} | - | {sig_t} | {pbo_t} | {verdict} |")
        report_lines.append(f"| Ex-Crypto (stress) | {stress.sharpe:.3f} | - | {sig_s} | - | {verdict} |")
    report_lines.extend(
        [
            "| Academic TSM baseline | ~0.4 | ~0.4 | - | - | Reference |",
            "",
            "## Interpretation\n",
            "**If Ex-Crypto Sharpe >> 0.5:** Real momentum alpha exists. Continue.",
            "**If Ex-Crypto Sharpe 0.3-0.5:** Marginal. Needs more investigation.",
            "**If Ex-Crypto Sharpe < 0.3:** No alpha. Crypto beta only. ARCHIVE_NO_EDGE.",
            "",
        ]
    )

    report_path = REPORTS / "tsm_ensemble_backtest_excrypto.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"\nReport written to: {report_path}")

    print("\n" + "=" * 80)
    print(f"FINAL VERDICT: {verdict}")
    print(f"  {detail}")
    print("=" * 80)

    return verdict


if __name__ == "__main__":
    main()
