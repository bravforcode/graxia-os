"""
EMA-Crossover Trend Signal — Multi-Asset D1 Portfolio.

Baz et al. 2015, Man AHL style.
Signal: sign(EMA_fast(t) - EMA_slow(t))
Rebalance: weekly (Friday close)
Cost: 5 bps per trade
Walk-forward: 60% train / 40% test

Usage:
    python scripts/tsm_ema.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

BASE = Path(__file__).resolve().parent.parent
ARTIFACTS = BASE / "artifacts"
OUT_DIR = ARTIFACTS / "portfolio"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Config ──────────────────────────────────────────────────────────────────

TARGET_VOL = 0.10  # 10% annualized portfolio vol
RVOL_WINDOW = 20  # realized vol lookback
REBALANCE_FREQ = "W-FRI"
COST_BPS = 5  # round-trip cost per trade in bps

# EMA combos to test (fast, slow)
EMA_COMBOS = [(10, 30), (20, 60), (40, 120), (60, 180)]

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

# Total trials across TSM backtest + EMA (4 sign-of-return + 4 EMA combos)
N_TRIALS = 8


# ── Data ────────────────────────────────────────────────────────────────────


def load_data() -> pd.DataFrame:
    path = OUT_DIR / "d1_multi_asset.parquet"
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index, utc=True)
    return df.sort_index()


# ── Signal ──────────────────────────────────────────────────────────────────


def ema_crossover_signal(close: pd.Series, fast: int, slow: int) -> pd.Series:
    """EMA-crossover signal: sign(EMA_fast - EMA_slow)."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    return np.sign(ema_fast - ema_slow)


def vol_targeted_weight(close: pd.Series, fast: int, slow: int,
                        target_vol: float, rvol_window: int) -> pd.Series:
    """Vol-targeted position: signal * target_vol / realized_vol, cap at 1.0."""
    signal = ema_crossover_signal(close, fast, slow)
    daily_ret = close.pct_change(1, fill_method=None)
    rvol = daily_ret.rolling(rvol_window).std() * np.sqrt(252)
    rvol = rvol.replace(0, np.nan)
    weight = signal * target_vol / rvol
    return weight.clip(-1, 1)


# ── Single-asset backtest ───────────────────────────────────────────────────


def backtest_single_asset(close: pd.Series, fast: int, slow: int,
                          target_vol: float, rvol_window: int,
                          cost_bps: float) -> pd.DataFrame:
    """Backtest EMA crossover on one asset."""
    df = pd.DataFrame({"close": close})
    df["ret"] = df["close"].pct_change(1, fill_method=None)
    df["weight"] = vol_targeted_weight(close, fast, slow, target_vol, rvol_window)

    # Rebalance weekly: sample weight at Friday close, forward-fill
    weekly_w = df["weight"].resample(REBALANCE_FREQ).last()
    weekly_w = weekly_w.reindex(df.index, method="ffill")
    df["weight"] = weekly_w

    # Strategy return (lagged weight)
    df["strat_ret"] = df["weight"].shift(1) * df["ret"]

    # Transaction costs proportional to |Δweight|
    df["weight_change"] = df["weight"].diff().abs()
    df["cost"] = df["weight_change"] * cost_bps / 10_000
    df["strat_ret_net"] = df["strat_ret"] - df["cost"]
    df["cum_ret"] = (1 + df["strat_ret_net"]).cumprod()

    return df


# ── Portfolio backtest ──────────────────────────────────────────────────────


def portfolio_backtest(data: pd.DataFrame, assets: list, fast: int, slow: int,
                       target_vol: float, rvol_window: int,
                       cost_bps: float) -> pd.DataFrame:
    """Multi-asset portfolio with inverse-vol weighting."""
    asset_returns = {}

    for asset in assets:
        col = f"{asset}_close"
        if col not in data.columns:
            continue
        close = data[col].dropna()
        if len(close) < slow + 60:
            continue

        bt = backtest_single_asset(close, fast, slow, target_vol, rvol_window, cost_bps)
        asset_returns[asset] = bt["strat_ret_net"]

    if not asset_returns:
        return pd.DataFrame()

    ret_df = pd.DataFrame(asset_returns)

    # Inverse-vol weighting across assets (60-day rolling)
    asset_rvol = ret_df.rolling(60).std()
    inv_rvol = 1.0 / asset_rvol.replace(0, np.nan)
    inv_rvol = inv_rvol.div(inv_rvol.sum(axis=1), axis=0)

    portfolio_ret = (ret_df * inv_rvol).sum(axis=1)

    return pd.DataFrame({
        "portfolio_ret": portfolio_ret,
        "cum_ret": (1 + portfolio_ret).cumprod(),
    })


# ── Metrics ─────────────────────────────────────────────────────────────────


def compute_metrics(ret: pd.Series, name: str = "") -> dict:
    ret = ret.dropna()
    if len(ret) < 60:
        return {}

    ann_ret = ret.mean() * 252
    ann_vol = ret.std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0

    cum = (1 + ret).cumprod()
    peak = cum.cummax()
    max_dd = ((cum - peak) / peak).min()

    win_rate = (ret > 0).mean()
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


# ── Deflated Sharpe ─────────────────────────────────────────────────────────


def deflated_sharpe_test(sharpe: float, n_obs: int, n_trials: int) -> dict:
    """Bailey & Lopez de Prado deflated Sharpe ratio test."""
    se = np.sqrt((1 + 0.5 * sharpe**2) / n_obs)
    z = sharpe / se
    p_single = 1 - stats.norm.cdf(z)

    expected_max_z = np.sqrt(2 * np.log(n_trials))
    expected_max_sharpe = expected_max_z * se

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


