"""
Pooled Multi-Asset Trend Strategy Test — Driscoll-Kraay Cluster-Robust Inference
================================================================================
Tests 3 trend-following strategies on 7 assets (no BTC):
  1. Donchian 10-day breakout
  2. Donchian 10-day + ADX filter
  3. Bollinger squeeze breakout

Method: same as pooled_donchian_test.py — BacktestEngine, DK t-stat, ≥1000 trades.
"""

from __future__ import annotations

import json
import math
import sys
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

# 7-asset universe (no BTC)
UNIVERSE = [
    "XAUUSD",
    "XAGUSD",
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "NAS100",
    "US30",
]

# Per-symbol spread_pips (realistic Pepperstone Razor values)
SYMBOL_SPREAD_PIPS: dict[str, float] = {
    "XAUUSD": 100.0,  # 1.0 point (pip_size=0.01)
    "XAGUSD": 150.0,  # 1.5 points
    "EURUSD": 1.2,  # 0.12 pips (pip_size=0.0001)
    "GBPUSD": 1.5,  # 0.15 pips
    "USDJPY": 1.2,  # 0.12 pips (pip_size=0.01 for JPY)
    "NAS100": 120.0,  # 1.2 points (pip_size=0.01)
    "US30": 120.0,  # 1.2 points (pip_size=0.01)
}

# Per-symbol commission_per_lot (Pepperstone Razor)
SYMBOL_COMMISSION: dict[str, float] = {
    "XAUUSD": 0.0,
    "XAGUSD": 0.0,
    "EURUSD": 7.0,
    "GBPUSD": 7.0,
    "USDJPY": 7.0,
    "NAS100": 5.0,
    "US30": 5.0,
}


def _trade_pnl(t) -> float:
    if isinstance(t, dict):
        return float(t.get("pnl", t.get("net_pnl", 0)))
    return float(getattr(t, "pnl", 0))


def _trade_exit_time(t):
    if isinstance(t, dict):
        ts = t.get("exit_time")
    else:
        ts = getattr(t, "exit_time", None)
    if ts is None:
        return None
    return pd.Timestamp(ts)


def reconstruct_equity_from_trades(trades: list, initial_capital: float = 10000.0) -> list[dict]:
    """Build equity points from trade exits.

    Engine Phase-4 path may leave equity_curve empty (uses RealTimePnLTracker
    without appending EquityPoint). Trade ledger is authoritative.
    """
    if not trades:
        return [{"timestamp": pd.Timestamp("2005-01-01"), "equity": initial_capital, "balance": initial_capital}]

    sorted_trades = sorted(
        [t for t in trades if _trade_exit_time(t) is not None],
        key=_trade_exit_time,
    )
    equity = float(initial_capital)
    points = [
        {"timestamp": _trade_exit_time(sorted_trades[0]) - pd.Timedelta(days=1), "equity": equity, "balance": equity}
    ]
    for t in sorted_trades:
        equity += _trade_pnl(t)
        points.append({"timestamp": _trade_exit_time(t), "equity": equity, "balance": equity})
    return points


def load_asset_data(symbol: str) -> pd.DataFrame:
    """Load and clean asset D1 data."""
    path = ROOT / "data" / f"{symbol}_D1.csv"
    df = pd.read_csv(path)
    ts_col = "time" if "time" in df.columns else "date"
    df[ts_col] = pd.to_datetime(df[ts_col])
    df = df[df[ts_col] >= "2005-01-01"].sort_values(ts_col).reset_index(drop=True)
    return df


def run_engine_for_asset(symbol: str, strategy) -> dict:
    """Run BacktestEngine with given strategy on one asset."""
    from graxia.packages.quant_os.backtest.engine import BacktestConfig, BacktestEngine

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
    )

    engine = BacktestEngine(config)
    engine._symbol = symbol  # Fix Bug #1: thread real symbol through engine
    engine.set_strategy(strategy)
    engine.load_data(ohlcv, timestamps, symbol=symbol)
    engine._check_risk_halt = lambda: False

    results = engine.run()

    # Prefer live equity_curve; Phase-4 tracker path leaves it empty, so fall
    # back to reconstructing equity from the (authoritative) trade ledger.
    full_equity = [{"timestamp": p.timestamp, "equity": p.equity, "balance": p.balance} for p in engine.equity_curve]
    if len(full_equity) < 2:
        full_equity = reconstruct_equity_from_trades(results.get("trades", []), initial_capital=10000.0)
    results["_full_equity_curve"] = full_equity
    results["_symbol"] = symbol
    results["_timestamps"] = timestamps
    return results


