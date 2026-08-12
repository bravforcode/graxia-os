"""
TSM Portfolio Construction — Multi-Lookback + Vol-Targeting + Inverse-Vol Combination.

Combines short-term (20d) and long-term (120d) TSM sleeves with proper
vol-targeting and inverse-vol weighting across assets.

Architecture:
  1. Per-sleeve: signal = sign(lookback_return)
  2. Per-sleeve: asset weights = signal * inv_vol(asset) [normalized]
  3. Combine sleeves: inv_vol(sleeve) weighting
  4. Portfolio-level vol-targeting: scale to 10% annualized vol
  5. Cap leverage at 1.0

Usage:
    python scripts/tsm_portfolio.py
"""

from pathlib import Path
import json
import pandas as pd
import numpy as np
from scipy import stats

BASE = Path(__file__).resolve().parent.parent
ARTIFACTS = BASE / "artifacts"
OUT_DIR = ARTIFACTS / "portfolio"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Config ──
TARGET_VOL = 0.10
LOOKBACKS = [20, 120]
REBALANCE_FREQ = "W-FRI"
COST_BPS = 5
RVOL_WINDOW = 20
CORR_WINDOW = 60
MAX_LEVERAGE = 1.0

ASSETS = [
    "XAUUSD", "EURUSD_YF", "GBPUSD_YF", "USDJPY",
    "BTC_YF", "ETH_YF", "SILVER", "OIL",
]


# ─────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────

def load_data() -> pd.DataFrame:
    path = OUT_DIR / "d1_multi_asset.parquet"
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index, utc=True)
    return df.sort_index()


def get_close_matrix(data: pd.DataFrame) -> pd.DataFrame:
    cols = {}
    for asset in ASSETS:
        col = f"{asset}_close"
        if col in data.columns:
            cols[asset] = data[col]
    return pd.DataFrame(cols)


# ─────────────────────────────────────────────
# Signals & Weights
# ─────────────────────────────────────────────

def tsm_signal(close: pd.Series, lookback: int) -> pd.Series:
    return np.sign(close.pct_change(lookback, fill_method=None))


