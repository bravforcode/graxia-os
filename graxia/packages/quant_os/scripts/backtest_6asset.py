"""
6-Asset Ensemble TSM Backtest - BTCUSD + SPX500 Validation.

Validates the 6-asset portfolio: NAS100, XAUUSD, OIL, USDJPY, BTCUSD, SPX500.
Tests whether adding BTCUSD and SPX500 improves Sharpe vs the 4-asset baseline.

Outputs:
  - Sharpe, Sortino, Max DD, correlation matrix
  - Comparison vs 4-asset baseline
  - Report saved to reports/backtest_6asset_validation.json
"""

import importlib.util
import json
import sys
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

REPORTS = BASE / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

# ── SIGNAL SPEC ─────────────────────────────────────────────────────
LOOKBACKS = [20, 40, 60, 120]
WEIGHTS = [0.25, 0.25, 0.25, 0.25]
TARGET_VOL = 0.10
REBALANCE_FREQ = "W-FRI"
POSITION_CAP = 1.5

# 4-asset baseline
ASSETS_4 = {
    "NAS100": {"csv": "data/NAS100_D1.csv", "cost_key": "NAS100"},
    "XAUUSD": {"csv": "data/XAUUSD_D1.csv", "cost_key": "XAUUSD"},
    "OIL": {"csv": "data/market_data/yfinance/CL_F.csv", "cost_key": "OIL"},
    "USDJPY": {"csv": "data/USDJPY_D1.csv", "cost_key": "USDJPY"},
}

# 6-asset extended
ASSETS_6 = {
    **ASSETS_4,
    "BTCUSD": {"csv": "data/BTCUSD_D1.csv", "cost_key": "BTCUSD"},
    "SPX500": {"csv": "data/market_data/yfinance/_GSPC.csv", "cost_key": "SPX500"},
}


def load_costs() -> dict:
    path = BASE / "config" / "cost_calibration.json"
    with open(path) as f:
        return json.load(f)


def build_cost_map(assets_cfg: dict, cost_data: dict) -> tuple[dict, dict, dict]:
    typical, swap_long, swap_short = {}, {}, {}
    assets = cost_data["assets"]
    for tsm_name, cfg in assets_cfg.items():
        cost_key = cfg["cost_key"]
        if cost_key in assets:
            a = assets[cost_key]
            typical[tsm_name] = a["round_trip_bps_measured"]
            swap_long[tsm_name] = a.get("swap_long_bps", 0.0)
            swap_short[tsm_name] = a.get("swap_short_bps", 0.0)
        else:
            print(f"  WARNING: No cost for {cost_key}, using 10bps")
            typical[tsm_name] = 10.0
            swap_long[tsm_name] = 0.0
            swap_short[tsm_name] = 0.0
    return typical, swap_long, swap_short


def load_data(assets_cfg: dict) -> pd.DataFrame:
    closes = {}
    for tsm_name, cfg in assets_cfg.items():
        csv_path = BASE / cfg["csv"]
        if not csv_path.exists():
            print(f"  WARNING: {csv_path} not found, skipping {tsm_name}")
            continue
        df = pd.read_csv(csv_path)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df = df.set_index("timestamp").sort_index()
            close = df["close"]
        elif "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"], utc=True)
            df = df.set_index("time").sort_index()
            close = df["close"]
        elif "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], utc=True)
            df = df.set_index("Date").sort_index()
            close = df["Close"]
        elif "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], utc=True)
            df = df.set_index("date").sort_index()
            close = df["close"]
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


def compute_position(returns: pd.Series) -> pd.Series:
    sig = ensemble_signal(returns)
    realized_vol = returns.rolling(60).std() * (252**0.5)
    pos = sig * (TARGET_VOL / realized_vol.replace(0, np.nan))
    return pos.clip(-POSITION_CAP, POSITION_CAP)


def backtest_single(close: pd.Series, cost_bps: float, swap_l: float, swap_s: float) -> pd.DataFrame:
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
    df.loc[long_mask, "swap_cost"] = prev_pos[long_mask].abs() * swap_l / 10000
    df.loc[short_mask, "swap_cost"] = prev_pos[short_mask].abs() * swap_s / 10000
    df["swap_cost"] = df["swap_cost"].abs()
    df["cost"] = df["tx_cost"] + df["swap_cost"]
    df["strat_ret_net"] = df["strat_ret"] - df["cost"]
    return df


def portfolio_backtest(data: pd.DataFrame, cost_map: dict, swap_l_map: dict, swap_s_map: dict) -> tuple:
    asset_returns, asset_costs, asset_pos = {}, {}, {}
    for asset in data.columns:
        close = data[asset].dropna()
        if len(close) < 180:
            print(f"  SKIP {asset}: only {len(close)} bars")
            continue
        bt = backtest_single(close, cost_map.get(asset, 5.0), swap_l_map.get(asset, 0.0), swap_s_map.get(asset, 0.0))
        asset_returns[asset] = bt["strat_ret_net"]
        asset_costs[asset] = bt["cost"]
        asset_pos[asset] = bt["pos_change"]

    if not asset_returns:
        return pd.DataFrame(), {}

    ret_df = pd.DataFrame(asset_returns)
    portfolio_ret = ret_df.mean(axis=1, skipna=True)
    valid_mask = portfolio_ret.notna()
    portfolio_ret = portfolio_ret[valid_mask]

    result = pd.DataFrame(
        {
            "portfolio_ret": portfolio_ret,
            "cum_ret": (1 + portfolio_ret).cumprod(),
        }
    )
    details = {"asset_returns": ret_df, "n_assets": len(asset_returns)}
    return result, details