def extract_daily_returns(results: dict) -> pd.DataFrame:
    """Extract daily returns from equity curve."""
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

    # Max drawdown
    equity_vals = [e["equity"] for e in equity_curve]
    peak = equity_vals[0]
    max_dd = 0.0
    for eq in equity_vals:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    # Trade stats (trades may be dicts or objects)
    def _pnl(t):
        return float(t["pnl"]) if isinstance(t, dict) else float(t.pnl)

    wins = [t for t in trades if _pnl(t) > 0]
    losses = [t for t in trades if _pnl(t) <= 0]
    total_profit = sum(_pnl(t) for t in wins)
    total_loss = abs(sum(_pnl(t) for t in losses))
    pf = total_profit / total_loss if total_loss > 0 else 999.0
    win_pct = len(wins) / len(trades) * 100 if trades else 0.0

    return {
        "n_trades": len(trades),
        "sharpe": sharpe,
        "win_pct": win_pct,
        "profit_factor": pf,
        "max_dd_pct": max_dd * 100,
        "total_return_pct": (equity_vals[-1] / equity_vals[0] - 1) * 100 if equity_vals else 0.0,
    }


def run_dk_test(all_returns: pd.DataFrame, total_trades: int) -> dict:
    """Driscoll-Kraay cluster-robust pooled inference."""
    if all_returns.empty or len(all_returns.columns) < 2:
        return {"dk_t_stat": 0, "pooled_sharpe": 0, "verdict": "INSUFFICIENT_DATA"}

    # Cross-sectional mean return per day
    cs_mean = all_returns.mean(axis=1).dropna()
    if len(cs_mean) < 30:
        return {"dk_t_stat": 0, "pooled_sharpe": 0, "verdict": "INSUFFICIENT_DATA"}

    mu = float(cs_mean.mean())
    T = len(cs_mean)

    # Newey-West HAC with max lags = floor(T^(1/3))
    max_lag = max(1, int(T ** (1 / 3)))
    gamma_0 = float(cs_mean.var(ddof=1))
    nw_var = gamma_0

    for lag in range(1, max_lag + 1):
        cov = float(cs_mean.iloc[lag:].cov(cs_mean.iloc[:-lag]))
        weight = 1.0 - lag / (max_lag + 1)  # Bartlett kernel
        nw_var += 2 * weight * cov

    nw_se = math.sqrt(nw_var / T) if nw_var > 0 else 1e-10
    dk_t = mu / nw_se if nw_se > 0 else 0.0
    pooled_sharpe = mu / (math.sqrt(gamma_0) + 1e-10) * math.sqrt(252)

    # Count assets with positive Sharpe
    pos_sharpe = 0
    for col in all_returns.columns:
        r = all_returns[col].dropna()
        if len(r) > 30:
            s = float(r.mean()) / (float(r.std(ddof=1)) + 1e-10) * math.sqrt(252)
            if s > 0:
                pos_sharpe += 1

    # Verdict
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


