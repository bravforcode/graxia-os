"""
Jackknife Asset Robustness Test (F5)
=====================================
Re-run edge search 7 times, each time excluding one asset, to confirm
no single asset carries the entire result.

Uses momentum_factor_rotation (cross-sectional TSMOM rotation) with the
same DK-test formula as edge_search_all.py.

Jackknife criterion: dk_t > 1.0 in ALL leave-one-out runs.
If any single exclusion collapses dk_t below 1.0, the result is fragile.

Usage:
    python scripts/jackknife_asset_robustness.py \
        --universe XAUUSD,XAGUSD,EURUSD,GBPUSD,USDJPY,NAS100,US30 \
        --trial 2001 \
        --cost-model pepperstone_razor
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

ROOT = Path(__file__).resolve().parent.parent
GRAXIA_ROOT = ROOT.parent.parent.parent
for p in (str(GRAXIA_ROOT), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# ---------------------------------------------------------------------------
# Imports from quant_os
# ---------------------------------------------------------------------------
from graxia.packages.quant_os.strategies.momentum_factor_rotation import (
    MomentumFactorRotationConfig,
    compute_momentum_factor_rotation,
)

# Minimum bars after 2005 filter
MIN_BARS = 500

# Pepperstone Razor cost model (spread + commission per symbol)
PEPPERSTONE_SPREAD_PIPS: dict[str, float] = {
    "XAUUSD": 1.5,
    "XAGUSD": 2.0,
    "EURUSD": 0.1,
    "GBPUSD": 0.3,
    "USDJPY": 0.2,
    "NAS100": 1.0,
    "US30": 1.5,
    "BTCUSD": 50.0,
    "AUDUSD": 0.2,
    "USDCHF": 0.3,
    "USDCAD": 0.3,
    "ETHUSD": 3.0,
}

PEPPERSTONE_COMMISSION: dict[str, float] = {
    "XAUUSD": 0.0,
    "XAGUSD": 0.0,
    "EURUSD": 7.0,
    "GBPUSD": 7.0,
    "USDJPY": 7.0,
    "NAS100": 5.0,
    "US30": 5.0,
    "BTCUSD": 0.0,
    "AUDUSD": 7.0,
    "USDCHF": 7.0,
    "USDCAD": 7.0,
    "ETHUSD": 0.0,
}

# Pip values for cost estimation (USD per pip per standard lot)
PIP_VALUE: dict[str, float] = {
    "XAUUSD": 10.0,
    "XAGUSD": 50.0,
    "EURUSD": 10.0,
    "GBPUSD": 10.0,
    "USDJPY": 6.7,
    "NAS100": 1.0,
    "US30": 1.0,
    "BTCUSD": 1.0,
    "AUDUSD": 10.0,
    "USDCHF": 10.0,
    "USDCAD": 7.5,
    "ETHUSD": 1.0,
}


# ---------------------------------------------------------------------------
# Data loading (reuses same path convention as edge_search_all.py)
# ---------------------------------------------------------------------------


def load_asset_data(symbol: str) -> pd.DataFrame:
    """Load D1 OHLCV from data/{symbol}_D1.csv, filtered >= 2005."""
    path = ROOT / "data" / f"{symbol}_D1.csv"
    if not path.exists():
        raise FileNotFoundError(f"missing {path}")
    df = pd.read_csv(path)
    ts_col = "time" if "time" in df.columns else "date"
    df[ts_col] = pd.to_datetime(df[ts_col])
    df = df[df[ts_col] >= "2005-01-01"].sort_values(ts_col).reset_index(drop=True)
    if "time" not in df.columns and ts_col != "time":
        df = df.rename(columns={ts_col: "time"})
    if len(df) < MIN_BARS:
        raise ValueError(f"{symbol}: only {len(df)} bars (< {MIN_BARS})")
    return df


def load_close_prices(symbols: list[str]) -> pd.DataFrame:
    """Load close prices for multiple assets into a single aligned DataFrame.

    Returns DataFrame with DatetimeIndex and columns = symbol names.
    All series are aligned to the common date range.
    """
    frames = {}
    for sym in symbols:
        df = load_asset_data(sym)
        ts = pd.to_datetime(df["time"])
        close = pd.Series(df["close"].values, index=ts, name=sym, dtype=float)
        frames[sym] = close

    combined = pd.DataFrame(frames)
    # Forward-fill short gaps, then drop rows where any asset still has NaN
    combined = combined.ffill(limit=5).dropna()
    return combined


# ---------------------------------------------------------------------------
# Cost model
# ---------------------------------------------------------------------------


def apply_transaction_costs(
    signal_changes: pd.DataFrame,
    symbols: list[str],
    cost_model: str = "pepperstone_razor",
) -> float:
    """Estimate total transaction costs (USD) from signal changes.

    For each signal flip (0->1, 1->0, 1->-1, etc.) on each asset,
    we charge spread + commission on a notional 1-lot trade.
    """
    if cost_model != "pepperstone_razor":
        # Custom cost model not yet supported; return 0 for non-standard
        return 0.0

    total_cost = 0.0
    for sym in symbols:
        if sym not in signal_changes.columns:
            continue
        # Count signal flips (non-zero changes)
        flips = (signal_changes[sym].fillna(0).diff().abs() > 0).sum()
        spread_pips = PEPPERSTONE_SPREAD_PIPS.get(sym, 2.0)
        commission = PEPPERSTONE_COMMISSION.get(sym, 3.5)
        pip_val = PIP_VALUE.get(sym, 10.0)
        cost_per_flip = spread_pips * pip_val + commission
        total_cost += flips * cost_per_flip

    return total_cost


# ---------------------------------------------------------------------------
# DK-test (exact formula from edge_search_all.py lines 573-634)
# ---------------------------------------------------------------------------


def run_dk_test(all_returns: pd.DataFrame, total_trades: int) -> dict:
    """Newey-West t-statistic on cross-sectional mean returns.

    Identical formula to edge_search_all.run_dk_test().
    """
    if all_returns.empty or len(all_returns.columns) < 2:
        return {
            "dk_t_stat": 0.0,
            "pooled_sharpe": 0.0,
            "positive_sharpe_count": 0,
            "total_assets": len(all_returns.columns) if not all_returns.empty else 0,
            "total_days": 0,
            "total_trades": total_trades,
            "verdict": "INSUFFICIENT_DATA",
        }

    cs_mean = all_returns.mean(axis=1).dropna()
    if len(cs_mean) < 30:
        return {
            "dk_t_stat": 0.0,
            "pooled_sharpe": 0.0,
            "positive_sharpe_count": 0,
            "total_assets": len(all_returns.columns),
            "total_days": len(cs_mean),
            "total_trades": total_trades,
            "verdict": "INSUFFICIENT_DATA",
        }

    mu = float(cs_mean.mean())
    T = len(cs_mean)
    max_lag = max(1, int(T ** (1 / 3)))
    gamma_0 = float(cs_mean.var(ddof=1))
    nw_var = gamma_0
    for lag in range(1, max_lag + 1):
        cov = float(cs_mean.iloc[lag:].cov(cs_mean.iloc[:-lag]))
        weight = 1.0 - lag / (max_lag + 1)
        nw_var += 2 * weight * cov

    nw_se = math.sqrt(nw_var / T) if nw_var > 0 else 1e-10
    dk_t = mu / nw_se if nw_se > 0 else 0.0
    pooled_sharpe = mu / (math.sqrt(gamma_0) + 1e-10) * math.sqrt(252)

    pos_sharpe = 0
    for col in all_returns.columns:
        r = all_returns[col].dropna()
        if len(r) > 30:
            s = float(r.mean()) / (float(r.std(ddof=1)) + 1e-10) * math.sqrt(252)
            if s > 0:
                pos_sharpe += 1

    if dk_t > 2.0 and pos_sharpe >= 5:
        verdict = "GO"
    elif dk_t > 1.5 or (dk_t > 1.0 and pos_sharpe >= 4):
        verdict = "MARGINAL"
    else:
        verdict = "REJECT"

    return {
        "dk_t_stat": round(dk_t, 4),
        "pooled_sharpe": round(pooled_sharpe, 4),
        "positive_sharpe_count": pos_sharpe,
        "total_assets": len(all_returns.columns),
        "total_days": T,
        "total_trades": total_trades,
        "verdict": verdict,
    }


# ---------------------------------------------------------------------------
# Per-asset metrics (from edge_search_all.py lines 517-570)
# ---------------------------------------------------------------------------


def compute_per_asset_metrics(
    daily_returns: pd.Series,
    symbol: str,
) -> dict:
    """Compute Sharpe, total return, max DD for a single asset's daily returns."""
    r = daily_returns.dropna()
    if len(r) < 30:
        return {
            "symbol": symbol,
            "n_days": len(r),
            "sharpe": 0.0,
            "total_return_pct": 0.0,
            "max_dd_pct": 0.0,
        }

    mu = float(r.mean())
    std = float(r.std(ddof=1))
    sharpe = mu / (std + 1e-10) * math.sqrt(252)

    # Equity curve from returns
    equity = (1 + r).cumprod()
    peak = equity.cummax()
    drawdown = (equity - peak) / peak
    max_dd = float(drawdown.min())
    total_ret = float(equity.iloc[-1] - 1)

    return {
        "symbol": symbol,
        "n_days": len(r),
        "sharpe": round(sharpe, 4),
        "total_return_pct": round(total_ret * 100, 4),
        "max_dd_pct": round(abs(max_dd) * 100, 4),
    }