def inv_vol_weights(ret_df: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """Inverse-volatility weights across columns, normalized to sum to 1."""
    rvol = ret_df.rolling(window, min_periods=20).std()
    inv = 1.0 / rvol.replace(0, np.nan)
    row_sums = inv.sum(axis=1)
    return inv.div(row_sums, axis=0)


def rebalance_weekly(weight: pd.DataFrame) -> pd.DataFrame:
    """Forward-fill weights to weekly Friday rebalance."""
    weekly = weight.resample(REBALANCE_FREQ).last()
    return weekly.reindex(weight.index, method="ffill")


def sleeve_raw_weights(
    close_matrix: pd.DataFrame, lookback: int
) -> pd.DataFrame:
    """
    Compute raw sleeve weights per asset:
      raw_weight = signal(asset, lookback) * inv_vol_weight(asset)
    Normalized so sum(|weights|) = 1 per row.
    """
    # Signals
    signals = close_matrix.apply(lambda c: tsm_signal(c, lookback))

    # Asset daily returns for vol estimation
    daily_ret = close_matrix.pct_change(1, fill_method=None)

    # Inverse-vol weights
    iv = inv_vol_weights(daily_ret, RVOL_WINDOW)

    # Raw weight = signal * inv_vol_share
    raw = signals * iv

    # Normalize so sum(|w|) = 1
    abs_sum = raw.abs().sum(axis=1).replace(0, np.nan)
    normalized = raw.div(abs_sum, axis=0)

    # Rebalance weekly
    normalized = rebalance_weekly(normalized)

    return normalized


def portfolio_backtest(
    close_matrix: pd.DataFrame,
    lookbacks: list[int],
    target_vol: float,
    cost_bps: float,
) -> tuple[pd.Series, pd.DataFrame, dict]:
    """
    Full portfolio backtest with multi-lookback combination + portfolio vol-targeting.

    Returns: (portfolio_return, sleeve_weights_df, details)
    """
    # Step 1: Compute raw weights per sleeve
    sleeve_w = {}
    for lb in lookbacks:
        sleeve_w[lb] = sleeve_raw_weights(close_matrix, lb)

    # Step 2: Combine sleeves using inverse-vol of sleeve returns
    # First compute sleeve returns (before vol-targeting)
    daily_ret = close_matrix.pct_change(1, fill_method=None)

    sleeve_rets = {}
    for lb in lookbacks:
        sw = sleeve_w[lb]
        # Sleeve return = sum(asset_weight * asset_return), shift by 1 for execution
        sr = (sw.shift(1) * daily_ret).sum(axis=1)
        sleeve_rets[lb] = sr

    sleeve_ret_df = pd.DataFrame(sleeve_rets)

    # Inverse-vol weights across sleeves
    sleeve_iv = inv_vol_weights(sleeve_ret_df, window=60)

    # Combined raw portfolio return (before vol-targeting)
    combined_raw = (sleeve_ret_df * sleeve_iv).sum(axis=1)

    # Step 3: Portfolio-level vol-targeting
    # Compute rolling realized vol of the combined raw return
    port_rvol = combined_raw.rolling(RVOL_WINDOW, min_periods=10).std() * np.sqrt(252)
    port_rvol = port_rvol.replace(0, np.nan)

    # Scale factor = target_vol / realized_vol
    vol_scale = target_vol / port_rvol

    # Cap leverage: total abs weight cannot exceed MAX_LEVERAGE
    # vol_scale is a scalar multiplier on the already-normalized weights
    vol_scale = vol_scale.clip(0, MAX_LEVERAGE)

    # Apply vol targeting
    portfolio_ret = combined_raw * vol_scale

    # Step 4: Transaction costs
    # Cost proportional to changes in vol_scale and sleeve weights
    vol_scale_change = vol_scale.diff().abs()
    cost = vol_scale_change * cost_bps / 10000
    portfolio_ret_net = portfolio_ret - cost

    details = {
        "sleeve_raw_weights": sleeve_w,
        "sleeve_returns": sleeve_ret_df,
        "sleeve_inv_vol_weights": sleeve_iv,
        "vol_scale": vol_scale,
        "port_rvol": port_rvol,
    }

    return portfolio_ret_net, sleeve_iv, details


# ─────────────────────────────────────────────
# Correlation Monitoring
# ─────────────────────────────────────────────

def rolling_correlation(returns: pd.DataFrame, window: int = 60) -> pd.Series:
    """Rolling average pairwise cross-asset correlation."""
    n = returns.shape[1]
    if n < 2:
        return pd.Series(dtype=float)

    corrs = []
    for i in range(n):
        for j in range(i + 1, n):
            c = returns.iloc[:, i].rolling(window).corr(returns.iloc[:, j])
            corrs.append(c)

    return pd.concat(corrs, axis=1).mean(axis=1)


# ─────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────

def compute_metrics(ret: pd.Series, name: str = "") -> dict:
    """Sharpe, Sortino, Max DD, Calmar, skew, kurtosis."""
    ret = ret.dropna()
    if len(ret) < 60:
        return {"name": name}

    ann_ret = ret.mean() * 252
    ann_vol = ret.std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0

    downside = ret[ret < 0]
    down_std = downside.std() * np.sqrt(252) if len(downside) > 0 else 0.0
    sortino = ann_ret / down_std if down_std > 0 else 0.0

    cum = (1 + ret).cumprod()
    peak = cum.cummax()
    dd = (cum - peak) / peak
    max_dd = dd.min()
    calmar = ann_ret / abs(max_dd) if max_dd != 0 else 0.0

    return {
        "name": name,
        "ann_ret": float(ann_ret),
        "ann_vol": float(ann_vol),
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "max_dd": float(max_dd),
        "calmar": float(calmar),
        "skew": float(ret.skew()),
        "kurtosis": float(ret.kurtosis()),
        "win_rate": float((ret > 0).mean()),
        "n_days": int(len(ret)),
    }


def deflated_sharpe_test(sharpe: float, n_obs: int, n_trials: int) -> dict:
    se = np.sqrt((1 + 0.5 * sharpe**2) / n_obs)
    z = sharpe / se
    p_single = 1 - stats.norm.cdf(z)
    expected_max_z = np.sqrt(2 * np.log(n_trials))
    expected_max_sharpe = expected_max_z * se
    p_deflated = min(1.0, p_single * n_trials)

    return {
        "sharpe": round(sharpe, 4),
        "z_score": round(z, 4),
        "p_single": round(p_single, 6),
        "p_deflated": round(p_deflated, 6),
        "n_trials": n_trials,
        "expected_max_sharpe": round(expected_max_sharpe, 4),
        "significant_5pct": bool(p_deflated < 0.05),
    }


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    print("=" * 65)
    print("TSM Portfolio -- Multi-Lookback + Portfolio Vol-Targeting")
    print("=" * 65)

    data = load_data()
    close_matrix = get_close_matrix(data)
    print(f"\nData: {len(data)} rows, {data.index.min().date()} to {data.index.max().date()}")
    print(f"Assets: {list(close_matrix.columns)}")
    print(f"Lookbacks: {LOOKBACKS}")
    print(f"Target vol: {TARGET_VOL:.0%}  Cost: {COST_BPS} bps  Rebalance: {REBALANCE_FREQ}")

    # ── Full-period backtest ──
    port_ret, sleeve_iv, details = portfolio_backtest(
        close_matrix, LOOKBACKS, TARGET_VOL, COST_BPS
    )

    # ── Portfolio metrics ──
    m = compute_metrics(port_ret, "combined")
    print("\n--- Portfolio Metrics ---")
    print(f"  Ann ret:   {m.get('ann_ret', 0):.2%}")
    print(f"  Ann vol:   {m.get('ann_vol', 0):.2%}")
    print(f"  Sharpe:    {m.get('sharpe', 0):.3f}")
    print(f"  Sortino:   {m.get('sortino', 0):.3f}")
    print(f"  Max DD:    {m.get('max_dd', 0):.2%}")
    print(f"  Calmar:    {m.get('calmar', 0):.3f}")
    print(f"  Skew:      {m.get('skew', 0):.3f}")
    print(f"  Kurtosis:  {m.get('kurtosis', 0):.3f}")
    print(f"  Win rate:  {m.get('win_rate', 0):.1%}")

    # ── Per-sleeve metrics ──
    sleeve_metrics = {}
    for lb in LOOKBACKS:
        sr = details["sleeve_returns"][lb].dropna()
        sm = compute_metrics(sr, f"lb{lb}")
        sleeve_metrics[lb] = sm
        print(f"\n--- Sleeve {lb}d ---")
        print(f"  Ann ret: {sm.get('ann_ret', 0):.2%}  Sharpe: {sm.get('sharpe', 0):.3f}  Max DD: {sm.get('max_dd', 0):.2%}")

    # ── Sleeve weights (recent) ──
    print("\n--- Sleeve Weights (recent) ---")
    if not sleeve_iv.dropna().empty:
        recent = sleeve_iv.dropna().iloc[-1]
        for lb in LOOKBACKS:
            print(f"  {lb}d: {recent.get(lb, 0):.3f}")

    # ── Correlation monitor ──
    print(f"\n--- Correlation Monitor ({CORR_WINDOW}d) ---")
    daily_ret = close_matrix.pct_change(1, fill_method=None)
    avg_corr = rolling_correlation(daily_ret, CORR_WINDOW)
    if not avg_corr.dropna().empty:
        mean_corr = avg_corr.mean()
        recent_corr = avg_corr.dropna().iloc[-1]
        high_pct = (avg_corr > 0.5).mean()
        print(f"  Mean pairwise:    {mean_corr:.3f}")
        print(f"  Recent:           {recent_corr:.3f}")
        print(f"  Days corr > 0.5:  {high_pct:.1%}")
    else:
        mean_corr = np.nan
        recent_corr = np.nan
        high_pct = np.nan
        print("  Insufficient data")

    # ── Vol-targeting check ──
    vol_scale = details["vol_scale"]
    port_rvol = details["port_rvol"]
    if not vol_scale.dropna().empty:
        print("\n--- Vol Targeting ---")
        print(f"  Mean vol scale:   {vol_scale.mean():.3f}")
        print(f"  Recent vol scale: {vol_scale.dropna().iloc[-1]:.3f}")
        print(f"  Mean rvol (ann):  {port_rvol.mean():.2%}")

    # ── Walk-forward ──
    print("\n--- Walk-Forward (60/40) ---")
    n = len(data)
    train_end = int(n * 0.6)
    for label, sl in [("Train", slice(None, train_end)), ("Test", slice(train_end, None))]:
        sub = close_matrix.iloc[sl]
        sub_ret, _, _ = portfolio_backtest(sub, LOOKBACKS, TARGET_VOL, COST_BPS)
        sub_m = compute_metrics(sub_ret, label.lower())
        print(f"  {label}: Sharpe={sub_m.get('sharpe', 0):.3f}  "
              f"Ann ret={sub_m.get('ann_ret', 0):.2%}  Max DD={sub_m.get('max_dd', 0):.2%}")

    # ── Deflated Sharpe ──
    n_trials = len(LOOKBACKS) * 2
    dsr = deflated_sharpe_test(m.get("sharpe", 0), m.get("n_days", 0), n_trials)
    print("\n--- Deflated Sharpe ---")
    print(f"  z={dsr['z_score']:.4f}  p_single={dsr['p_single']:.6f}  p_deflated={dsr['p_deflated']:.6f}")
    print(f"  Significant: {'YES' if dsr['significant_5pct'] else 'NO'}")

    # ── Save results ──
    results = {
        "config": {
            "target_vol": TARGET_VOL,
            "lookbacks": LOOKBACKS,
            "rebalance": REBALANCE_FREQ,
            "cost_bps": COST_BPS,
            "rvol_window": RVOL_WINDOW,
            "corr_window": CORR_WINDOW,
            "max_leverage": MAX_LEVERAGE,
            "assets": list(close_matrix.columns),
        },
        "data": {
            "rows": len(data),
            "start": str(data.index.min().date()),
            "end": str(data.index.max().date()),
        },
        "portfolio": m,
        "sleeves": {str(lb): sm for lb, sm in sleeve_metrics.items()},
        "correlation": {
            "window": CORR_WINDOW,
            "mean_pairwise": round(float(mean_corr), 4) if not np.isnan(mean_corr) else None,
            "recent": round(float(recent_corr), 4) if not np.isnan(recent_corr) else None,
            "high_corr_pct": round(float(high_pct), 4) if not np.isnan(high_pct) else None,
        },
        "sleeve_weights_recent": {
            str(lb): round(float(sleeve_iv.dropna().iloc[-1].get(lb, 0)), 4)
            for lb in LOOKBACKS
            if not sleeve_iv.dropna().empty
        },
        "deflated_sharpe": dsr,
    }

    out_path = OUT_DIR / "tsm_portfolio_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n[OK] Results saved to {out_path}")

    # ── Final table ──
    print("\n" + "=" * 75)
    print("FINAL METRICS TABLE")
    print("=" * 75)
    header = f"{'Config':>12} {'Sharpe':>8} {'Sortino':>8} {'AnnRet':>8} {'AnnVol':>8} {'MaxDD':>8} {'Calmar':>8} {'Skew':>7} {'Kurt':>7}"
    print(header)
    print("-" * 75)

    all_m = {**{f"lb{lb}": sm for lb, sm in sleeve_metrics.items()}, "combined": m}
    for key, entry in all_m.items():
        if "sharpe" not in entry:
            continue
        print(f"{key:>12} {entry['sharpe']:>8.3f} {entry.get('sortino', 0):>8.3f} "
              f"{entry['ann_ret']:>7.1%} {entry['ann_vol']:>7.1%} {entry['max_dd']:>7.1%} "
              f"{entry.get('calmar', 0):>8.3f} {entry.get('skew', 0):>7.3f} {entry.get('kurtosis', 0):>7.3f}")
    print("=" * 75)


if __name__ == "__main__":
    main()
