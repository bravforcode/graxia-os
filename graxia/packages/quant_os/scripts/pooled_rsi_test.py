"""
Pooled Multi-Asset RSI Mean-Reversion Test — Driscoll-Kraay Cluster-Robust Inference
======================================================================================
Same universe/method as pooled_donchian_test.py, using RSIMeanReversion.
Tests multiple RSI threshold pairs: (25/75), (30/70), (20/80).

Method:
  1. Run BacktestEngine with RSIMeanReversion on each of 8 assets
  2. Extract bar-level returns from equity curve
  3. Align returns by date into panel (date x asset)
  4. Compute daily cross-sectional means
  5. Apply Newey-West to time series of cross-sectional means (Driscoll-Kraay)
  6. Report per-asset + pooled results, per threshold variant
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

ROOT = Path(__file__).resolve().parent.parent
GRAXIA_ROOT = ROOT.parent.parent.parent
if str(GRAXIA_ROOT) not in sys.path:
    sys.path.insert(0, str(GRAXIA_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Pre-registered universe (same as pooled_donchian_test.py, for comparability)
UNIVERSE = [
    "XAUUSD",
    "XAGUSD",
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "NAS100",
    "US30",
    "BTCUSD",
]

# RSI threshold variants to test
THRESHOLD_VARIANTS = [
    (25, 75),
    (30, 70),
    (20, 80),
]

FIXED_PARAMS = {
    "rsi_period": 14,
    "ema_period": 0,  # 0 = disabled (pure RSI)
    "atr_period": 14,
    "atr_sl_mult": 2.0,
    "atr_tp_mult": 3.0,
}

# Per-symbol spread_pips (realistic Pepperstone Razor values)
# Indices need much higher spread than FX — pip_size=0.01 means 1.0 pts = 100 pips
SYMBOL_SPREAD_PIPS: dict[str, float] = {
    "XAUUSD": 100.0,  # 1.0 point (pip_size=0.01)
    "XAGUSD": 150.0,  # 1.5 points
    "EURUSD": 1.2,  # 0.12 pips (pip_size=0.0001)
    "GBPUSD": 1.5,  # 0.15 pips
    "USDJPY": 1.2,  # 0.12 pips (pip_size=0.01 for JPY)
    "NAS100": 120.0,  # 1.2 points (pip_size=0.01)
    "US30": 120.0,  # 1.2 points (pip_size=0.01)
    "BTCUSD": 5000.0,  # 50 points (pip_size=0.01)
}

# Per-symbol commission_per_lot ( Pepperstone Razor)
SYMBOL_COMMISSION: dict[str, float] = {
    "XAUUSD": 0.0,  # Commission embedded in spread
    "XAGUSD": 0.0,
    "EURUSD": 7.0,  # $7 round-trip
    "GBPUSD": 7.0,
    "USDJPY": 7.0,
    "NAS100": 5.0,  # $5 round-trip for indices
    "US30": 5.0,
    "BTCUSD": 0.0,  # Commission embedded in spread
}


def load_asset_data(symbol: str) -> pd.DataFrame:
    """Load and clean asset D1 data."""
    path = ROOT / "data" / f"{symbol}_D1.csv"
    df = pd.read_csv(path)
    ts_col = "time" if "time" in df.columns else "date"
    df[ts_col] = pd.to_datetime(df[ts_col])
    df = df[df[ts_col] >= "2005-01-01"].sort_values(ts_col).reset_index(drop=True)
    return df


def run_engine_for_asset(symbol: str, oversold: float, overbought: float) -> dict:
    """Run BacktestEngine with RSIMeanReversion on one asset."""
    from graxia.packages.quant_os.backtest.engine import BacktestConfig, BacktestEngine
    from graxia.packages.quant_os.strategies.rsi_mean_reversion import RSIMeanReversion

    df = load_asset_data(symbol)

    ohlcv = {
        "open": df["open"].tolist(),
        "high": df["high"].tolist(),
        "low": df["low"].tolist(),
        "close": df["close"].tolist(),
        "volume": df["volume"].tolist(),
    }
    timestamps = df["time"].tolist()

    config = BacktestConfig(
        initial_capital=10000,
        slippage_pips=0.5,
        spread_pips=SYMBOL_SPREAD_PIPS.get(symbol, 2.0),
        commission_per_lot=Decimal(str(SYMBOL_COMMISSION.get(symbol, 3.5))),
        risk_per_trade_bps=100,
        max_positions=1,
        strict_mtf=False,
        symbol=symbol,
    )

    strategy = RSIMeanReversion(
        rsi_period=FIXED_PARAMS["rsi_period"],
        oversold=oversold,
        overbought=overbought,
        ema_period=FIXED_PARAMS["ema_period"],
        atr_period=FIXED_PARAMS["atr_period"],
        atr_sl_mult=FIXED_PARAMS["atr_sl_mult"],
        atr_tp_mult=FIXED_PARAMS["atr_tp_mult"],
    )

    engine = BacktestEngine(config)
    engine._symbol = symbol  # Fix Bug #1: thread real symbol through engine
    engine.set_strategy(strategy)
    engine.load_data(ohlcv, timestamps)
    engine._check_risk_halt = lambda: False

    results = engine.run()

    full_equity = [{"timestamp": p.timestamp, "equity": p.equity, "balance": p.balance} for p in engine.equity_curve]
    results["_full_equity_curve"] = full_equity
    results["_symbol"] = symbol
    results["_timestamps"] = timestamps
    return results


def extract_daily_returns(results: dict) -> pd.DataFrame:
    """Extract daily returns from equity curve as a DataFrame with date index."""
    equity_curve = results.get("_full_equity_curve", [])
    symbol = results.get("_symbol", "UNKNOWN")

    if len(equity_curve) < 2:
        return pd.DataFrame()

    rows = []
    for i in range(1, len(equity_curve)):
        prev_eq = equity_curve[i - 1]["equity"]
        curr_eq = equity_curve[i]["equity"]
        ts = equity_curve[i]["timestamp"]
        if isinstance(ts, str):
            ts = pd.Timestamp(ts)
        ret = (curr_eq - prev_eq) / prev_eq if prev_eq > 0 else 0.0
        rows.append({"date": ts.date() if hasattr(ts, "date") else ts, "return": ret})

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["date"] = pd.to_datetime(df["date"])
    daily = df.groupby("date")["return"].sum().reset_index()
    daily = daily.set_index("date")
    daily.columns = [symbol]
    return daily


def compute_per_asset_metrics(results: dict) -> dict:
    """Compute per-asset Sharpe, trades, win rate, PF, max DD."""
    equity_curve = results.get("_full_equity_curve", [])
    trades = results.get("trades", [])
    metrics = results.get("metrics")

    if not equity_curve:
        return {}

    bar_returns = []
    for i in range(1, len(equity_curve)):
        prev_eq = equity_curve[i - 1]["equity"]
        curr_eq = equity_curve[i]["equity"]
        if prev_eq > 0:
            bar_returns.append((curr_eq - prev_eq) / prev_eq)

    arr = np.array(bar_returns)
    n_bars = len(arr)
    mu = float(arr.mean())
    std = float(arr.std(ddof=1))
    sharpe = mu / (std + 1e-10) * math.sqrt(252)

    trade_returns = [t["return_pct"] / 100.0 for t in trades] if trades else []
    wins = [r for r in trade_returns if r > 0]
    losses = [r for r in trade_returns if r < 0]
    win_rate = len(wins) / len(trade_returns) if trade_returns else 0
    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 0
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    max_dd = float(metrics.max_drawdown_pct) if metrics else 0.0

    nw_t = compute_nw_t_stat(arr)

    return {
        "symbol": results.get("_symbol", "UNKNOWN"),
        "n_bars": n_bars,
        "n_trades": len(trades),
        "sharpe": sharpe,
        "win_rate": win_rate,
        "profit_factor": pf,
        "max_dd_pct": max_dd,
        "nw_t_stat": nw_t,
        "mean_return": mu,
        "std_return": std,
    }


def compute_nw_t_stat(arr: np.ndarray, bandwidth: int | None = None) -> float:
    """Compute Newey-West t-stat for mean return."""
    n = len(arr)
    if n < 20:
        return 0.0

    mu = arr.mean()
    if bandwidth is None:
        bandwidth = int(4 * (n / 100) ** (2 / 9))
        bandwidth = max(bandwidth, 1)

    gamma_0 = float(np.mean((arr - mu) ** 2))
    nw_var = gamma_0

    for k in range(1, bandwidth + 1):
        weight = 1 - k / (bandwidth + 1)
        gamma_k = float(np.mean((arr[k:] - mu) * (arr[:-k] - mu)))
        nw_var += 2 * weight * gamma_k

    nw_se = math.sqrt(nw_var / n)
    return mu / (nw_se + 1e-10)


def driscoll_kraay_t_stat(daily_means: np.ndarray) -> tuple[float, float, float]:
    """Driscoll-Kraay: NW on time series of cross-sectional means."""
    n = len(daily_means)
    if n < 20:
        return 0.0, 0.0, 0.0

    mu = daily_means.mean()
    bandwidth = int(4 * (n / 100) ** (2 / 9))
    bandwidth = max(bandwidth, 1)

    gamma_0 = float(np.mean((daily_means - mu) ** 2))
    nw_var = gamma_0

    for k in range(1, bandwidth + 1):
        weight = 1 - k / (bandwidth + 1)
        gamma_k = float(np.mean((daily_means[k:] - mu) * (daily_means[:-k] - mu)))
        nw_var += 2 * weight * gamma_k

    nw_se = math.sqrt(nw_var / n)
    t_stat = mu / (nw_se + 1e-10)
    return t_stat, mu, nw_se


def run_one_variant(oversold: float, overbought: float) -> dict:
    print("=" * 70)
    print(f"  POOLED MULTI-ASSET RSI MEAN-REVERSION ({int(oversold)}/{int(overbought)}) TEST")
    print("  Driscoll-Kraay Cluster-Robust Inference")
    print(
        f"  Params: rsi_period={FIXED_PARAMS['rsi_period']}, oversold={oversold}, "
        f"overbought={overbought}, atr_sl={FIXED_PARAMS['atr_sl_mult']}, "
        f"atr_tp={FIXED_PARAMS['atr_tp_mult']}"
    )
    print("=" * 70)

    all_results = {}
    per_asset_returns = {}

    for symbol in UNIVERSE:
        print(f"\n  Running {symbol}...", end=" ", flush=True)
        try:
            results = run_engine_for_asset(symbol, oversold, overbought)
            all_results[symbol] = results
            daily_ret = extract_daily_returns(results)
            if not daily_ret.empty:
                per_asset_returns[symbol] = daily_ret
                trades = results.get("trades", [])
                print(f"{len(trades)} trades, {len(daily_ret)} daily returns")
            else:
                print("NO RETURNS")
        except Exception as e:
            print(f"ERROR: {e}")

    if len(per_asset_returns) < 3:
        print("  ERROR: Not enough assets with returns. Need >= 3.")
        return {
            "thresholds": f"{int(oversold)}/{int(overbought)}",
            "verdict": "INSUFFICIENT_SAMPLE",
        }

    panel = pd.concat(per_asset_returns.values(), axis=1, join="outer")
    panel = panel.fillna(0.0)

    print(f"\n  Panel shape: {panel.shape} (dates x assets)")
    print(f"  Assets: {list(panel.columns)}")

    daily_means = panel.mean(axis=1).values
    n_dates = len(daily_means)

    dk_t, dk_mean, dk_se = driscoll_kraay_t_stat(daily_means)
    dk_sharpe = dk_mean / (daily_means.std(ddof=1) + 1e-10) * math.sqrt(252)

    print(f"\n  Pooled DK t-stat: {dk_t:.4f}")
    print(f"  Pooled Sharpe (annualized): {dk_sharpe:.4f}")

    per_asset_metrics = {}
    for symbol in UNIVERSE:
        if symbol in all_results:
            per_asset_metrics[symbol] = compute_per_asset_metrics(all_results[symbol])

    header = f"  {'Symbol':<10} {'Trades':>7} {'Sharpe':>8} {'Win%':>6} {'PF':>6} {'NW t':>7} {'MaxDD':>7}"
    print(f"\n{header}")
    print(f"  {'-'*len(header.strip())}")

    total_trades = 0
    positive_sharpe_count = 0
    for symbol in UNIVERSE:
        if symbol not in per_asset_metrics:
            continue
        m = per_asset_metrics[symbol]
        total_trades += m.get("n_trades", 0)
        if m.get("sharpe", 0) > 0:
            positive_sharpe_count += 1
        print(
            f"  {symbol:<10} {m.get('n_trades', 0):>7} {m.get('sharpe', 0):>8.4f} "
            f"{m.get('win_rate', 0)*100:>5.1f}% {m.get('profit_factor', 0):>5.2f} "
            f"{m.get('nw_t_stat', 0):>7.3f} {m.get('max_dd_pct', 0):>6.2f}%"
        )

    corr = panel.corr()
    print(f"\n  Correlation matrix:\n{corr.round(3).to_string()}")

    print(f"\n  Total pooled trades: {total_trades}")
    print(f"  Pooled DK t-stat: {dk_t:.4f}")
    print(f"  Assets with Sharpe > 0: {positive_sharpe_count}/{len(per_asset_metrics)}")

    if dk_t > 2.0 and positive_sharpe_count >= 5:
        verdict = "GO"
        reason = "Pooled t > 2.0 AND Sharpe > 0 in >= 5/8 assets"
    elif dk_t > 1.5 or positive_sharpe_count >= 3:
        verdict = "MARGINAL"
        reason = "Pooled t 1.5-2.0 OR Sharpe > 0 in 3-4/8 assets"
    else:
        verdict = "REJECT"
        reason = "Pooled t < 1.5 AND Sharpe > 0 in < 3/8 assets"

    print(f"\n  VERDICT: {verdict}  ({reason})")

    cost_sensitivity = {}
    for haircut in [0.0, 0.3, 0.5]:
        adjusted_means = daily_means * (1 - haircut)
        dk_t_adj, _, _ = driscoll_kraay_t_stat(adjusted_means)
        cost_sensitivity[f"{int(haircut*100)}pct"] = dk_t_adj

    # BTC-exclusion sensitivity: recompute DK t-stat without BTCUSD
    btc_exclusion = {}
    if "BTCUSD" in panel.columns and len(panel.columns) > 3:
        panel_no_btc = panel.drop(columns=["BTCUSD"])
        means_no_btc = panel_no_btc.mean(axis=1).values
        dk_t_no_btc, dk_mean_no_btc, dk_se_no_btc = driscoll_kraay_t_stat(means_no_btc)
        dk_sharpe_no_btc = dk_mean_no_btc / (means_no_btc.std(ddof=1) + 1e-10) * math.sqrt(252)
        positive_no_btc = sum(
            1 for s in per_asset_metrics if s != "BTCUSD" and per_asset_metrics[s].get("sharpe", 0) > 0
        )
        btc_exclusion = {
            "dk_t_stat": dk_t_no_btc,
            "dk_sharpe": dk_sharpe_no_btc,
            "positive_sharpe_count": positive_no_btc,
            "n_assets": len(panel_no_btc.columns),
        }
        print(f"\n  BTC-excluded DK t-stat: {dk_t_no_btc:.4f}")
        print(f"  BTC-excluded Sharpe: {dk_sharpe_no_btc:.4f}")
        print(f"  BTC-excluded positive: {positive_no_btc}/{len(panel_no_btc.columns)}")

    return {
        "thresholds": f"{int(oversold)}/{int(overbought)}",
        "params": {**FIXED_PARAMS, "oversold": oversold, "overbought": overbought},
        "universe": UNIVERSE,
        "panel_shape": list(panel.shape),
        "date_range": [str(panel.index.min()), str(panel.index.max())],
        "total_trades": total_trades,
        "pooled": {
            "dk_t_stat": dk_t,
            "dk_mean_return": dk_mean,
            "dk_se": dk_se,
            "dk_sharpe": dk_sharpe,
            "n_dates": n_dates,
        },
        "per_asset": per_asset_metrics,
        "verdict": verdict,
        "reason": reason,
        "positive_sharpe_count": positive_sharpe_count,
        "cost_sensitivity": cost_sensitivity,
        "btc_exclusion": btc_exclusion,
    }


def main():
    reports = {}
    for oversold, overbought in THRESHOLD_VARIANTS:
        key = f"rsi_{int(oversold)}_{int(overbought)}"
        reports[key] = run_one_variant(oversold, overbought)
        print("\n")

    report = {
        "timestamp": datetime.now().isoformat(),
        "strategy": "RSIMeanReversion",
        "variants": reports,
    }

    report_path = ROOT / "reports" / "pooled_rsi_results.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"  Report saved: {report_path}")

    print("\n" + "=" * 70)
    print("  SUMMARY — RSI Mean-Reversion across threshold variants")
    print("=" * 70)
    for key, r in reports.items():
        print(
            f"  {key}: {r.get('verdict')} "
            f"(trades={r.get('total_trades', 0)}, "
            f"dk_t={r.get('pooled', {}).get('dk_t_stat', 0):.3f}, "
            f"positive_sharpe={r.get('positive_sharpe_count', 0)}/8)"
        )


if __name__ == "__main__":
    main()