# ── Walk-forward ────────────────────────────────────────────────────────────


def walk_forward(data: pd.DataFrame, assets: list, fast: int, slow: int,
                 target_vol: float, rvol_window: int, cost_bps: float,
                 train_pct: float = 0.6) -> dict:
    """Walk-forward: train on first train_pct, test on rest."""
    n = len(data)
    split = int(n * train_pct)

    train_data = data.iloc[:split]
    test_data = data.iloc[split:]

    train_bt = portfolio_backtest(train_data, assets, fast, slow, target_vol, rvol_window, cost_bps)
    train_m = compute_metrics(train_bt["portfolio_ret"], "train") if not train_bt.empty else {}

    test_bt = portfolio_backtest(test_data, assets, fast, slow, target_vol, rvol_window, cost_bps)
    test_m = compute_metrics(test_bt["portfolio_ret"], "test") if not test_bt.empty else {}

    return {"train": train_m, "test": test_m, "train_bt": train_bt, "test_bt": test_bt}


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print("  EMA-Crossover Trend Signal — Multi-Asset D1 Portfolio")
    print("  (Baz et al. 2015, Man AHL style)")
    print("=" * 60)
    print()

    data = load_data()
    available = [a for a in ASSETS if f"{a}_close" in data.columns]
    print(f"Data: {len(data)} rows, {data.index.min().date()} to {data.index.max().date()}")
    print(f"Assets: {available}")
    print(f"EMA combos: {EMA_COMBOS}")
    print(f"Deflated Sharpe trials: {N_TRIALS} (4 TSM sign-of-return + 4 EMA)")
    print()

    rows = []

    for fast, slow in EMA_COMBOS:
        label = f"EMA({fast},{slow})"
        print(f"--- {label} ---")

        # Full-period backtest
        bt = portfolio_backtest(data, ASSETS, fast, slow, TARGET_VOL, RVOL_WINDOW, COST_BPS)
        if bt.empty:
            print("  No data — skipped")
            continue

        m = compute_metrics(bt["portfolio_ret"], label)
        dsr = deflated_sharpe_test(m["sharpe"], m["n_days"], N_TRIALS)

        # Walk-forward
        wf = walk_forward(data, ASSETS, fast, slow, TARGET_VOL, RVOL_WINDOW, COST_BPS)
        train_m = wf["train"]
        test_m = wf["test"]

        row = {
            "combo": label,
            "fast": fast,
            "slow": slow,
            "ann_ret": m["ann_ret"],
            "ann_vol": m["ann_vol"],
            "sharpe": m["sharpe"],
            "max_dd": m["max_dd"],
            "win_rate": m["win_rate"],
            "skew": m["skew"],
            "n_days": m["n_days"],
            "p_single": dsr["p_single"],
            "p_deflated": dsr["p_deflated"],
            "deflated_sig": dsr["significant_5pct"],
            "wf_train_sharpe": train_m.get("sharpe", 0.0),
            "wf_test_sharpe": test_m.get("sharpe", 0.0),
            "wf_train_ret": train_m.get("ann_ret", 0.0),
            "wf_test_ret": test_m.get("ann_ret", 0.0),
        }
        rows.append(row)

        print(f"  Ann ret:  {m['ann_ret']:+.2%}")
        print(f"  Ann vol:  {m['ann_vol']:.2%}")
        print(f"  Sharpe:   {m['sharpe']:.3f}")
        print(f"  Max DD:   {m['max_dd']:.2%}")
        print(f"  Win rate: {m['win_rate']:.1%}")
        print(f"  Skew:     {m['skew']:.3f}")
        print(f"  Deflated: p_single={dsr['p_single']:.4f}  p_deflated={dsr['p_deflated']:.4f}  sig@5%={dsr['significant_5pct']}")
        print(f"  WF Train Sharpe: {train_m.get('sharpe', 0):.3f}  Ann Ret: {train_m.get('ann_ret', 0):.2%}")
        print(f"  WF Test  Sharpe: {test_m.get('sharpe', 0):.3f}  Ann Ret: {test_m.get('ann_ret', 0):.2%}")
        print()

    # ── Summary table ───────────────────────────────────────────────────────
    if rows:
        summary = pd.DataFrame(rows)
        print("=" * 90)
        print("  SUMMARY — EMA-Crossover Trend Signal")
        print("=" * 90)
        hdr = (f"{'Combo':<14} {'Sharpe':>7} {'Ann Ret':>8} {'Ann Vol':>8} "
               f"{'Max DD':>8} {'Win%':>6} {'Skew':>7} "
               f"{'p_defl':>7} {'Sig5%':>5} {'WF Trn':>7} {'WF Tst':>7}")
        print(hdr)
        print("-" * len(hdr))
        for r in rows:
            sig = "YES" if r["deflated_sig"] else "NO"
            print(f"{r['combo']:<14} {r['sharpe']:>7.3f} {r['ann_ret']:>+7.1%} {r['ann_vol']:>7.1%} "
                  f"{r['max_dd']:>7.1%} {r['win_rate']:>5.1%} {r['skew']:>7.3f} "
                  f"{r['p_deflated']:>7.4f} {sig:>5} {r['wf_train_sharpe']:>7.3f} {r['wf_test_sharpe']:>7.3f}")
        print()

        # Save summary to CSV
        csv_path = OUT_DIR / "tsm_ema_summary.csv"
        summary.to_csv(csv_path, index=False)
        print(f"Saved summary: {csv_path}")


if __name__ == "__main__":
    main()
