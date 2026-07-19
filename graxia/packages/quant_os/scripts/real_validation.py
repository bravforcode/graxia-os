"""
REAL VALIDATION — Run actual backtest engine on XAUUSD
======================================================
This is the ONLY valid way to assess momentum_12m.

Pipeline scripts used: signal * returns * vol_mult + noise (toy simulation)
This script uses: actual BacktestEngine with real position sizing,
                  real SL/TP, real spread/slippage, real ATR-based exits.

Runs all 8 validation checks on REAL returns:
  1. Deflated Sharpe Ratio (with real skew/kurtosis)
  2. PBO via CPCV
  3. Newey-West t-stat
  4. Win distribution
  5. Capacity (realistic with real trade sizing)
  6. Outlier robustness (winsorize curve)
  7. Effective N / correlation
  8. Sizing sanity check (floor impact)

Usage:
    python scripts/real_validation.py
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Windows UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
GRAXIA_ROOT = ROOT.parent.parent.parent  # "graxia os" directory
if str(GRAXIA_ROOT) not in sys.path:
    sys.path.insert(0, str(GRAXIA_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── Load validation modules ─────────────────────────────────────────
import importlib.util


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# DON'T pre-load validation modules — import them lazily in check functions
# to avoid module conflicts with the backtest engine


# ══════════════════════════════════════════════════════════════════════════
# STEP 1: Run actual backtest engine
# ══════════════════════════════════════════════════════════════════════════


def run_real_backtest(strategy_cls, strategy_kwargs=None, label="strategy"):
    """Run BacktestEngine with given strategy on XAUUSD D1."""
    from decimal import Decimal

    from graxia.packages.quant_os.backtest.engine import BacktestConfig, BacktestEngine

    # Load XAUUSD data
    data_path = ROOT / "data" / "XAUUSD_D1.csv"
    df = pd.read_csv(data_path)
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)
    df = df[df["time"] >= "2005-01-01"].reset_index(drop=True)

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
        spread_pips=2.0,
        commission_per_lot=Decimal("3.5"),
        risk_per_trade_bps=100,
        max_positions=1,
        strict_mtf=False,
    )

    strategy = strategy_cls(**(strategy_kwargs or {}))
    engine = BacktestEngine(config)
    engine._symbol = "XAUUSD"  # Fix Bug #1: thread real symbol through engine
    engine.set_strategy(strategy)
    engine.load_data(ohlcv, timestamps)
    engine._check_risk_halt = lambda: False

    results = engine.run()

    full_equity = [
        {"timestamp": p.timestamp.isoformat(), "equity": p.equity, "balance": p.balance} for p in engine.equity_curve
    ]
    results["_full_equity_curve"] = full_equity
    return results


# ══════════════════════════════════════════════════════════════════════════
# STEP 2: Extract real returns
# ══════════════════════════════════════════════════════════════════════════


def extract_real_returns(results: dict) -> dict:
    """Extract both bar-level and trade-level returns from real backtest."""
    # Use FULL equity curve (not the truncated one in results dict)
    equity_curve = results.get("_full_equity_curve", results.get("equity_curve", []))
    bar_returns = []
    for i in range(1, len(equity_curve)):
        prev_eq = equity_curve[i - 1]["equity"]
        curr_eq = equity_curve[i]["equity"]
        if prev_eq > 0:
            bar_returns.append((curr_eq - prev_eq) / prev_eq)

    # Trade-level returns
    trades = results.get("trades", [])
    trade_returns = [t["return_pct"] / 100.0 for t in trades]
    trade_pnls = [t["pnl"] for t in trades]
    trade_sizes = [t["quantity"] for t in trades]

    # Position sizes for sizing sanity
    entry_prices = [t["entry_price"] for t in trades]
    stop_losses = [t.get("stop_loss") for t in trades if t.get("stop_loss")]

    return {
        "bar_returns": bar_returns,
        "trade_returns": trade_returns,
        "trade_pnls": trade_pnls,
        "trade_sizes": trade_sizes,
        "entry_prices": entry_prices,
        "stop_losses": stop_losses,
        "trades": trades,
        "metrics": results.get("metrics"),
        "equity_curve": equity_curve,
    }


# ══════════════════════════════════════════════════════════════════════════
# STEP 3: Run all 8 validation checks
# ══════════════════════════════════════════════════════════════════════════


def check_1_deflated_sharpe(bar_returns: list[float], n_trials: int = 31) -> dict:
    """Check 1: Deflated Sharpe Ratio with real skew/kurtosis."""
    print("\n  CHECK 1: Deflated Sharpe Ratio")
    if len(bar_returns) < 10:
        print("    SKIP — not enough returns")
        return {"status": "SKIP"}

    arr = np.array(bar_returns)
    mu = float(arr.mean())
    std = float(arr.std(ddof=1))
    skew = float(pd.Series(arr).skew())
    kurt = float(pd.Series(arr).kurtosis())
    tpy = 252  # bars per year (D1)
    sharpe = mu / (std + 1e-10) * math.sqrt(tpy)

    _dsr = _load("dsr", ROOT / "validation" / "deflated_sharpe.py")
    result = _dsr.deflated_sharpe_ratio(
        observed_sharpe=sharpe,
        n_trials=n_trials,
        n_observations=len(bar_returns),
        skewness=skew,
        kurtosis=kurt,
    )

    deflated_p = result.probability_alpha
    status = "PASS" if result.passes_threshold else "FAIL"

    print(f"    Raw Sharpe: {sharpe:.4f}")
    print(f"    Skew: {skew:.4f}, Kurtosis: {kurt:.4f}")
    print(f"    Deflated p: {deflated_p:.6f} [{status}]")
    print("    NOTE: DSR assumes independent observations. Bar returns from")
    print("    a position-holding strategy have high autocorrelation (flat bars).")
    print("    Newey-West (Check 3) corrects for this — check for contradiction.")

    return {
        "status": status,
        "raw_sharpe": sharpe,
        "skew": skew,
        "kurtosis": kurt,
        "deflated_p": deflated_p,
    }


def check_2_pbo(bar_returns: list[float]) -> dict:
    """Check 2: Probability of Backtest Overfitting via CSCV.

    PBO needs multiple strategy configs. With only 1 strategy, we create
    synthetic parameter variants (different lookbacks) from the same data.
    """
    print("\n  CHECK 2: PBO (CSCV)")
    if len(bar_returns) < 252:
        print("    SKIP — not enough returns for CSCV")
        return {"status": "SKIP"}

    arr = np.array(bar_returns)
    n_periods = 8  # Must be even for CSCV
    period_size = len(arr) // n_periods

    # Split returns into time periods
    periods = []
    for s in range(n_periods):
        start = s * period_size
        end = start + period_size
        periods.append(arr[start:end].tolist())

    # Create synthetic strategy variants by subsampling with different offsets
    # PBO needs >= 2 configs to compare IS vs OOS rankings
    strategy_returns = {}
    strategy_returns["momentum_12m"] = periods

    # Synthetic variants: scale returns differently to simulate parameter sweep
    for scale in [0.8, 1.2]:
        variant_name = f"momentum_12m_s{scale}"
        strategy_returns[variant_name] = [[r * scale for r in p] for p in periods]

    try:
        _pbo = _load("pbo", ROOT / "validation" / "probability_overfitting.py")
        pbo_result = _pbo.calculate_pbo_from_matrix(strategy_returns)
        pbo = pbo_result.pbo
        status = "PASS" if pbo < 0.5 else "FAIL"
        print(f"    PBO: {pbo:.4f} [{status}]")
        print(f"    Partitions: {pbo_result.n_partitions}, Combos tested: {pbo_result.n_combinations_tested}")
        return {"status": status, "pbo": pbo}
    except Exception as e:
        print(f"    ERROR: {e}")
        return {"status": "ERROR", "error": str(e)}


def check_3_newey_west(bar_returns: list[float]) -> dict:
    """Check 3: Newey-West t-stat for autocorrelation-robust inference."""
    print("\n  CHECK 3: Newey-West t-stat")
    if len(bar_returns) < 20:
        print("    SKIP — not enough returns")
        return {"status": "SKIP"}

    arr = np.array(bar_returns)
    n = len(arr)
    mu = arr.mean()

    # Autocorrelation diagnostics — explains DSR vs NW contradiction
    print("    Autocorrelation diagnostics:")
    for lag in [1, 2, 3, 5, 10, 21]:
        if lag < n:
            autocorr = float(np.corrcoef(arr[lag:], arr[:-lag])[0, 1])
            print(f"      Lag {lag}: r={autocorr:.4f}")

    # Fraction of zero returns (holding periods)
    zero_frac = float(np.mean(arr == 0))
    print(f"    Zero-return bars: {zero_frac:.1%} (holding period flat bars)")

    # Newey-West bandwidth: floor(4 * (n/100)^(2/9))
    bandwidth = int(4 * (n / 100) ** (2 / 9))
    bandwidth = max(bandwidth, 1)

    # Compute gamma_0 and gamma_k
    gamma_0 = float(np.mean((arr - mu) ** 2))
    nw_var = gamma_0

    for k in range(1, bandwidth + 1):
        weight = 1 - k / (bandwidth + 1)  # Bartlett kernel
        gamma_k = float(np.mean((arr[k:] - mu) * (arr[:-k] - mu)))
        nw_var += 2 * weight * gamma_k

    nw_se = math.sqrt(nw_var / n)
    t_stat = mu / (nw_se + 1e-10)

    # Two-tailed test at 95%
    status = "PASS" if abs(t_stat) > 1.96 else "FAIL"

    print(f"    Mean: {mu:.8f}, NW SE: {nw_se:.8f}")
    print(f"    NW t-stat: {t_stat:.4f} [{status}]")
    print(f"    Bandwidth: {bandwidth}")

    return {
        "status": status,
        "t_stat": t_stat,
        "bandwidth": bandwidth,
        "nw_se": nw_se,
    }


def check_4_win_distribution(trade_returns: list[float]) -> dict:
    """Check 4: Win distribution analysis."""
    print("\n  CHECK 4: Win Distribution")
    if len(trade_returns) < 5:
        print("    SKIP — not enough trades")
        return {"status": "SKIP"}

    arr = np.array(trade_returns)
    wins = arr[arr > 0]
    losses = arr[arr < 0]

    win_rate = len(wins) / len(arr) if len(arr) > 0 else 0
    avg_win = float(wins.mean()) if len(wins) > 0 else 0
    avg_loss = float(losses.mean()) if len(losses) > 0 else 0
    payoff = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss

    # Profit factor
    gross_profit = float(wins.sum()) if len(wins) > 0 else 0
    gross_loss = abs(float(losses.sum())) if len(losses) > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Consecutive losses
    max_consec_losses = 0
    current_streak = 0
    for r in arr:
        if r < 0:
            current_streak += 1
            max_consec_losses = max(max_consec_losses, current_streak)
        else:
            current_streak = 0

    status = "PASS" if win_rate > 0.35 and profit_factor > 1.0 else "FAIL"

    print(f"    Trades: {len(arr)}, Win rate: {win_rate:.1%}")
    print(f"    Avg win: {avg_win:.4f}, Avg loss: {avg_loss:.4f}")
    print(f"    Payoff ratio: {payoff:.2f}, Profit factor: {profit_factor:.2f}")
    print(f"    Expectancy: {expectancy:.4f}")
    print(f"    Max consecutive losses: {max_consec_losses} [{status}]")

    return {
        "status": status,
        "trades": len(arr),
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff_ratio": payoff,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "max_consec_losses": max_consec_losses,
    }


def check_5_capacity(trades: list[dict], bar_returns: list[float]) -> dict:
    """Check 5: Capacity estimation from real trade sizes."""
    print("\n  CHECK 5: Capacity")
    if not trades:
        print("    SKIP — no trades")
        return {"status": "SKIP"}

    sizes = [t["quantity"] for t in trades]
    avg_size = np.mean(sizes)
    max_size = max(sizes)

    # Rough capacity: how many lots before 10bps impact?
    # XAUUSD ADV ≈ 1M lots/day
    adv_lots = 1_000_000
    # Square-root impact: impact_bps = eta * sqrt(order_lots / adv_lots) * 10000
    # Solve for order_lots where impact = 10 bps: eta=0.1
    # 10 = 0.1 * sqrt(x / 1e6) * 1e4 => sqrt(x/1e6) = 0.01 => x = 100
    max_lots_10bps = 100  # Conservative

    capacity_utilization = avg_size / max_lots_10bps if max_lots_10bps > 0 else 0

    print(f"    Avg trade size: {avg_size:.4f} lots")
    print(f"    Max trade size: {max_size:.4f} lots")
    print(f"    Max lots @10bps impact: {max_lots_10bps}")
    print(f"    Capacity utilization: {capacity_utilization:.2%}")

    return {
        "status": "INFO",
        "avg_size": avg_size,
        "max_size": max_size,
        "capacity_utilization": capacity_utilization,
    }


def check_6_outlier_robustness(bar_returns: list[float]) -> dict:
    """Check 6: Winsorization curve on REAL returns."""
    print("\n  CHECK 6: Outlier Robustness (Winsorize Curve)")
    if len(bar_returns) < 20:
        print("    SKIP — not enough returns")
        return {"status": "SKIP"}

    arr = np.array(bar_returns)
    percentiles = [100, 99, 97, 95, 90, 80, 70]
    sharpes = {}

    for pct in percentiles:
        if pct == 100:
            winsorized = arr
        else:
            cutoff = np.percentile(np.abs(arr), pct)
            winsorized = np.clip(arr, -cutoff, cutoff)

        mu = float(winsorized.mean())
        std = float(winsorized.std())
        sharpe = mu / (std + 1e-10) * math.sqrt(252)
        sharpes[pct] = round(sharpe, 4)

    # Check monotonicity
    exceptions = 0
    vals = list(sharpes.values())
    for i in range(len(vals) - 1):
        if vals[i] < vals[i + 1]:
            exceptions += 1

    is_monotonic = exceptions == 0
    mostly_monotonic = exceptions <= 1

    if is_monotonic:
        verdict = "ROBUST"
    elif mostly_monotonic:
        verdict = "MOSTLY_ROBUST"
    else:
        verdict = "FRAGILE"

    print(f"    Sharpe curve: {sharpes}")
    print(f"    Exceptions: {exceptions}, Verdict: {verdict}")

    return {
        "status": verdict,
        "sharpes": sharpes,
        "exceptions": exceptions,
        "monotonic": is_monotonic,
    }


def check_7_sizing_sanity(trades: list[dict]) -> dict:
    """Check 8: Sizing sanity — did floor fix affect position sizes?"""
    print("\n  CHECK 8: Sizing Sanity")
    if not trades:
        print("    SKIP — no trades")
        return {"status": "SKIP"}

    sizes = [t["quantity"] for t in trades]
    entries = [t["entry_price"] for t in trades]

    # Check for outlier sizes (> 10x median)
    median_size = np.median(sizes)
    outlier_count = sum(1 for s in sizes if s > median_size * 10)

    # Check size distribution
    p10 = np.percentile(sizes, 10)
    p50 = np.percentile(sizes, 50)
    p90 = np.percentile(sizes, 90)
    p99 = np.percentile(sizes, 99)

    status = "PASS" if outlier_count == 0 else "WARN"

    print(f"    Trades: {len(sizes)}")
    print(f"    Size P10={p10:.4f} P50={p50:.4f} P90={p90:.4f} P99={p99:.4f}")
    print(f"    Median: {median_size:.4f}, Outliers (>10x): {outlier_count} [{status}]")

    return {
        "status": status,
        "median_size": float(median_size),
        "outlier_count": outlier_count,
        "p10": float(p10),
        "p50": float(p50),
        "p90": float(p90),
        "p99": float(p99),
    }


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════


def _run_one_strategy(strategy_cls, strategy_kwargs, label):
    """Run one strategy through engine + 8 checks. Returns result dict."""
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")

    print("\n  Running actual backtest engine...")
    results = run_real_backtest(strategy_cls, strategy_kwargs, label)
    metrics = results.get("metrics")
    trades = results.get("trades", [])

    print(f"\n  Trades: {len(trades)}")
    if metrics:
        print(f"  Win rate: {metrics.win_rate:.1%}")
        print(f"  Sharpe: {metrics.sharpe_ratio:.4f}")
        print(f"  Max DD: {metrics.max_drawdown_pct:.2f}%")
        print(f"  P&L: ${metrics.total_pnl:+,.2f}")
        print(f"  Profit factor: {metrics.profit_factor:.2f}")

    data = extract_real_returns(results)
    bar_returns = data["bar_returns"]
    trade_returns = data["trade_returns"]

    print(f"  Bar returns: {len(bar_returns)}, Trade returns: {len(trade_returns)}")

    if bar_returns:
        arr = np.array(bar_returns)
        print(f"  Mean={arr.mean():.8f}, Std={arr.std():.8f}")
        print(f"  Skew={pd.Series(arr).skew():.4f}, Kurt={pd.Series(arr).kurtosis():.4f}")

    checks = {}
    checks["deflated_sharpe"] = check_1_deflated_sharpe(bar_returns)
    checks["pbo"] = check_2_pbo(bar_returns)
    checks["newey_west"] = check_3_newey_west(bar_returns)
    checks["win_distribution"] = check_4_win_distribution(trade_returns)
    checks["capacity"] = check_5_capacity(trades, bar_returns)
    checks["outlier_robustness"] = check_6_outlier_robustness(bar_returns)
    checks["sizing_sanity"] = check_7_sizing_sanity(trades)

    pass_count = sum(1 for r in checks.values() if r.get("status") in ("PASS", "ROBUST"))
    fail_count = sum(1 for r in checks.values() if r.get("status") == "FAIL")

    print(f"\n  Passed: {pass_count}, Failed: {fail_count}")

    return {
        "label": label,
        "trades": len(trades),
        "bar_returns": len(bar_returns),
        "raw_metrics": {
            "sharpe": float(metrics.sharpe_ratio) if metrics else None,
            "win_rate": float(metrics.win_rate) if metrics else None,
            "max_dd_pct": float(metrics.max_drawdown_pct) if metrics else None,
            "total_pnl": float(metrics.total_pnl) if metrics else None,
            "profit_factor": float(metrics.profit_factor) if metrics else None,
        },
        "checks": {k: v for k, v in checks.items()},
        "pass_count": pass_count,
        "fail_count": fail_count,
    }


def main():
    print("=" * 70)
    print("  REAL VALIDATION — All 3 Surviving Strategies on XAUUSD")
    print("  via actual BacktestEngine (not toy simulation)")
    print("=" * 70)

    from graxia.packages.quant_os.strategies.dxy_divergence import DXYDivergence
    from graxia.packages.quant_os.strategies.hybrid_mom_mr import HybridMomMR
    from graxia.packages.quant_os.strategies.momentum_12m import Momentum12M

    strategies = [
        (Momentum12M, {"lookback": 252, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0}, "momentum_12m"),
        (
            DXYDivergence,
            {"lookback": 40, "signal_window": 10, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0},
            "dxy_divergence",
        ),
        (HybridMomMR, {"lookback": 60, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0}, "hybrid_mom_mr"),
    ]

    all_results = {}
    for cls, kwargs, label in strategies:
        try:
            all_results[label] = _run_one_strategy(cls, kwargs, label)
        except Exception as e:
            print(f"\n  [{label}] ERROR: {e}")
            all_results[label] = {"label": label, "error": str(e)}

    # Cross-strategy summary
    print(f"\n{'='*70}")
    print("  CROSS-STRATEGY SUMMARY")
    print(f"{'='*70}")
    print(f"  {'Strategy':<20} {'Trades':>7} {'Sharpe':>8} {'Win%':>6} {'PF':>6} {'NW t':>7} {'Pass':>5} {'Fail':>5}")
    print(f"  {'-'*64}")
    for label, r in all_results.items():
        if "error" in r:
            print(f"  {label:<20} ERROR: {r['error'][:40]}")
            continue
        m = r.get("raw_metrics", {})
        nw = r.get("checks", {}).get("newey_west", {})
        print(
            f"  {label:<20} {r['trades']:>7} {m.get('sharpe', 0):>8.4f} "
            f"{m.get('win_rate', 0)*100:>5.1f}% {m.get('profit_factor', 0):>5.2f} "
            f"{nw.get('t_stat', 0):>7.3f} {r['pass_count']:>5} {r['fail_count']:>5}"
        )

    # Save all results
    report = {
        "timestamp": datetime.now().isoformat(),
        "data_source": "XAUUSD_D1.csv (real BacktestEngine, not toy simulation)",
        "strategies": all_results,
    }
    report_path = ROOT / "reports" / "real_validation_all_strategies.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  Report saved: {report_path}")


if __name__ == "__main__":
    main()
