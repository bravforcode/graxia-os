"""
Generic Pooled Multi-Asset Strategy Test — Driscoll-Kraay Cluster-Robust Inference
====================================================================================
Strategy-agnostic version of pooled_donchian_rsi_test.py. Takes any strategy
factory (zero-arg callable returning a `Strategy` instance, see strategies/base.py)
instead of hardcoding DonchianRSI, so the same DK-test harness can be pointed at
any of the strategies/ files.

Method (unchanged from pooled_donchian_rsi_test.py):
  1. Run BacktestEngine with the given strategy on each asset in UNIVERSE
  2. Extract bar-level returns from equity curve
  3. Align returns by date into panel (date x asset)
  4. Compute daily cross-sectional means
  5. Apply Newey-West to time series of cross-sectional means (Driscoll-Kraay)
  6. Report per-asset + pooled results, per variant

CLI usage (any strategy by dotted path):
  python pooled_strategy_test.py \\
      --strategy graxia.packages.quant_os.strategies.donchian_rsi.DonchianRSI \\
      --params '{"atr_period": 14, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0}' \\
      --variants '{"period_20": {"period": 20}, "period_55": {"period": 55}}'

Programmatic usage (preferred for per-strategy wrapper scripts):
  from pooled_strategy_test import run_strategy
  run_strategy("DonchianRSI", {"period_20": lambda: DonchianRSI(period=20, ...)})
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import sys
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

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

# Pre-registered universe (same across all pooled_* tests, for comparability)
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

# Per-symbol spread_pips (realistic Pepperstone Razor values)
SYMBOL_SPREAD_PIPS: dict[str, float] = {
    "XAUUSD": 100.0,
    "XAGUSD": 150.0,
    "EURUSD": 1.2,
    "GBPUSD": 1.5,
    "USDJPY": 1.2,
    "NAS100": 120.0,
    "US30": 120.0,
    "BTCUSD": 5000.0,
}

SYMBOL_COMMISSION: dict[str, float] = {
    "XAUUSD": 0.0,
    "XAGUSD": 0.0,
    "EURUSD": 7.0,
    "GBPUSD": 7.0,
    "USDJPY": 7.0,
    "NAS100": 5.0,
    "US30": 5.0,
    "BTCUSD": 0.0,
}


def load_asset_data(symbol: str) -> pd.DataFrame:
    """Load and clean asset D1 data."""
    path = ROOT / "data" / f"{symbol}_D1.csv"
    df = pd.read_csv(path)
    ts_col = "time" if "time" in df.columns else "date"
    df[ts_col] = pd.to_datetime(df[ts_col])
    df = df[df[ts_col] >= "2005-01-01"].sort_values(ts_col).reset_index(drop=True)
    return df


def run_engine_for_asset(symbol: str, strategy_factory: Callable[[], Any], cost_mult: float = 1.0) -> dict:
    """Run BacktestEngine with a strategy (from strategy_factory()) on one asset.

    strategy_factory: zero-arg callable returning a fresh `Strategy` instance
    (see strategies/base.py). Called once per asset so each run gets an
    unshared instance.

    cost_mult scales spread/slippage/commission inputs to the engine directly
    (real cost stress), rather than post-hoc rescaling returns — rescaling
    returns by a constant is a no-op on the DK t-stat (scale-invariant ratio).
    """
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
        slippage_pips=0.5 * cost_mult,
        spread_pips=SYMBOL_SPREAD_PIPS.get(symbol, 2.0) * cost_mult,
        commission_per_lot=Decimal(str(SYMBOL_COMMISSION.get(symbol, 3.5) * cost_mult)),
        risk_per_trade_bps=100,
        max_positions=1,
        strict_mtf=False,
    )

    strategy = strategy_factory()

    engine = BacktestEngine(config)
    engine._symbol = symbol  # Fix Bug #1: thread real symbol through engine
    engine.set_strategy(strategy)
    engine.load_data(ohlcv, timestamps)
    engine._check_risk_halt = lambda: False
    # Force legacy equity path — Phase 4 PnL tracker doesn't populate equity_curve
    # Monkey-patch _reset to prevent Phase 4 re-initialization during run()
    _orig_reset = engine._reset

    def _patched_reset():
        _orig_reset()
        engine._pnl_tracker = None
        engine._regime_detector = None
        # BUG #2 FIX: removed engine._margin_simulator = None
        # Margin simulation must stay active for liquidation-floor protection.

    engine._reset = _patched_reset

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


def run_one_variant(
    variant_label: str,
    strategy_factory: Callable[[], Any],
    params: dict | None = None,
    universe: list[str] | None = None,
) -> dict:
    """Run the pooled DK-test for one strategy variant across `universe`.

    params is metadata only (echoed into the report) — the actual strategy
    construction is entirely owned by strategy_factory.
    """
    universe = universe or UNIVERSE
    params = params or {}

    print("=" * 70)
    print(f"  POOLED MULTI-ASSET TEST: {variant_label}")
    print("  Driscoll-Kraay Cluster-Robust Inference")
    if params:
        print(f"  Params: {params}")
    print("=" * 70)

    all_results = {}
    per_asset_returns = {}

    for symbol in universe:
        print(f"\n  Running {symbol}...", end=" ", flush=True)
        try:
            results = run_engine_for_asset(symbol, strategy_factory)
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
        return {"variant": variant_label, "params": params, "verdict": "INSUFFICIENT_SAMPLE"}

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
    for symbol in universe:
        if symbol in all_results:
            per_asset_metrics[symbol] = compute_per_asset_metrics(all_results[symbol])

    header = f"  {'Symbol':<10} {'Trades':>7} {'Sharpe':>8} {'Win%':>6} {'PF':>6} {'NW t':>7} {'MaxDD':>7}"
    print(f"\n{header}")
    print(f"  {'-' * len(header.strip())}")

    total_trades = 0
    positive_sharpe_count = 0
    for symbol in universe:
        if symbol not in per_asset_metrics:
            continue
        m = per_asset_metrics[symbol]
        total_trades += m.get("n_trades", 0)
        if m.get("sharpe", 0) > 0:
            positive_sharpe_count += 1
        print(
            f"  {symbol:<10} {m.get('n_trades', 0):>7} {m.get('sharpe', 0):>8.4f} "
            f"{m.get('win_rate', 0) * 100:>5.1f}% {m.get('profit_factor', 0):>5.2f} "
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
        reason = "Pooled t < 1.5 OR Sharpe > 0 in < 3/8 assets"

    print(f"\n  VERDICT: {verdict}  ({reason})")

    # Real cost stress: re-run the engine with scaled spread/slippage/commission
    # inputs, not a post-hoc rescale of daily_means (which is a no-op on the
    # DK t-stat since it's a scale-invariant ratio of mean to its own std).
    cost_sensitivity = {"0pct": dk_t}
    for stress_pct in [30, 50]:
        cost_mult = 1 + stress_pct / 100
        stressed_returns = {}
        for symbol in universe:
            try:
                stressed_results = run_engine_for_asset(symbol, strategy_factory, cost_mult=cost_mult)
                daily_ret = extract_daily_returns(stressed_results)
                if not daily_ret.empty:
                    stressed_returns[symbol] = daily_ret
            except Exception:
                continue
        if len(stressed_returns) >= 3:
            stressed_panel = pd.concat(stressed_returns.values(), axis=1, join="outer").fillna(0.0)
            stressed_dk_t, _, _ = driscoll_kraay_t_stat(stressed_panel.mean(axis=1).values)
            cost_sensitivity[f"{stress_pct}pct"] = stressed_dk_t
        else:
            cost_sensitivity[f"{stress_pct}pct"] = None

    return {
        "variant": variant_label,
        "params": params,
        "universe": universe,
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
    }


def run_strategy(
    strategy_name: str,
    variants: dict[str, Callable[[], Any]],
    variant_params: dict[str, dict] | None = None,
    universe: list[str] | None = None,
    output_path: Path | str | None = None,
) -> dict:
    """Run the pooled DK-test across every variant of one strategy and write a report.

    variants: dict of variant_label -> zero-arg factory producing a fresh
              `Strategy` instance for that variant.
    variant_params: optional dict of variant_label -> params dict, echoed
              into the report for traceability (e.g. the kwargs used to
              construct the strategy). Purely informational.
    """
    variant_params = variant_params or {}
    reports = {}
    for label, factory in variants.items():
        reports[label] = run_one_variant(label, factory, params=variant_params.get(label), universe=universe)
        print("\n")

    report = {
        "timestamp": datetime.now().isoformat(),
        "strategy": strategy_name,
        "variants": reports,
    }

    output_path = (
        Path(output_path) if output_path else ROOT / "reports" / f"pooled_{strategy_name.lower()}_results.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"  Report saved: {output_path}")

    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    for key, r in reports.items():
        print(
            f"  {key}: {r.get('verdict')} (trades={r.get('total_trades', 0)}, "
            f"dk_t={r.get('pooled', {}).get('dk_t_stat', 0):.3f})"
        )

    return report


def _load_strategy_class(dotted_path: str) -> type:
    """Import a Strategy subclass from a dotted path, e.g.
    'graxia.packages.quant_os.strategies.donchian_rsi.DonchianRSI'."""
    module_path, _, class_name = dotted_path.rpartition(".")
    if not module_path:
        raise ValueError(f"--strategy must be a dotted module.ClassName path, got: {dotted_path!r}")
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def main():
    parser = argparse.ArgumentParser(description="Generic pooled multi-asset strategy DK-test")
    parser.add_argument(
        "--strategy",
        required=True,
        help="Dotted path to a Strategy subclass, e.g. " "graxia.packages.quant_os.strategies.donchian_rsi.DonchianRSI",
    )
    parser.add_argument(
        "--params",
        default="{}",
        help="JSON dict of constructor kwargs applied to every variant (base params)",
    )
    parser.add_argument(
        "--variants",
        default=None,
        help="JSON dict of variant_label -> override-kwargs dict, merged over --params. "
        "Defaults to a single variant named 'default' with no overrides.",
    )
    parser.add_argument(
        "--output", default=None, help="Report output path (defaults to reports/pooled_<strategy>_results.json)"
    )
    args = parser.parse_args()

    strategy_cls = _load_strategy_class(args.strategy)
    base_params = json.loads(args.params)
    variant_overrides = json.loads(args.variants) if args.variants else {"default": {}}

    variants = {}
    variant_params = {}
    for label, overrides in variant_overrides.items():
        merged = {**base_params, **overrides}
        variants[label] = lambda cls=strategy_cls, kw=merged: cls(**kw)
        variant_params[label] = merged

    run_strategy(strategy_cls.__name__, variants, variant_params=variant_params, output_path=args.output)


if __name__ == "__main__":
    main()