def compute_metrics(ret: pd.Series, name: str = "") -> dict:
    ret = ret.dropna()
    if len(ret) < 60:
        return {"name": name, "sharpe": 0, "sortino": 0, "max_dd": 0, "n_days": 0}
    n_days = len(ret)
    n_years = n_days / 252
    ann_ret = ret.mean() * 252
    ann_vol = ret.std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
    downside = ret[ret < 0]
    down_vol = downside.std() * np.sqrt(252) if len(downside) > 0 else 1e-10
    sortino = ann_ret / down_vol if down_vol > 0 else 0
    cum = (1 + ret).cumprod()
    running_max = cum.cummax()
    dd = (cum - running_max) / running_max
    max_dd = dd.min()

    # Deflated Sharpe
    dsr = deflated_sharpe_ratio(
        observed_sharpe=sharpe,
        n_trials=len(LOOKBACKS),
        n_observations=n_days,
        skewness=float(ret.skew()),
        kurtosis=float(ret.kurtosis()),
    )

    return {
        "name": name,
        "ann_ret": round(float(ann_ret), 4),
        "ann_vol": round(float(ann_vol), 4),
        "sharpe": round(float(sharpe), 4),
        "sortino": round(float(sortino), 4),
        "max_dd": round(float(max_dd), 4),
        "n_days": n_days,
        "n_years": round(n_years, 2),
        "total_return": round(float(cum.iloc[-1] - 1), 4),
        "deflated_sharpe": round(float(dsr.deflated_sharpe), 4),
    }


def correlation_matrix(ret_df: pd.DataFrame) -> pd.DataFrame:
    return ret_df.corr().round(4)


def main():
    print("=" * 60)
    print("6-ASSET ENSEMBLE TSM BACKTEST - BTCUSD + SPX500 VALIDATION")
    print("=" * 60)

    cost_data = load_costs()

    # -- 4-asset baseline --
    print("\n-- 4-Asset Baseline --")
    data_4 = load_data(ASSETS_4)
    print(f"  Data: {data_4.index[0].date()} to {data_4.index[-1].date()} ({len(data_4)} bars)")
    print(f"  Assets: {list(data_4.columns)}")
    cost_4, swap_l_4, swap_s_4 = build_cost_map(ASSETS_4, cost_data)
    bt_4, det_4 = portfolio_backtest(data_4, cost_4, swap_l_4, swap_s_4)
    m4 = compute_metrics(bt_4["portfolio_ret"], "4-Asset Baseline")

    # -- 6-asset extended --
    print("\n-- 6-Asset Extended (BTCUSD + SPX500) --")
    data_6 = load_data(ASSETS_6)
    print(f"  Data: {data_6.index[0].date()} to {data_6.index[-1].date()} ({len(data_6)} bars)")
    print(f"  Assets: {list(data_6.columns)}")
    cost_6, swap_l_6, swap_s_6 = build_cost_map(ASSETS_6, cost_data)
    bt_6, det_6 = portfolio_backtest(data_6, cost_6, swap_l_6, swap_s_6)
    m6 = compute_metrics(bt_6["portfolio_ret"], "6-Asset Extended")

    # -- Correlation matrix --
    print("\n-- Correlation Matrix (6-Asset) --")
    corr = correlation_matrix(det_6["asset_returns"])
    print(corr.to_string())

    # -- Comparison --
    print("\n" + "=" * 60)
    print("COMPARISON")
    print("=" * 60)
    for key in ["sharpe", "sortino", "max_dd", "ann_ret", "ann_vol", "total_return", "deflated_sharpe"]:
        v4 = m4[key]
        v6 = m6[key]
        delta = v6 - v4
        sign = "+" if delta > 0 else ""
        print(f"  {key:20s}:  4-asset={v4:+.4f}  6-asset={v6:+.4f}  delta={sign}{delta:+.4f}")

    # -- Verdict --
    print("\n-- Verdict --")
    if m6["sharpe"] > m4["sharpe"]:
        print(f"  6-asset IMPROVES Sharpe: {m4['sharpe']:.4f} -> {m6['sharpe']:.4f}")
    elif m6["sharpe"] < m4["sharpe"]:
        print(f"  6-asset REDUCES Sharpe: {m4['sharpe']:.4f} -> {m6['sharpe']:.4f}")
    else:
        print("  Sharpe unchanged")

    if m6["sharpe"] >= 0.5:
        print("  DECISION: REAL ALPHA — proceed to paper trading")
    elif m6["sharpe"] >= 0.3:
        print("  DECISION: MARGINAL - needs investigation")
    else:
        print("  DECISION: NO ALPHA — consider reverting to 4-asset")

    # ── Save report ──
    report = {
        "baseline_4asset": m4,
        "extended_6asset": m6,
        "correlation_matrix": corr.to_dict(),
        "assets_6": list(ASSETS_6.keys()),
        "signal_spec": {
            "lookbacks": LOOKBACKS,
            "weights": WEIGHTS,
            "target_vol": TARGET_VOL,
            "rebalance": REBALANCE_FREQ,
            "position_cap": POSITION_CAP,
        },
    }
    report_path = REPORTS / "backtest_6asset_validation.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report saved: {report_path}")


if __name__ == "__main__":
    main()
