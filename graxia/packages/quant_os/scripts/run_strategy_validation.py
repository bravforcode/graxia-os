"""
General Strategy Validation Runner

Runs any strategy through the same validation gates as RYDC:
- Walk-Forward Analysis (WFA)
- Deflated Sharpe Ratio (DSR)
- Bootstrap Sharpe CI
- Statistical significance (p < 0.05)

Usage:
    python scripts/run_strategy_validation.py --strategy cam
    python scripts/run_strategy_validation.py --strategy sp
    python scripts/run_strategy_validation.py --strategy mrm
    python scripts/run_strategy_validation.py --all
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ── Data Loading ──

def load_research_data() -> list[dict]:
    """Load research data (NOT sacred holdout)."""
    data_file = PROJECT_ROOT / "data" / "rydc" / "rydc_research.csv"
    if not data_file.exists():
        print(f"ERROR: {data_file} not found")
        sys.exit(1)

    rows = []
    with open(data_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "date": row["date"],
                "xau_close": float(row["xau_close"]),
                "xau_high": float(row["xau_high"]),
                "xau_low": float(row["xau_low"]),
                "dxy_close": float(row["dxy_close"]),
                "dfii10": float(row["dfii10"]),
            })
    return rows


# ── Signal Generation (Strategy Adapters) ──

def _load_module(name: str, path: Path):
    """Load module directly to avoid strategies/__init__.py relative imports."""
    import importlib.util
    import sys as _sys
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    _sys.modules[name] = mod  # register before exec (needed for dataclass frozen)
    spec.loader.exec_module(mod)
    return mod


def generate_cam_signals(data: list[dict]) -> list[int]:
    """Generate Cross-Asset Momentum signals."""
    mod = _load_module("cam", PROJECT_ROOT / "strategies" / "cross_asset_momentum.py")
    config = mod.CAMConfig()
    xau_close = pd.Series([d["xau_close"] for d in data])
    dxy_close = pd.Series([d["dxy_close"] for d in data])
    result = mod.compute_cam_signals(xau_close, dxy_close, config=config)
    return result.signal.tolist()  # NamedTuple, not dict


def generate_sp_signals(data: list[dict]) -> list[int]:
    """Generate Session Pattern signals."""
    mod = _load_module("sp", PROJECT_ROOT / "strategies" / "session_pattern.py")
    config = mod.SPConfig()
    # SP needs DatetimeIndex on close/highs/lows for session classification
    idx = pd.to_datetime([d["date"] for d in data])
    close = pd.Series([d["xau_close"] for d in data], index=idx)
    highs = pd.Series([d["xau_high"] for d in data], index=idx)
    lows = pd.Series([d["xau_low"] for d in data], index=idx)
    result = mod.compute_sp_signals(close, highs, lows, timestamps=idx, config=config)
    return result.signal.tolist()  # NamedTuple, not dict


def generate_mrm_signals(data: list[dict]) -> list[int]:
    """Generate Macro Regime MR signals."""
    mod = _load_module("mrm", PROJECT_ROOT / "strategies" / "macro_regime_mr.py")
    config = mod.MRMConfig()
    close = pd.Series([d["xau_close"] for d in data])
    highs = pd.Series([d["xau_high"] for d in data])
    lows = pd.Series([d["xau_low"] for d in data])
    dfii10 = pd.Series([d["dfii10"] for d in data])
    result = mod.compute_mrm_signals(close, highs, lows, dfii10, config=config)
    return result.signal.tolist()


def generate_gss_signals(data: list[dict]) -> list[int]:
    """Generate Gold-Silver Spread signals. Needs XAGUSD data."""
    # Load XAGUSD from existing CSV
    xag_file = PROJECT_ROOT / "data" / "XAGUSD_D1.csv"
    if not xag_file.exists():
        raise FileNotFoundError(f"XAGUSD data not found: {xag_file}")

    xag_rows = []
    with open(xag_file, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                xag_rows.append({"date": row["time"].split(" ")[0], "close": float(row["close"])})
            except (ValueError, KeyError):
                continue

    # Align by date
    xag_by_date = {r["date"]: r["close"] for r in xag_rows}
    xag_close = pd.Series([xag_by_date.get(d["date"], np.nan) for d in data])

    mod = _load_module("gss", PROJECT_ROOT / "strategies" / "gold_silver_spread.py")
    config = mod.GSSConfig()
    close = pd.Series([d["xau_close"] for d in data])
    highs = pd.Series([d["xau_high"] for d in data])
    lows = pd.Series([d["xau_low"] for d in data])
    result = mod.compute_gss_signals(close, highs, lows, xag_close, config=config)
    return result.signal.tolist()


def generate_bvc_signals(data: list[dict]) -> list[int]:
    """Generate BTC Vol Clustering signals. Needs BTCUSD data."""
    btc_file = PROJECT_ROOT / "data" / "BTCUSD_D1.csv"
    if not btc_file.exists():
        raise FileNotFoundError(f"BTCUSD data not found: {btc_file}")

    btc_rows = []
    with open(btc_file, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                btc_rows.append({
                    "date": row["time"].split(" ")[0],
                    "close": float(row["close"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                })
            except (ValueError, KeyError):
                continue

    btc_by_date = {r["date"]: r for r in btc_rows}
    # Use BTCUSD data directly (not aligned to XAUUSD dates)
    close = pd.Series([btc_by_date[d]["close"] for d in [r["date"] for r in btc_rows] if d in btc_by_date])
    highs = pd.Series([btc_by_date[d]["high"] for d in [r["date"] for r in btc_rows] if d in btc_by_date])
    lows = pd.Series([btc_by_date[d]["low"] for d in [r["date"] for r in btc_rows] if d in btc_by_date])

    mod = _load_module("bvc", PROJECT_ROOT / "strategies" / "btc_vol_clustering.py")
    config = mod.BVCConfig()
    result = mod.compute_bvc_signals(close, highs, lows, config=config)
    return result.signal.tolist()


def generate_cvr_signals(data: list[dict]) -> list[int]:
    """Generate Cross-Asset Vol Rank signals. Uses XAUUSD (available)."""
    mod = _load_module("cvr", PROJECT_ROOT / "strategies" / "cross_asset_vol_rank.py")
    config = mod.CVRConfig()
    close = pd.Series([d["xau_close"] for d in data])
    highs = pd.Series([d["xau_high"] for d in data])
    lows = pd.Series([d["xau_low"] for d in data])
    result = mod.compute_cvr_signals(close, highs, lows, config=config)
    return result.signal.tolist()  # NamedTuple, not dict


# ── Backtest Engine ──

def simulate_trades(data: list[dict], signals: list[int], hold_days: int = 4) -> list[float]:
    """Simulate trades from signals with fixed hold period."""
    trade_returns = []
    hold_counter = 0
    entry_price = 0.0
    position_type = None  # 1 = long, -1 = short

    for i in range(len(data)):
        row = data[i]
        signal = signals[i] if i < len(signals) else 0

        # Exit check
        if hold_counter > 0:
            hold_counter -= 1
            if hold_counter == 0:
                if position_type == 1:
                    pnl = (row["xau_close"] - entry_price) / entry_price
                else:
                    pnl = (entry_price - row["xau_close"]) / entry_price
                trade_returns.append(pnl)
                position_type = None
            continue

        # Entry
        if signal == 1:
            entry_price = row["xau_close"]
            hold_counter = hold_days
            position_type = 1
        elif signal == -1:
            entry_price = row["xau_close"]
            hold_counter = hold_days
            position_type = -1

    return trade_returns


# ── WFA ──

def run_wfa(data, signals, hold_days, n_folds=5):
    """Walk-Forward Analysis."""
    fold_size = len(data) // (n_folds + 1)
    oos_results = []
    is_sharpes = []
    oos_sharpes = []

    for fold in range(n_folds):
        is_start = fold * fold_size
        is_end = is_start + fold_size
        oos_start = is_end
        oos_end = min(oos_start + fold_size, len(data))

        if oos_end <= oos_start:
            continue

        # IS
        is_returns = simulate_trades(data[is_start:is_end], signals[is_start:is_end], hold_days)
        is_sharpe = compute_sharpe(is_returns)
        is_sharpes.append(is_sharpe)

        # OOS
        oos_returns = simulate_trades(data[oos_start:oos_end], signals[oos_start:oos_end], hold_days)
        oos_sharpe = compute_sharpe(oos_returns)
        oos_sharpes.append(oos_sharpe)

        oos_results.append({
            "fold": fold,
            "trades": len(oos_returns),
            "returns": oos_returns,
            "sharpe": oos_sharpe,
            "total_pnl": sum(oos_returns),
        })

    oos_positive = sum(1 for r in oos_results if r["total_pnl"] > 0)
    oos_ratio = oos_positive / len(oos_results) if oos_results else 0.0

    min_trades_for_sharpe = 10
    valid_is = [s for s, r in zip(is_sharpes, oos_results) if r["trades"] >= min_trades_for_sharpe]
    valid_oos = [s for s, r in zip(oos_sharpes, oos_results) if r["trades"] >= min_trades_for_sharpe]

    if valid_is and valid_oos:
        avg_is = np.mean(valid_is)
        avg_oos = np.mean(valid_oos)
        wfe = avg_oos / avg_is if avg_is > 0 else 0.0
    else:
        wfe = float('nan')

    return oos_ratio, wfe, oos_results


# ── Metrics ──

def compute_sharpe(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    arr = np.array(returns)
    mean = np.mean(arr)
    std = np.std(arr, ddof=1)
    if std == 0:
        return 0.0
    return (mean / std) * math.sqrt(63)


def compute_deflated_sharpe(sharpe: float, n_trials: int, n_obs: int) -> float:
    from scipy import stats

    if n_obs < 30:
        return float('nan')

    sr_se = math.sqrt(max(1.0 / (n_obs - 1), 1e-12))
    if sr_se < 1e-10:
        return float('nan')

    euler_mascheroni = 0.5772
    e_max_sharpe = sr_se * (
        (1 - euler_mascheroni) * stats.norm.ppf(1 - 1/n_trials) +
        euler_mascheroni * stats.norm.ppf(1 - 1/(n_trials * math.e))
    )

    dsr = stats.norm.cdf((sharpe - e_max_sharpe) / sr_se)
    return dsr


def bootstrap_sharpe_ci(returns: list[float], n_bootstrap: int = 1000, block_size: int = 4) -> tuple:
    arr = np.array(returns)
    n = len(arr)
    if n < block_size:
        return -999.0, -999.0

    sharpes = []
    for _ in range(n_bootstrap):
        blocks = []
        while len(blocks) < n:
            start = np.random.randint(0, n - block_size + 1)
            blocks.extend(arr[start:start + block_size])
        sample = np.array(blocks[:n])
        mean_ret = np.mean(sample)
        std_ret = np.std(sample, ddof=1)
        if std_ret > 0:
            sharpes.append((mean_ret / std_ret) * math.sqrt(63))

    if not sharpes:
        return -999.0, -999.0

    lower = np.percentile(sharpes, 2.5)
    upper = np.percentile(sharpes, 97.5)
    return float(lower), float(upper)


# ── Main ──

def validate_strategy(name: str, data: list[dict], signals: list[int], trial_number: int) -> dict:
    """Run full validation for one strategy."""
    print(f"\n{'='*60}")
    print(f"  VALIDATING: {name} (trial #{trial_number})")
    print(f"{'='*60}")

    # Split: 60% IS, 40% OOS
    split_idx = int(len(data) * 0.6)
    oos_data = data[split_idx:]
    oos_signals = signals[split_idx:]

    # OOS backtest
    oos_returns = simulate_trades(oos_data, oos_signals)
    n_trades = len(oos_returns)
    print(f"\n  OOS trades: {n_trades}")

    if n_trades == 0:
        print("  No trades generated — FAIL")
        return {"name": name, "status": "NO_TRADES", "overall": "FAIL"}

    win_rate = sum(1 for r in oos_returns if r > 0) / n_trades
    total_pnl = sum(oos_returns)
    mean_ret = np.mean(oos_returns)
    std_ret = np.std(oos_returns, ddof=1)
    sharpe = (mean_ret / std_ret) * math.sqrt(63) if std_ret > 0 else 0.0

    print(f"  Win rate: {win_rate:.2%}")
    print(f"  Total PnL: {total_pnl:.4f}")
    print(f"  Sharpe: {sharpe:.3f}")

    # Statistical significance
    from scipy import stats as sp_stats
    t_stat, p_value = sp_stats.ttest_1samp(oos_returns, 0)
    print(f"  t-stat: {t_stat:.3f}")
    print(f"  p-value: {p_value:.4f}")

    # WFA
    wfa_oos_ratio, wfe, wfa_results = run_wfa(data, signals, hold_days=4)
    print(f"  WFA OOS positive: {wfa_oos_ratio:.2%}")
    print(f"  WFE: {wfe:.3f}")

    # DSR
    dsr = compute_deflated_sharpe(sharpe, trial_number, n_trades)
    print(f"  DSR: {dsr:.6f}" if not math.isnan(dsr) else "  DSR: NaN")

    # Bootstrap CI
    ci_lower, ci_upper = bootstrap_sharpe_ci(oos_returns)
    print(f"  Bootstrap 95% CI: [{ci_lower:.3f}, {ci_upper:.3f}]")

    # Gate checks
    gate_p = "PASS" if p_value < 0.05 else "FAIL"
    gate_wfa = "PASS" if wfa_oos_ratio >= 0.7 else "FAIL"
    gate_wfe = "PASS" if (not math.isnan(wfe) and 0.5 <= wfe <= 1.5) else ("INSUFFICIENT_DATA" if math.isnan(wfe) else "FAIL")
    gate_dsr = "PASS" if (not math.isnan(dsr) and dsr > 0.95) else ("INSUFFICIENT_DATA" if math.isnan(dsr) else "FAIL")
    gate_ci = "PASS" if ci_lower > 0 else "FAIL"
    gate_trades = "PASS" if n_trades >= 100 else "FAIL"

    gates = [gate_p, gate_wfa, gate_wfe, gate_dsr, gate_ci, gate_trades]
    pass_count = sum(1 for g in gates if g == "PASS")
    fail_count = sum(1 for g in gates if g == "FAIL")
    overall = "PASS" if fail_count == 0 else "FAIL"

    print(f"\n  Gate Results:")
    print(f"  {'p-value':<25} {p_value:.4f}   {'< 0.05':<10} {gate_p}")
    print(f"  {'WFA OOS positive':<25} {wfa_oos_ratio:.2%}   {'>= 70%':<10} {gate_wfa}")
    print(f"  {'WFE':<25} {wfe:.3f}     {'>=0.5&<1.5':<10} {gate_wfe}")
    print(f"  {'DSR':<25} {dsr:.6f}  {'> 0.95':<10} {gate_dsr}")
    print(f"  {'Bootstrap CI lower':<25} {ci_lower:.3f}   {'> 0':<10} {gate_ci}")
    print(f"  {'Min trades':<25} {n_trades:<10} {'>= 100':<10} {gate_trades}")
    print(f"\n  Overall: {overall} ({pass_count}/{pass_count+fail_count} PASS)")

    return {
        "name": name,
        "trial_number": trial_number,
        "n_trades": n_trades,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "sharpe": sharpe,
        "t_stat": float(t_stat),
        "p_value": float(p_value),
        "wfa_oos_ratio": wfa_oos_ratio,
        "wfe": wfe,
        "dsr": dsr,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "gates": {
            "p_value": gate_p,
            "wfa_oos_positive": gate_wfa,
            "wfe": gate_wfe,
            "dsr": gate_dsr,
            "bootstrap_ci": gate_ci,
            "min_trades": gate_trades,
        },
        "overall": overall,
        "pass_count": pass_count,
        "fail_count": fail_count,
    }


# ── Direction C Data Loading ──

def load_direction_c_data() -> dict:
    """Load BTC/ETH research data for Direction C strategies."""
    btc_file = PROJECT_ROOT / "data" / "direction_c" / "btc_research.csv"
    eth_file = PROJECT_ROOT / "data" / "direction_c" / "eth_research.csv"

    def load_csv(path):
        rows = []
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    rows.append({
                        "date": row["date"],
                        "close": float(row["close"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "volume": float(row["volume"]),
                    })
                except (ValueError, KeyError):
                    continue
        return rows

    btc = load_csv(btc_file) if btc_file.exists() else []
    eth = load_csv(eth_file) if eth_file.exists() else []

    # Align by date
    btc_by_date = {r["date"]: r for r in btc}
    eth_by_date = {r["date"]: r for r in eth}
    common_dates = sorted(set(btc_by_date.keys()) & set(eth_by_date.keys()))

    return {
        "btc": [btc_by_date[d] for d in common_dates],
        "eth": [eth_by_date[d] for d in common_dates],
        "dates": common_dates,
    }


# ── Direction C Signal Generators ──

def generate_btcvd_signals(data: list[dict]) -> list[int]:
    """Generate BTC Volume Divergence signals (uses Direction C data)."""
    dc = load_direction_c_data()
    if not dc["btc"]:
        raise FileNotFoundError("Direction C BTC data not found")
    mod = _load_module("btcvd", PROJECT_ROOT / "strategies" / "btc_vol_divergence.py")
    config = mod.BTCVolDivConfig()
    close = pd.Series([d["close"] for d in dc["btc"]])
    highs = pd.Series([d["high"] for d in dc["btc"]])
    lows = pd.Series([d["low"] for d in dc["btc"]])
    volume = pd.Series([d["volume"] for d in dc["btc"]])
    result = mod.compute_btcvd_signals(close, highs, lows, volume, config=config)
    return result.signal.tolist()


def generate_ethvc_signals(data: list[dict]) -> list[int]:
    """Generate ETH Volume Confirm signals (uses Direction C data)."""
    dc = load_direction_c_data()
    if not dc["eth"]:
        raise FileNotFoundError("Direction C ETH data not found")
    mod = _load_module("ethvc", PROJECT_ROOT / "strategies" / "eth_vol_confirm.py")
    config = mod.ETHVolConfirmConfig()
    close = pd.Series([d["close"] for d in dc["eth"]])
    highs = pd.Series([d["high"] for d in dc["eth"]])
    lows = pd.Series([d["low"] for d in dc["eth"]])
    volume = pd.Series([d["volume"] for d in dc["eth"]])
    result = mod.compute_ethvc_signals(close, highs, lows, volume, config=config)
    return result.signal.tolist()


def generate_bevs_signals(data: list[dict]) -> list[int]:
    """Generate BTC-ETH Vol Spread signals (uses Direction C data)."""
    dc = load_direction_c_data()
    if not dc["btc"] or not dc["eth"]:
        raise FileNotFoundError("Direction C data not found")
    mod = _load_module("bevs", PROJECT_ROOT / "strategies" / "btc_eth_vol_spread.py")
    config = mod.BTCETHVolSpreadConfig()
    btc_close = pd.Series([d["close"] for d in dc["btc"]])
    btc_volume = pd.Series([d["volume"] for d in dc["btc"]])
    eth_close = pd.Series([d["close"] for d in dc["eth"]])
    eth_volume = pd.Series([d["volume"] for d in dc["eth"]])
    result = mod.compute_bevs_signals(btc_close, btc_volume, eth_close, eth_volume, config=config)
    return result.signal.tolist()


def main():
    parser = argparse.ArgumentParser(description="Validate strategies through fixed gates")
    parser.add_argument("--strategy", choices=["cam", "sp", "mrm", "gss", "bvc", "cvr", "btcvd", "ethvc", "bevs", "all"], default="all")
    parser.add_argument("--bootstrap", type=int, default=1000)
    args = parser.parse_args()

    data = load_research_data()
    print(f"Research data: {len(data)} rows ({data[0]['date']} to {data[-1]['date']})")

    # Load Direction C data (BTC/ETH with volume)
    dc_data = load_direction_c_data()

    strategies = {
        "cam": ("Cross-Asset Momentum", 1003, generate_cam_signals),
        "sp": ("Session Pattern", 1004, generate_sp_signals),
        "mrm": ("Macro Regime MR", 1005, generate_mrm_signals),
        "gss": ("Gold-Silver Spread", 1006, generate_gss_signals),
        "bvc": ("BTC Vol Clustering", 1007, generate_bvc_signals),
        "cvr": ("Cross-Asset Vol Rank", 1008, generate_cvr_signals),
        "btcvd": ("BTC Vol Divergence", 2001, generate_btcvd_signals),
        "ethvc": ("ETH Vol Confirm", 2002, generate_ethvc_signals),
        "bevs": ("BTC-ETH Vol Spread", 2003, generate_bevs_signals),
    }

    results = []
    for key, (name, trial, gen_fn) in strategies.items():
        if args.strategy in ("all", key):
            try:
                # Direction C strategies use their own BTC/ETH data
                if key in ("btcvd", "ethvc", "bevs"):
                    dc = load_direction_c_data()
                    if key == "bevs":
                        # BEVS needs aligned BTC+ETH data as list of dicts
                        aligned = [{"date": d, "xau_close": dc["btc"][i]["close"], "xau_high": dc["btc"][i]["high"], "xau_low": dc["btc"][i]["low"],
                                    "dxy_close": dc["eth"][i]["close"], "dfii10": dc["eth"][i]["volume"]}
                                   for i, d in enumerate(dc["dates"])]
                        signals = gen_fn(aligned)
                    else:
                        # BTCVD/ETHVC load their own data internally
                        signals = gen_fn(data)
                    # Use BTC data for trade simulation
                    sim_data = [{"date": d, "xau_close": dc["btc"][i]["close"], "xau_high": dc["btc"][i]["high"], "xau_low": dc["btc"][i]["low"]}
                                for i, d in enumerate(dc["dates"])]
                    result = validate_strategy(name, sim_data, signals, trial)
                else:
                    signals = gen_fn(data)
                    result = validate_strategy(name, data, signals, trial)
                results.append(result)
            except Exception as e:
                print(f"\n  ERROR validating {name}: {e}")
                results.append({"name": name, "status": f"ERROR: {e}", "overall": "FAIL"})

    # Summary
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    print(f"{'Strategy':<30} {'Trades':>8} {'Win%':>8} {'Sharpe':>8} {'p-val':>8} {'Verdict':>10}")
    print("-" * 80)
    for r in results:
        if r.get("status") == "NO_TRADES":
            print(f"{r['name']:<30} {'0':>8} {'N/A':>8} {'N/A':>8} {'N/A':>8} {'NO_TRADES':>10}")
        elif r.get("status", "").startswith("ERROR"):
            print(f"{r['name']:<30} {'ERR':>8} {'ERR':>8} {'ERR':>8} {'ERR':>8} {r['status'][:10]:>10}")
        else:
            print(f"{r['name']:<30} {r['n_trades']:>8} {r['win_rate']:>7.1%} {r['sharpe']:>8.3f} {r['p_value']:>8.4f} {r['overall']:>10}")

    # Save
    output_file = PROJECT_ROOT / "reports" / f"strategy_validation_{datetime.now():%Y%m%d_%H%M%S}.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved: {output_file}")


if __name__ == "__main__":
    main()