def run_variant(name: str, strategy_factory, universe: list[str]) -> dict:
    """Run one strategy variant across all assets."""
    print(f"\n{'='*60}")
    print(f"  Strategy: {name}")
    print(f"{'='*60}")

    all_returns = pd.DataFrame()
    total_trades = 0
    per_asset = {}

    for sym in universe:
        strategy = strategy_factory()
        print(f"  Running {sym}...", end=" ", flush=True)
        try:
            results = run_engine_for_asset(sym, strategy)
            metrics = compute_per_asset_metrics(results)
            per_asset[sym] = metrics
            total_trades += metrics.get("n_trades", 0)

            daily_ret = extract_daily_returns(results)
            if not daily_ret.empty:
                all_returns = pd.concat([all_returns, daily_ret], axis=1)

            print(
                f"trades={metrics.get('n_trades', 0)}, "
                f"sharpe={metrics.get('sharpe', 0):.3f}, "
                f"maxdd={metrics.get('max_dd_pct', 0):.1f}%"
            )
        except Exception as e:
            print(f"ERROR: {e}")
            per_asset[sym] = {"error": str(e)}

    # DK test
    dk_result = run_dk_test(all_returns, total_trades)
    dk_result["per_asset"] = per_asset

    # Print summary
    print(f"\n  {'Symbol':<10} {'Trades':>7} {'Sharpe':>8} {'Win%':>6} {'PF':>6} {'MaxDD':>8}")
    print(f"  {'-'*50}")
    for sym, m in per_asset.items():
        if "error" in m:
            print(f"  {sym:<10} {'ERROR':>7}")
        else:
            print(
                f"  {sym:<10} {m.get('n_trades',0):>7} {m.get('sharpe',0):>8.3f} "
                f"{m.get('win_pct',0):>5.1f}% {m.get('profit_factor',0):>6.2f} "
                f"{m.get('max_dd_pct',0):>7.1f}%"
            )

    print(f"\n  Total trades: {total_trades}")
    print(f"  Pooled DK t-stat: {dk_result.get('dk_t_stat', 0)}")
    print(f"  Positive Sharpe: {dk_result.get('positive_sharpe_count', 0)}/{dk_result.get('total_assets', 7)}")
    print(f"  VERDICT: {dk_result.get('verdict', 'ERROR')}")

    return dk_result


def main():
    from graxia.packages.quant_os.strategies.bollinger_squeeze import BollingerSqueeze
    from graxia.packages.quant_os.strategies.donchian import DonchianBreakout
    from graxia.packages.quant_os.strategies.donchian_adx import DonchianADX

    # Strategy variants
    variants = [
        (
            "Donchian-10 (no vol filter)",
            lambda: DonchianBreakout(
                period=10,
                atr_period=14,
                atr_sl_mult=2.0,
                atr_tp_mult=3.0,
                vol_filter=False,
            ),
        ),
        (
            "Donchian-10 + ADX(25)",
            lambda: DonchianADX(
                period=10,
                atr_period=14,
                atr_sl_mult=2.0,
                atr_tp_mult=3.0,
                adx_period=14,
                adx_threshold=25.0,
            ),
        ),
        (
            "Donchian-10 + ADX(20)",
            lambda: DonchianADX(
                period=10,
                atr_period=14,
                atr_sl_mult=2.0,
                atr_tp_mult=3.0,
                adx_period=14,
                adx_threshold=20.0,
            ),
        ),
        (
            "BollingerSqueeze(20, p20)",
            lambda: BollingerSqueeze(
                bb_period=20,
                bb_std=2.0,
                squeeze_lookback=120,
                squeeze_pctile=0.2,
                atr_period=14,
                atr_sl_mult=2.0,
                atr_tp_mult=3.0,
            ),
        ),
        (
            "BollingerSqueeze(20, p30)",
            lambda: BollingerSqueeze(
                bb_period=20,
                bb_std=2.0,
                squeeze_lookback=120,
                squeeze_pctile=0.3,
                atr_period=14,
                atr_sl_mult=2.0,
                atr_tp_mult=3.0,
            ),
        ),
    ]

    all_results = {}
    for name, factory in variants:
        result = run_variant(name, factory, UNIVERSE)
        all_results[name] = result

    # Summary
    print(f"\n{'='*60}")
    print("  SUMMARY — All trend strategies on 7-asset universe")
    print(f"{'='*60}")
    print(f"  {'Strategy':<35} {'Trades':>7} {'DK-t':>7} {'Pos':>4} {'Verdict':<10}")
    print(f"  {'-'*65}")
    for name, r in all_results.items():
        print(
            f"  {name:<35} {r.get('total_trades',0):>7} {r.get('dk_t_stat',0):>7.3f} "
            f"{r.get('positive_sharpe_count',0):>3}/{r.get('total_assets',7)} {r.get('verdict','?'):<10}"
        )

    # Save
    out_path = ROOT / "reports" / "pooled_trend_strategies_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Report saved: {out_path}")


if __name__ == "__main__":
    main()
