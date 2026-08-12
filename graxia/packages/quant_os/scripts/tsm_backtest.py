"""
Time-Series Momentum (TSM) Backtest — Multi-Asset D1 Portfolio.

Signal: sign(lookback_return) * vol_target / realized_vol
Rebalance: weekly (Friday close)
Assets: XAUUSD, EURUSD, GBPUSD, USDJPY, BTC, ETH, SILVER, OIL

Usage:
    python scripts/tsm_backtest.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

# Allow running from repo root
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.returns import compute_returns

BASE = Path(__file__).resolve().parent.parent
ARTIFACTS = BASE / "artifacts"
OUT_DIR = ARTIFACTS / "portfolio"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Config ──

TARGET_VOL = 0.10  # 10% annualized portfolio vol
LOOKBACK_WINDOWS = [20, 40, 60, 120]  # trading days
REBALANCE_FREQ = "W-FRI"  # weekly Friday
COST_BPS = 5  # round-trip cost in bps per trade

# Assets with close data in the D1 dataset
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


def load_data() -> pd.DataFrame:
    path = OUT_DIR / "d1_multi_asset.parquet"
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index, utc=True)
    return df.sort_index()


def compute_tsm_signal(close: pd.Series, lookback: int) -> pd.Series:
    """TSM signal: sign of lookback-period return (honest missing-bar handling)."""
    ret = compute_returns(close, lookback)
    return np.sign(ret)


def compute_vol_target_weight(close: pd.Series, lookback: int, target_vol: float, rvol_window: int = 20) -> pd.Series:
    """Vol-targeted position weight: signal * target_vol / realized_vol."""
    signal = compute_tsm_signal(close, lookback)
    daily_ret = compute_returns(close, 1)
    rvol = daily_ret.rolling(rvol_window).std() * np.sqrt(252)
    # Avoid division by zero
    rvol = rvol.replace(0, np.nan)
    weight = signal * target_vol / rvol
    # Cap at 1.0 (no leverage)
    return weight.clip(-1, 1)


def backtest_tsm_single_asset(close: pd.Series, lookback: int, target_vol: float, cost_bps: float) -> pd.DataFrame:
    """Backtest TSM on a single asset."""
    df = pd.DataFrame({"close": close})
    df["ret"] = compute_returns(df["close"], lookback=1)
    df["weight"] = compute_vol_target_weight(close, lookback, target_vol)

    # Rebalance weekly: forward-fill weight to weekly
    weekly_weight = df["weight"].resample(REBALANCE_FREQ).last()
    weekly_weight = weekly_weight.reindex(df.index, method="ffill")
    df["weight"] = weekly_weight

    # Strategy return = weight * asset return
    df["strat_ret"] = df["weight"].shift(1) * df["ret"]

    # Transaction costs: proportional to weight change
    df["weight_change"] = df["weight"].diff().abs()
    df["cost"] = df["weight_change"] * cost_bps / 10000
    df["strat_ret_net"] = df["strat_ret"] - df["cost"]

    # Cumulative
    df["cum_ret"] = (1 + df["strat_ret_net"]).cumprod()

    return df


def portfolio_backtest(
    data: pd.DataFrame, assets: list, lookback: int, target_vol: float, cost_bps: float
) -> pd.DataFrame:
    """Backtest multi-asset TSM portfolio with inverse-vol weighting."""
    asset_returns = {}
    asset_weights = {}

    for asset in assets:
        col = f"{asset}_close"
        if col not in data.columns:
            continue
        close = data[col].dropna()
        if len(close) < lookback + 60:
            continue

        bt = backtest_tsm_single_asset(close, lookback, target_vol, cost_bps)
        asset_returns[asset] = bt["strat_ret_net"]
        asset_weights[asset] = bt["weight"]

    if not asset_returns:
        return pd.DataFrame()

    ret_df = pd.DataFrame(asset_returns)
    weight_df = pd.DataFrame(asset_weights)

    # Inverse-vol weighting across assets
    asset_rvol = ret_df.rolling(60).std()
    inv_rvol = 1.0 / asset_rvol.replace(0, np.nan)
    inv_rvol = inv_rvol.div(inv_rvol.sum(axis=1), axis=0)

    # Portfolio return = sum(asset_weight * inv_vol_weight * asset_return)
    portfolio_ret = (ret_df * inv_rvol).sum(axis=1)

    result = pd.DataFrame(
        {
            "portfolio_ret": portfolio_ret,
            "cum_ret": (1 + portfolio_ret).cumprod(),
        }
    )

    return result


def compute_metrics(ret: pd.Series, name: str = "") -> dict:
    """Compute standard TSM metrics."""
    ret = ret.dropna()
    if len(ret) < 60:
        return {}

    ann_ret = ret.mean() * 252
    ann_vol = ret.std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0

    # Max drawdown
    cum = (1 + ret).cumprod()
    peak = cum.cummax()
    dd = (cum - peak) / peak
    max_dd = dd.min()

    # Win rate (daily)
    win_rate = (ret > 0).mean()

    # Skewness
    skew = ret.skew()

    return {
        "name": name,
        "ann_ret": ann_ret,
        "ann_vol": ann_vol,
        "sharpe": sharpe,
        "max_dd": max_dd,
        "win_rate": win_rate,
        "skew": skew,
        "n_days": len(ret),
    }


def deflated_sharpe_test(sharpe: float, n_obs: int, n_trials: int) -> dict:
    """Bailey & Lopez de Prado deflated Sharpe test."""
    # Standard error of Sharpe
    se = np.sqrt((1 + 0.5 * sharpe**2) / n_obs)
    z = sharpe / se
    p_single = 1 - stats.norm.cdf(z)

    # Expected max Sharpe from n_trials random trials
    expected_max_z = np.sqrt(2 * np.log(n_trials))
    expected_max_sharpe = expected_max_z * se

    # Bonferroni correction
    p_deflated = min(1.0, p_single * n_trials)

    return {
        "sharpe": sharpe,
        "z_score": z,
        "p_single": p_single,
        "p_deflated": p_deflated,
        "n_trials": n_trials,
        "expected_max_sharpe": expected_max_sharpe,
        "significant_5pct": p_deflated < 0.05,
    }


def walk_forward_tsm(
    data: pd.DataFrame, assets: list, lookback: int, target_vol: float, cost_bps: float, train_pct: float = 0.6
) -> dict:
    """Walk-forward validation of TSM strategy."""
    # Split data
    n = len(data)
    train_end = int(n * train_pct)

    train_data = data.iloc[:train_end]
    test_data = data.iloc[train_end:]

    # Train metrics
    train_bt = portfolio_backtest(train_data, assets, lookback, target_vol, cost_bps)
    train_metrics = compute_metrics(train_bt["portfolio_ret"], "train") if not train_bt.empty else {}

    # Test metrics
    test_bt = portfolio_backtest(test_data, assets, lookback, target_vol, cost_bps)
    test_metrics = compute_metrics(test_bt["portfolio_ret"], "test") if not test_bt.empty else {}

    return {
        "train": train_metrics,
        "test": test_metrics,
        "train_bt": train_bt,
        "test_bt": test_bt,
    }


def main():
    print("=== TSM Multi-Asset Backtest ===\n")

    data = load_data()
    print(f"Data: {len(data)} rows, {data.index.min()} to {data.index.max()}")
    print(f"Assets: {[a for a in ASSETS if f'{a}_close' in data.columns]}")
    print()

    results = []

    for lookback in LOOKBACK_WINDOWS:
        print(f"--- Lookback: {lookback} days ---")

        # Full-period backtest
        bt = portfolio_backtest(data, ASSETS, lookback, TARGET_VOL, COST_BPS)
        if bt.empty:
            print("  No data")
            continue

        metrics = compute_metrics(bt["portfolio_ret"], f"lb{lookback}")
        metrics["lookback"] = lookback
        results.append(metrics)

        print(f"  Ann ret: {metrics.get('ann_ret', 0):.2%}")
        print(f"  Ann vol: {metrics.get('ann_vol', 0):.2%}")
        print(f"  Sharpe:  {metrics.get('sharpe', 0):.3f}")
        print(f"  Max DD:  {metrics.get('max_dd', 0):.2%}")
        print(f"  Win rate: {metrics.get('win_rate', 0):.1%}")
        print(f"  Skew:    {metrics.get('skew', 0):.3f}")

        # Walk-forward
        wf = walk_forward_tsm(data, ASSETS, lookback, TARGET_VOL, COST_BPS)
        train_m = wf["train"]
        test_m = wf["test"]
        print(f"  WF Train Sharpe: {train_m.get('sharpe', 0):.3f}")
        print(f"  WF Test Sharpe:  {test_m.get('sharpe', 0):.3f}")

        # Deflated Sharpe (conservative: 4 lookbacks * 2 signal types = 8 trials)
        n_trials = len(LOOKBACK_WINDOWS) * 2  # sign-of-return + EMA crossover (future)
        dsr = deflated_sharpe_test(metrics.get("sharpe", 0), metrics.get("n_days", 0), n_trials)
        print(f"  Deflated Sharpe: p_single={dsr['p_single']:.4f} p_deflated={dsr['p_deflated']:.4f}")
        print(f"  Significant at 5%? {dsr['significant_5pct']}")
        print()

    # Summary table
    if results:
        print("\n=== SUMMARY ===")
        print(f"{'Lookback':>10} {'Sharpe':>8} {'Ann Ret':>8} {'Max DD':>8} {'Win%':>6} {'Deflated':>10}")
        for r in results:
            dsr = deflated_sharpe_test(r["sharpe"], r["n_days"], len(LOOKBACK_WINDOWS) * 2)
            sig = "YES" if dsr["significant_5pct"] else "NO"
            print(
                f"{r['lookback']:>10} {r['sharpe']:>8.3f} {r['ann_ret']:>7.1%} {r['max_dd']:>7.1%} {r['win_rate']:>5.1%} {sig:>10}"
            )


if __name__ == "__main__":
    main()