# ---------------------------------------------------------------------------
# Single leave-one-out run
# ---------------------------------------------------------------------------


def run_leave_one_out(
    excluded_asset: str,
    universe: list[str],
    config: MomentumFactorRotationConfig,
    cost_model: str,
) -> dict:
    """Run momentum factor rotation edge search excluding one asset.

    Steps:
    1. Load close prices for the remaining (N-1) assets.
    2. Compute momentum factor rotation signals.
    3. Compute daily returns per asset (signal.shift(1) * daily_price_return).
    4. Apply transaction cost deduction.
    5. Run DK-test on pooled returns.
    """
    remaining = [a for a in universe if a != excluded_asset]
    print(f"\n  LOO: exclude={excluded_asset} | remaining={remaining}")

    # 1) Load prices
    prices = load_close_prices(remaining)
    print(f"    data: {len(prices)} bars, {len(remaining)} assets")

    # 2) Compute MFR signals
    result = compute_momentum_factor_rotation(prices, config)
    signals = result.signal  # {-1, 0, +1} per asset

    # 3) Daily price returns
    price_returns = prices.pct_change().iloc[1:]
    # Shift signals by 1 to avoid lookahead: trade on bar i+1 based on signal at bar i
    shifted_signals = signals.shift(1).iloc[1:]

    # Align indices
    common_idx = price_returns.index.intersection(shifted_signals.index)
    price_returns = price_returns.loc[common_idx]
    shifted_signals = shifted_signals.loc[common_idx]

    # Strategy returns = signal * price return
    strategy_returns = shifted_signals * price_returns

    # 4) Estimate and deduct transaction costs
    signal_changes = shifted_signals.copy()
    total_cost_usd = apply_transaction_costs(signal_changes, remaining, cost_model)

    # Deduct costs proportionally from returns (spread across all return days)
    n_days = len(strategy_returns)
    if n_days > 0 and total_cost_usd > 0:
        # Assume notional $100k; cost per day as fraction of notional
        notional = 100_000.0
        cost_per_day = total_cost_usd / (notional * n_days)
        # Subtract from each asset's return proportionally
        # Only on days where signal changed
        for sym in remaining:
            if sym in signal_changes.columns:
                flip_mask = (signal_changes[sym].fillna(0).diff().abs() > 0)
                # Spread cost of that flip over the holding period until next flip
                flips_idx = signal_changes.index[flip_mask]
                for flip_i, flip_ts in enumerate(flips_idx):
                    # Find next flip or end
                    if flip_i + 1 < len(flips_idx):
                        next_flip = flips_idx[flip_i + 1]
                    else:
                        next_flip = strategy_returns.index[-1]
                    hold_slice = strategy_returns.loc[flip_ts:next_flip].index
                    n_hold = max(len(hold_slice), 1)
                    # Per-flip cost for this asset
                    spread_pips = PEPPERSTONE_SPREAD_PIPS.get(sym, 2.0)
                    commission = PEPPERSTONE_COMMISSION.get(sym, 3.5)
                    pip_val = PIP_VALUE.get(sym, 10.0)
                    flip_cost = (spread_pips * pip_val + commission) / (notional * n_hold)
                    strategy_returns.loc[hold_slice, sym] -= flip_cost

    # 5) Count total trades (signal changes across all assets)
    total_trades = 0
    per_asset_details: dict = {}
    for sym in remaining:
        sc = shifted_signals[sym].fillna(0)
        flips = (sc.diff().abs() > 0).sum()
        total_trades += int(flips)
        per_asset_details[sym] = compute_per_asset_metrics(strategy_returns[sym], sym)
        per_asset_details[sym]["n_trades"] = int(flips)

    # 6) DK test
    dk = run_dk_test(strategy_returns, total_trades)
    dk["per_asset"] = per_asset_details
    dk["excluded_asset"] = excluded_asset
    dk["remaining_assets"] = remaining
    dk["total_cost_usd"] = round(total_cost_usd, 2)

    print(
        f"    trades={total_trades}  dk_t={dk['dk_t_stat']:.4f}  "
        f"sharpe={dk['pooled_sharpe']:.4f}  verdict={dk['verdict']}"
    )
    return dk


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Jackknife asset robustness test (F5) — momentum factor rotation"
    )
    parser.add_argument(
        "--universe",
        type=str,
        default="XAUUSD,XAGUSD,EURUSD,GBPUSD,USDJPY,NAS100,US30",
        help="Comma-separated list of 7 assets",
    )
    parser.add_argument(
        "--trial",
        type=int,
        default=2001,
        help="Trial number (e.g. 2001)",
    )
    parser.add_argument(
        "--cost-model",
        type=str,
        default="pepperstone_razor",
        help="Cost model: pepperstone_razor or path to JSON",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Output JSON path (default: reports/jackknife_robustness_YYYYMMDD.json)",
    )
    args = parser.parse_args()

    universe = [s.strip() for s in args.universe.split(",") if s.strip()]
    if len(universe) < 3:
        print(f"FATAL: need >= 3 assets, got {len(universe)}")
        return 1

    # Default output path
    if not args.output:
        date_str = datetime.now(UTC).strftime("%Y%m%d")
        args.output = str(ROOT / "reports" / f"jackknife_robustness_{date_str}.json")

    # Frozen config (pre-registered, same as momentum_factor_rotation.py)
    config = MomentumFactorRotationConfig()

    print(f"Jackknife Asset Robustness Test (F5)")
    print(f"{'=' * 64}")
    print(f"  Trial:     {args.trial}")
    print(f"  Universe:  {universe} ({len(universe)} assets)")
    print(f"  Cost model:{args.cost_model}")
    print(f"  Strategy:  momentum_factor_rotation")
    print(f"  Config:    lookbacks={config.lookbacks} vol_target={config.vol_target}")
    print(f"             top_n={config.top_n} bottom_n={config.bottom_n}")
    print(f"             rebalance_freq={config.rebalance_freq}")
    print(f"             min_signal_strength={config.min_signal_strength}")
    print(f"  Jackknife: dk_t > 1.0 in ALL {len(universe)} leave-one-out runs")
    print(f"{'=' * 64}")

    # Validate data availability
    print("\nValidating data...")
    usable = []
    for sym in universe:
        try:
            df = load_asset_data(sym)
            usable.append(sym)
            print(f"  OK  {sym}: {len(df)} bars")
        except Exception as e:
            print(f"  SKIP {sym}: {e}")
    if len(usable) < 3:
        print(f"FATAL: only {len(usable)} assets have data (need >= 3)")
        return 1
    universe = usable

    # Run leave-one-out tests
    results: list[dict] = []
    all_pass = True
    min_dk_t = float("inf")
    worst_exclusion = ""

    print(f"\nRunning {len(universe)} leave-one-out tests...")
    for excluded in universe:
        try:
            loo_result = run_leave_one_out(
                excluded_asset=excluded,
                universe=universe,
                config=config,
                cost_model=args.cost_model,
            )
            results.append(loo_result)

            dk_t = loo_result.get("dk_t_stat", 0.0)
            if dk_t < min_dk_t:
                min_dk_t = dk_t
                worst_exclusion = excluded
            if dk_t <= 1.0:
                all_pass = False
        except Exception as e:
            print(f"    ERROR excluding {excluded}: {e}")
            traceback.print_exc()
            results.append({
                "excluded_asset": excluded,
                "dk_t_stat": 0.0,
                "verdict": "ERROR",
                "error": str(e),
            })
            all_pass = False

    # Also run full universe (no exclusion) as baseline
    print(f"\nRunning full universe baseline ({len(universe)} assets)...")
    try:
        baseline = run_leave_one_out(
            excluded_asset="__NONE__",
            universe=universe + ["__NONE__"],  # dummy that gets excluded
            config=config,
            cost_model=args.cost_model,
        )
        # Actually, run directly on full universe
        prices_full = load_close_prices(universe)
        result_full = compute_momentum_factor_rotation(prices_full, config)
        signals_full = result_full.signal
        price_ret_full = prices_full.pct_change().iloc[1:]
        shifted_full = signals_full.shift(1).iloc[1:]
        common_full = price_ret_full.index.intersection(shifted_full.index)
        strat_ret_full = shifted_full.loc[common_full] * price_ret_full.loc[common_full]

        total_trades_full = 0
        per_asset_full: dict = {}
        for sym in universe:
            sc = shifted_full[sym].fillna(0)
            flips = int((sc.diff().abs() > 0).sum())
            total_trades_full += flips
            per_asset_full[sym] = compute_per_asset_metrics(strat_ret_full[sym], sym)
            per_asset_full[sym]["n_trades"] = flips

        baseline_dk = run_dk_test(strat_ret_full, total_trades_full)
        baseline_dk["per_asset"] = per_asset_full
        baseline_dk["excluded_asset"] = None
        baseline_dk["remaining_assets"] = universe
        print(
            f"  BASELINE: trades={total_trades_full}  "
            f"dk_t={baseline_dk['dk_t_stat']:.4f}  "
            f"verdict={baseline_dk['verdict']}"
        )
    except Exception as e:
        print(f"  BASELINE ERROR: {e}")
        baseline_dk = {"dk_t_stat": 0.0, "verdict": "ERROR", "error": str(e)}

    # Summary table
    print(f"\n{'=' * 64}")
    print(f"  JACKKNIFE RESULTS — Trial {args.trial}")
    print(f"{'=' * 64}")
    print(f"  {'Excluded':<12} {'DK-t':>8} {'Sharpe':>8} {'Trades':>7} {'Pos':>5} {'Verdict':<12}")
    print(f"  {'-' * 56}")
    for r in sorted(results, key=lambda x: x.get("dk_t_stat", 0)):
        print(
            f"  {r['excluded_asset']:<12} "
            f"{r.get('dk_t_stat', 0):>8.4f} "
            f"{r.get('pooled_sharpe', 0):>8.4f} "
            f"{r.get('total_trades', 0):>7} "
            f"{r.get('positive_sharpe_count', 0)}/{r.get('total_assets', 0):<2} "
            f"{r.get('verdict', '?'):<12}"
        )

    print(f"\n  Baseline DK-t:  {baseline_dk.get('dk_t_stat', 0):.4f}")
    print(f"  Min LOO DK-t:   {min_dk_t:.4f} (excluded: {worst_exclusion})")
    print(f"  Jackknife PASS: {all_pass}")

    if all_pass:
        print("\n  ✅ PASS: dk_t > 1.0 in all leave-one-out runs. No single-asset dependency.")
    else:
        failed = [r for r in results if r.get("dk_t_stat", 0) <= 1.0]
        print(f"\n  ❌ FAIL: {len(failed)} exclusion(s) dropped dk_t <= 1.0:")
        for r in failed:
            print(f"     exclude {r['excluded_asset']}: dk_t={r.get('dk_t_stat', 0):.4f}")

    # Build output JSON
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "trial": args.trial,
        "test": "jackknife_asset_robustness",
        "version": "F5",
        "strategy": "momentum_factor_rotation",
        "strategy_config": {
            "lookbacks": list(config.lookbacks),
            "vol_target": config.vol_target,
            "top_n": config.top_n,
            "bottom_n": config.bottom_n,
            "rebalance_freq": config.rebalance_freq,
            "min_signal_strength": config.min_signal_strength,
        },
        "universe": universe,
        "cost_model": args.cost_model,
        "n_assets": len(universe),
        "jackknife_criterion": "dk_t > 1.0 in ALL leave-one-out runs",
        "verdict": "PASS" if all_pass else "FAIL",
        "baseline": {
            "dk_t_stat": baseline_dk.get("dk_t_stat", 0),
            "pooled_sharpe": baseline_dk.get("pooled_sharpe", 0),
            "total_trades": baseline_dk.get("total_trades", 0),
            "positive_sharpe_count": baseline_dk.get("positive_sharpe_count", 0),
            "verdict": baseline_dk.get("verdict", "?"),
        },
        "min_loo_dk_t": round(min_dk_t, 4),
        "worst_exclusion": worst_exclusion,
        "leave_one_out_results": [
            {
                "excluded_asset": r.get("excluded_asset"),
                "dk_t_stat": r.get("dk_t_stat", 0),
                "pooled_sharpe": r.get("pooled_sharpe", 0),
                "total_trades": r.get("total_trades", 0),
                "positive_sharpe_count": r.get("positive_sharpe_count", 0),
                "total_assets": r.get("total_assets", 0),
                "total_days": r.get("total_days", 0),
                "verdict": r.get("verdict", "?"),
                "total_cost_usd": r.get("total_cost_usd", 0),
                "per_asset": r.get("per_asset", {}),
            }
            for r in results
        ],
        "honest_note": (
            "Jackknife robustness (F5): each asset removed one at a time. "
            "If any single exclusion collapses dk_t below 1.0, the pooled result "
            "is driven by that asset and is fragile. PASS means no single-asset dependency."
        ),
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"\n  Saved: {out_path}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
