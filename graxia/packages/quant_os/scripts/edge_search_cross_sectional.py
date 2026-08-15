"""
Cross-Sectional Edge Search — Momentum Factor Rotation with Pooled DK-test
==========================================================================
Phase 0A of MEGA_PLAN_v2. Wires momentum_factor_rotation.py into the
pooled DK-test harness from edge_search_all.py.

Honest search: same universe, same costs, same DK threshold.
Does NOT burn sacred holdout. Does NOT claim live edge without GO + label-shuffle.

GO criteria (pre-registered):
  dk_t > 2.0 AND pos_sharpe >= 5 AND label_shuffle_p < 0.05  → GO
  dk_t > 1.5 OR (dk_t > 1.0 AND pos_sharpe >= 4)             → MARGINAL
  else                                                         → REJECT

FROZEN parameters (pre-registered, never tuned after seeing results):
  lookbacks = (21, 63, 252)   vol_target = 0.10   kappa = 2.0
  top_n = 2                   bottom_n = 0         rebalance_freq = 5
  min_signal_strength = 0.3

Usage:
  python scripts/edge_search_cross_sectional.py \\
      --universe XAUUSD,XAGUSD,EURUSD,GBPUSD,USDJPY,NAS100,US30 \\
      --cost-model pepperstone_razor \\
      --cost-multiplier 1.0 \\
      --dk-test pooled \\
      --label-shuffle 200 \\
      --min-years 8 \\
      --output reports/edge_search_cross_sectional_20260720.json
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

from graxia.packages.quant_os.strategies.momentum_factor_rotation import (
    MomentumFactorRotationConfig,
    compute_momentum_factor_rotation,
)
from graxia.packages.quant_os.strategies.tsmom import compute_tsmom_signal  # noqa: F401
from graxia.packages.quant_os.backtest.engine import BacktestConfig, BacktestEngine
from graxia.packages.quant_os.strategies.base import Strategy, Signal, SignalType, StrategyConfig
from decimal import Decimal
from typing import Any


# ---------------------------------------------------------------------------
# Engine-based backtest helpers (replaces standalone pct_change logic)
# ---------------------------------------------------------------------------

class _MomentumSignalAdapter(Strategy):
    """Wraps pre-computed momentum_factor_rotation signals into engine-compatible Signal."""

    def __init__(self, symbol: str, signal_array: np.ndarray, sl_mult: float = 2.0):
        config = StrategyConfig(name="MomentumAdapter", version="1.0", symbols=[symbol],
                                 timeframes=["D1"], risk_per_trade_pct=1.0, max_trades_per_day=1,
                                 require_trend_confirm=False)
        super().__init__(config)
        self._sym = symbol
        self._signals = signal_array
        self._sl_mult = sl_mult
        self._last_sig = 0.0

    def required_features(self) -> list[str]:
        return ["momentum_signal"]

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        n = len(ohlcv_data.get("close", []))
        if n == 0 or n > len(self._signals):
            return None
        cur = float(self._signals[n - 1])
        if cur == self._last_sig:
            return None
        self._last_sig = cur
        if cur == 0 or np.isnan(cur):
            return None
        st = SignalType.BUY if cur > 0 else SignalType.SELL
        entry = float(ohlcv_data["close"][-1])
        h = np.array(ohlcv_data.get("high", []), dtype=float)
        l = np.array(ohlcv_data.get("low", []), dtype=float)
        c = np.array(ohlcv_data.get("close", []), dtype=float)
        atr = 0.0
        if len(h) >= 15:
            tr = np.maximum.reduce([h[1:]-l[1:], np.abs(h[1:]-c[:-1]), np.abs(l[1:]-c[:-1])])
            atr = float(np.mean(tr[-14:])) if len(tr) >= 14 else 0.0
        sl = None
        if entry > 0 and atr > 0:
            sl = Decimal(str(entry - atr * self._sl_mult if st == SignalType.BUY else entry + atr * self._sl_mult))
        return Signal.create(strategy_id=self.id, symbol=symbol, signal_type=st,
                              confidence=abs(cur), entry_price=Decimal(str(entry)), stop_loss=sl)


def _extract_daily_returns(equity_curve: list) -> pd.Series:
    eq = pd.Series([float(e.equity if hasattr(e, "equity") else e.get("equity", 0))
                     for e in equity_curve])
    return eq.pct_change().dropna() if len(eq) >= 2 else pd.Series(dtype=float)


def _calc_max_dd(equity_curve: list) -> float:
    eq = pd.Series([float(e.equity if hasattr(e, "equity") else e.get("equity", 0))
                     for e in equity_curve])
    return float((eq / eq.cummax() - 1).min()) if len(eq) > 0 else 0.0


def load_asset_data_raw(symbol: str) -> pd.DataFrame | None:
    for ext in [".csv"]:
        p = ROOT / "data" / f"{symbol}_D1{ext}"
        if p.exists():
            df = pd.read_csv(p)
            for col in ["time", "date"]:
                if col in df.columns:
                    df["time"] = pd.to_datetime(df[col])
                    df = df.set_index("time")
                    break
            for c in ["open", "high", "low", "close", "volume"]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            return df.dropna(subset=["close"])
    return None


# ---------------------------------------------------------------------------
# Pre-registered universe
# ---------------------------------------------------------------------------

CORE_UNIVERSE = [
    "XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "US30",
]

MIN_BARS = 500


# ---------------------------------------------------------------------------
# Pepperstone Razor cost model (same as edge_search_all.py)
# ---------------------------------------------------------------------------

SYMBOL_SPREAD_PIPS: dict[str, float] = {
    "XAUUSD": 100.0,
    "XAGUSD": 150.0,
    "EURUSD": 1.2,
    "GBPUSD": 1.5,
    "USDJPY": 1.2,
    "NAS100": 120.0,
    "US30": 120.0,
}

SYMBOL_COMMISSION: dict[str, float] = {
    "XAUUSD": 0.0,
    "XAGUSD": 0.0,
    "EURUSD": 7.0,
    "GBPUSD": 7.0,
    "USDJPY": 7.0,
    "NAS100": 5.0,
    "US30": 5.0,
}

# Asset-class cost denominators (matching edge_search_all.py engine model)
# FX:  spread in pips  → pip_value ($/pip/lot) + $/rt commission
# Metals/Indices: spread in points → point_value ($/point/lot)
PIP_VALUE: dict[str, float] = {
    "EURUSD": 10.0,   # $10/pip/lot
    "GBPUSD": 10.0,
    "USDJPY": 6.67,   # $6.67/pip/lot (1 pip = 0.01 JPY; lot=100k units)
}

POINT_VALUE: dict[str, float] = {
    "XAUUSD": 1.0,    # $1/point/lot (100 oz × $0.01)
    "XAGUSD": 5.0,    # $5/point/lot (5000 oz × $0.001)
    "NAS100": 1.0,    # $1/point/lot (1 contract)
    "US30":  1.0,     # $1/point/lot (1 contract)
}


def per_trade_cost(symbol: str, cost_multiplier: float = 1.0) -> float:
    """Dollar cost per round-trip trade (1 standard lot)."""
    spread = SYMBOL_SPREAD_PIPS.get(symbol, 0.0)
    commission = SYMBOL_COMMISSION.get(symbol, 0.0)
    if symbol in PIP_VALUE:
        return (spread * PIP_VALUE[symbol] + commission) * cost_multiplier
    if symbol in POINT_VALUE:
        return spread * POINT_VALUE[symbol] * cost_multiplier
    return 0.0


# ---------------------------------------------------------------------------
# Data loading (same path convention as edge_search_all.py)
# ---------------------------------------------------------------------------


def load_asset_data(symbol: str) -> pd.DataFrame:
    """Load D1 OHLCV data, filtered to >= 2005-01-01."""
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


# ---------------------------------------------------------------------------
# DK-test (EXACT same formula as edge_search_all.py — Newey-West, T^(1/3) lags)
# ---------------------------------------------------------------------------


def run_dk_test(all_returns: pd.DataFrame, total_trades: int) -> dict:
    """Pooled Driscoll-Kraay test with Newey-West HAC correction.

    Identical formula to edge_search_all.run_dk_test().
    """
    if all_returns.empty or len(all_returns.columns) < 2:
        return {
            "dk_t_stat": 0.0, "pooled_sharpe": 0.0,
            "positive_sharpe_count": 0, "total_assets": 0,
            "total_days": 0, "total_trades": total_trades,
            "verdict": "INSUFFICIENT_DATA",
        }

    cs_mean = all_returns.mean(axis=1).dropna()
    if len(cs_mean) < 30:
        return {
            "dk_t_stat": 0.0, "pooled_sharpe": 0.0,
            "positive_sharpe_count": 0, "total_assets": len(all_returns.columns),
            "total_days": len(cs_mean), "total_trades": total_trades,
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

    # Count assets with positive individual Sharpe
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
# Per-asset metrics
# ---------------------------------------------------------------------------


def compute_asset_metrics(daily_ret: pd.Series) -> dict:
    """Compute Sharpe, total return, max drawdown from a daily return series."""
    r = daily_ret.dropna()
    if len(r) < 2:
        return {"trades": 0, "sharpe": 0.0, "return": 0.0, "max_dd": 0.0, "days": 0}

    mu = float(r.mean())
    std = float(r.std(ddof=1))
    sharpe = mu / (std + 1e-10) * math.sqrt(252)

    cum = (1 + r).cumprod()
    total_ret = float(cum.iloc[-1] - 1)

    peak = cum.cummax()
    dd = (cum - peak) / peak
    max_dd = float(dd.min())

    return {
        "sharpe": round(sharpe, 4),
        "return": round(total_ret, 6),
        "max_dd": round(max_dd, 6),
        "days": len(r),
    }


# ---------------------------------------------------------------------------
# Regime detection (coarse, date-based)
# ---------------------------------------------------------------------------

CRISIS_WINDOWS = [
    ("2008-09-01", "2009-03-31"),  # GFC
    ("2011-08-01", "2011-10-31"),  # EU debt
    ("2015-08-10", "2015-09-30"),  # CNY deval
    ("2016-06-20", "2016-07-15"),  # Brexit
    ("2018-02-01", "2018-03-31"),  # VIX blow-up
    ("2020-02-15", "2020-04-30"),  # COVID
    ("2022-02-20", "2022-06-30"),  # Russia/Ukraine + inflation
]


def detect_regime_coverage(prices_df: pd.DataFrame) -> dict[str, bool]:
    """Check if the data spans crisis, trend, and choppy periods."""
    if prices_df.empty:
        return {"crisis": False, "trend": False, "choppy": False}

    idx = prices_df.index
    crisis = any(
        idx[0] <= pd.Timestamp(s) and idx[-1] >= pd.Timestamp(e)
        for s, e in CRISIS_WINDOWS
    )

    # Trend: check if any asset has a 12-month return > 20% or < -20%
    if len(prices_df) > 252:
        rolling_ret = prices_df.pct_change(252).dropna()
        has_trend = bool((rolling_ret.abs() > 0.20).any().any())
    else:
        has_trend = False

    # Choppy: check if average 20-day realized vol is elevated
    if len(prices_df) > 20:
        vol20 = prices_df.pct_change().rolling(20).std() * math.sqrt(252)
        avg_vol = vol20.mean().mean()
        has_choppy = bool(avg_vol > 0.10)  # >10% annualized vol
    else:
        has_choppy = False

    return {"crisis": crisis, "trend": has_trend, "choppy": has_choppy}


# ---------------------------------------------------------------------------
# Effective-N (correlation-adjusted independent bets)
# ---------------------------------------------------------------------------


def compute_effective_n(returns: pd.DataFrame) -> dict:
    """Compute effective number of independent bets from return correlation.

    Uses eigenvalue-based participation ratio: N_eff = (sum(lambda_i))^2 / sum(lambda_i^2)
    where lambda_i are eigenvalues of the correlation matrix.

    More robust than the simple avg_corr formula for heterogeneous correlation structures.
    """
    corr = returns.corr()
    n = len(corr)
    if n < 2:
        return {"n_nominal": n, "n_effective": float(n), "method": "trivial"}

    eigenvalues = np.linalg.eigvalsh(corr.values)
    eigenvalues = eigenvalues[eigenvalues > 1e-10]  # drop near-zero
    sum_eig = eigenvalues.sum()
    sum_eig_sq = (eigenvalues ** 2).sum()
    n_eff = (sum_eig ** 2) / sum_eig_sq if sum_eig_sq > 0 else float(n)

    # Also compute simple avg_corr for reference
    mask = np.triu(np.ones_like(corr.values, dtype=bool), k=1)
    avg_corr = float(corr.values[mask].mean())

    return {
        "n_nominal": n,
        "n_effective": round(n_eff, 2),
        "avg_pairwise_corr": round(avg_corr, 4),
        "diversification_ratio": round(n_eff / n, 4),
        "method": "eigenvalue_participation_ratio",
    }


# ---------------------------------------------------------------------------
# Monte Carlo ruin wiring
# ---------------------------------------------------------------------------


def run_monte_carlo_ruin(
    trade_returns: np.ndarray,
    starting_balance: float = 100_000.0,
    kill_threshold_dd: float = 0.20,
    n_sims: int = 1000,
    horizon_months: int = 6,
) -> dict:
    """Bootstrap-resample trade returns to estimate ruin probability.

    Uses the existing core.risk.monte_carlo.bootstrap_equity_paths engine.
    """
    try:
        from core.risk.monte_carlo import bootstrap_equity_paths
    except ImportError:
        return {"error": "core.risk.monte_carlo not importable", "prob_ruin_6mo": None}

    # Approximate trades per month (daily data, ~21 trading days, ~1 trade/rebalance)
    trades_per_month = max(1, len(trade_returns) // max(1, horizon_months * 4))
    n_trades_forward = trades_per_month * horizon_months

    # Convert percentage returns to dollar P&L
    trade_pnls = trade_returns * starting_balance

    kill_switch_balance = starting_balance * (1.0 - kill_threshold_dd)

    result = bootstrap_equity_paths(
        trade_pnls=trade_pnls,
        n_sims=n_sims,
        n_trades_forward=n_trades_forward,
        starting_balance=starting_balance,
        kill_switch_balance=kill_switch_balance,
    )

    return {
        "prob_ruin_6mo": round(result["prob_ruin"], 4),
        "median_max_dd_pct": round(result["median_max_dd_pct"] * 100, 2),
        "p95_max_dd_pct": round(result["p95_max_dd_pct"] * 100, 2),
        "n_sims": n_sims,
        "horizon_months": horizon_months,
        "kill_threshold_dd": kill_threshold_dd,
    }


# ---------------------------------------------------------------------------
# Lot-size / margin feasibility check (G9)
# ---------------------------------------------------------------------------

# Pepperstone Razor lot specifications (standard, not account-specific)
_PEPPERSTONE_LOT_SPECS: dict[str, dict] = {
    "XAUUSD": {"min_lot": 0.01, "lot_step": 0.01, "contract_size": 100},
    "XAGUSD": {"min_lot": 0.01, "lot_step": 0.01, "contract_size": 5000},
    "EURUSD": {"min_lot": 0.01, "lot_step": 0.01, "contract_size": 100_000},
    "GBPUSD": {"min_lot": 0.01, "lot_step": 0.01, "contract_size": 100_000},
    "USDJPY": {"min_lot": 0.01, "lot_step": 0.01, "contract_size": 100_000},
    "NAS100": {"min_lot": 0.01, "lot_step": 0.01, "contract_size": 1},
    "US30":   {"min_lot": 0.01, "lot_step": 0.01, "contract_size": 1},
}


def check_lot_feasibility(
    theoretical_lots: dict[str, list[float]],
) -> dict:
    """Check that theoretical position sizes map to tradable lot sizes.

    Args:
        theoretical_lots: {symbol: [lot_sizes across backtest]}

    Returns:
        Per-symbol and aggregate feasibility report.
    """
    report = {}
    all_deviations = []

    for symbol, lots in theoretical_lots.items():
        spec = _PEPPERSTONE_LOT_SPECS.get(symbol)
        if spec is None:
            report[symbol] = {"status": "UNKNOWN_SYMBOL", "deviations": []}
            continue

        min_lot = spec["min_lot"]
        lot_step = spec["lot_step"]

        deviations = []
        for theoretical in lots:
            if theoretical <= 0:
                continue
            # Snap to nearest tradable lot size
            tradable = max(min_lot, round(theoretical / lot_step) * lot_step)
            if theoretical > 0:
                dev_pct = abs(tradable - theoretical) / theoretical * 100
                deviations.append(dev_pct)

        mean_dev = float(np.mean(deviations)) if deviations else 0.0
        max_dev = float(np.max(deviations)) if deviations else 0.0
        pct_over_10 = float(np.mean([1 for d in deviations if d > 10])) * 100 if deviations else 0.0

        report[symbol] = {
            "mean_deviation_pct": round(mean_dev, 2),
            "max_deviation_pct": round(max_dev, 2),
            "pct_trades_over_10pct_dev": round(pct_over_10, 1),
            "n_trades": len(lots),
            "status": "OK" if mean_dev < 10 else "MATERIAL_DEVIATION",
        }
        all_deviations.extend(deviations)

    aggregate_dev = float(np.mean(all_deviations)) if all_deviations else 0.0
    return {
        "per_symbol": report,
        "aggregate_mean_deviation_pct": round(aggregate_dev, 2),
        "status": "OK" if aggregate_dev < 10 else "MATERIAL_DEVIATION",
    }


# ---------------------------------------------------------------------------
# Label shuffle (noise-proof test)
# ---------------------------------------------------------------------------


def label_shuffle_test(
    all_returns: pd.DataFrame,
    observed_t: float,
    n_shuffles: int = 200,
    seed: int = 42,
    block_length: int = 10,
) -> dict:
    """Stationary-bootstrap label shuffle (Politis & Romano 1994), recompute DK-t.

    Preserves autocorrelation and volatility clustering in the return series,
    unlike iid permutation which destroys temporal structure and produces
    an unrealistic null distribution.

    Args:
        all_returns: DataFrame of per-asset returns (columns = assets).
        observed_t: The observed DK-t statistic to test against.
        n_shuffles: Number of bootstrap resamples.
        seed: Random seed for reproducibility.
        block_length: Mean block length for stationary bootstrap (10-20 for daily FX).

    Returns p-value: fraction of shuffles with dk_t >= observed.
    """
    rng = np.random.RandomState(seed)
    count = 0
    shuffled_ts = []
    p = 1.0 / block_length  # Probability of starting a new block

    for _ in range(n_shuffles):
        # Stationary bootstrap: preserves autocorrelation within each asset
        shuffled = pd.DataFrame(index=all_returns.index)
        for col in all_returns.columns:
            vals = all_returns[col].dropna().values.copy()
            n = len(vals)
            idx = rng.randint(0, n - 1)
            bootstrapped = []
            while len(bootstrapped) < n:
                bootstrapped.append(vals[idx])
                if rng.random() < p:
                    idx = rng.randint(0, n - 1)
                else:
                    idx = (idx + 1) % n
            shuffled[col] = pd.Series(bootstrapped[:n], index=all_returns[col].dropna().index)

        cs_mean = shuffled.mean(axis=1).dropna()
        if len(cs_mean) < 30:
            continue

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
        t_shuffled = mu / nw_se if nw_se > 0 else 0.0
        shuffled_ts.append(t_shuffled)
        if t_shuffled >= observed_t:
            count += 1

    p_value = count / n_shuffles if n_shuffles > 0 else 1.0
    return {
        "method": "stationary_bootstrap",
        "block_length": block_length,
        "n_shuffles": n_shuffles,
        "observed_dk_t": round(observed_t, 4),
        "mean_shuffled_t": round(float(np.mean(shuffled_ts)), 4) if shuffled_ts else 0.0,
        "p_value": round(p_value, 4),
        "verdict": "PASS" if p_value < 0.05 else "FAIL",
    }


# ---------------------------------------------------------------------------
# Main edge search
# ---------------------------------------------------------------------------


def run_edge_search(
    universe: list[str],
    cost_multiplier: float = 1.0,
    label_shuffle_n: int = 200,
    min_years: int = 8,
    block_length: int = 10,
) -> dict:
    """Run momentum factor rotation across universe with pooled DK-test."""

    # ------------------------------------------------------------------
    # 1. Load close prices for all assets
    # ------------------------------------------------------------------
    print(f"\nLoading data for {len(universe)} assets...")
    close_prices = pd.DataFrame()
    for sym in universe:
        try:
            df = load_asset_data(sym)
            ts = df["time"] if "time" in df.columns else df["date"]
            s = pd.Series(df["close"].values, index=pd.to_datetime(ts), name=sym)
            close_prices = pd.concat([close_prices, s], axis=1)
            print(f"  {sym}: {len(df)} bars ({df['time'].iloc[0].date()} → {df['time'].iloc[-1].date()})")
        except Exception as e:
            print(f"  {sym}: SKIP — {e}")

    if close_prices.empty or len(close_prices.columns) < 2:
        print("FATAL: need >= 2 assets with data")
        sys.exit(1)

    # Align on common dates
    close_prices = close_prices.dropna(how="all").ffill().dropna()
    print(f"  Aligned: {len(close_prices)} bars, {len(close_prices.columns)} assets")

    # ------------------------------------------------------------------
    # 2. Check data range / regime coverage
    # ------------------------------------------------------------------
    data_start = close_prices.index[0]
    data_end = close_prices.index[-1]
    years = (data_end - data_start).days / 365.25

    if years < min_years:
        print(f"WARNING: only {years:.1f} years of data (min_years={min_years})")

    regime_coverage = detect_regime_coverage(close_prices)
    print(f"  Data range: {data_start.date()} → {data_end.date()} ({years:.1f} years)")
    print(f"  Regime coverage: {regime_coverage}")

    # ------------------------------------------------------------------
    # 3. Run momentum factor rotation with FROZEN parameters
    # ------------------------------------------------------------------
    print("\nRunning momentum_factor_rotation (FROZEN params)...")
    config = MomentumFactorRotationConfig(
        lookbacks=(21, 63, 252),
        vol_target=0.10,
        top_n=2,
        bottom_n=0,
        rebalance_freq=5,
        min_signal_strength=0.3,
    )
    result = compute_momentum_factor_rotation(close_prices, config)
    signals = result.signal  # DataFrame: {asset: {-1, 0, +1}}

    print(f"  Signal shape: {signals.shape}")
    print(f"  Non-zero signals per asset:")
    for col in signals.columns:
        n_long = int((signals[col] == 1).sum())
        n_short = int((signals[col] == -1).sum())
        print(f"    {col}: long={n_long}  short={n_short}")

    # ------------------------------------------------------------------
    # 4. Run through verified BacktestEngine (not standalone pct_change)
    # ------------------------------------------------------------------
    print("\nRunning BacktestEngine for each asset...")
    print(f"  Cost multiplier: {cost_multiplier}x")

    all_returns = pd.DataFrame()
    per_asset: dict = {}
    total_trades = 0

    for sym in universe:
        if sym not in close_prices.columns or sym not in signals.columns:
            continue

        # Load raw OHLCV for engine
        df = load_asset_data_raw(sym)
        if df is None:
            continue
        ohlcv = {
            "open": df["open"].tolist(),
            "high": df["high"].tolist(),
            "low": df["low"].tolist(),
            "close": df["close"].tolist(),
            "volume": df["volume"].tolist() if "volume" in df.columns else [0.0] * len(df),
        }
        timestamps = [pd.Timestamp(t).to_pydatetime() for t in df.index]

        # Align signal to raw OHLCV dates: sort both, drop dups, ffill
        sig_s = signals[sym]
        if not isinstance(sig_s.index, pd.DatetimeIndex):
            sig_s.index = pd.to_datetime(sig_s.index)
        if not isinstance(df.index, pd.DatetimeIndex):
            raw_idx = pd.to_datetime(df.index)
        else:
            raw_idx = df.index
        sig_s = sig_s[~sig_s.index.duplicated(keep="first")].sort_index()
        raw_idx = raw_idx[~raw_idx.duplicated(keep="first")].sort_values()
        aligned = sig_s.reindex(raw_idx, method="ffill").fillna(0)
        sig_series = aligned.values

        # Determine ATR multiplier
        if sym in ("EURUSD", "GBPUSD", "USDJPY"):
            sl_mult = 2.0
        elif sym in ("XAUUSD", "XAGUSD"):
            sl_mult = 1.5
        else:
            sl_mult = 3.0

        # Create engine
        bt_config = BacktestConfig()
        bt_config.initial_capital = Decimal("100000")
        bt_config.spread_pips = float(SYMBOL_SPREAD_PIPS.get(sym, 2.0)) * cost_multiplier
        bt_config.commission_per_lot = Decimal(str(SYMBOL_COMMISSION.get(sym, 3.5)))
        bt_config.risk_per_trade_bps = 100
        bt_config.max_positions = 1
        bt_config.strict_mtf = False

        engine = BacktestEngine(bt_config)
        engine._symbol = sym
        adapter = _MomentumSignalAdapter(sym, sig_series, sl_mult)
        engine.set_strategy(adapter)
        engine.load_data(ohlcv, timestamps)
        engine._check_risk_halt = lambda: False
        engine._pnl_tracker = None

        try:
            results = engine.run()
        except Exception as e:
            print(f"  {sym}: ENGINE ERROR: {e}")
            per_asset[sym] = {"error": str(e)}
            continue

        # Extract daily returns from equity curve
        equity = getattr(engine, "equity_curve", []) or []
        n_trades = len(results.get("trades", []) or [])
        total_trades += n_trades

        if len(equity) >= 2:
            daily_ret = _extract_daily_returns(equity)
            all_returns[sym] = daily_ret
            metrics = compute_asset_metrics(daily_ret)
            max_dd = _calc_max_dd(equity)
        else:
            metrics = {"sharpe": 0.0, "return": 0.0, "max_dd": 0.0}
            max_dd = 0.0

        per_asset[sym] = {**metrics, "trades": n_trades, "max_dd": max_dd}
        print(
            f"  {sym}: trades={n_trades:>5}  sharpe={metrics['sharpe']:>+7.3f}  "
            f"ret={metrics['return']:>+8.4f}  max_dd={max_dd:>+8.4f}"
        )

    # ------------------------------------------------------------------
    # 5. Pooled DK-test
    # ------------------------------------------------------------------
    print("\n--- Pooled DK-test ---")
    dk = run_dk_test(all_returns, total_trades)
    print(f"  DK t-stat:        {dk['dk_t_stat']:.4f}")
    print(f"  Pooled Sharpe:    {dk['pooled_sharpe']:.4f}")
    print(f"  Pos Sharpe count: {dk['positive_sharpe_count']}/{dk['total_assets']}")
    print(f"  Verdict (DK):     {dk['verdict']}")

    # ------------------------------------------------------------------
    # 6. Label shuffle (noise-proof)
    # ------------------------------------------------------------------
    print(f"\n--- Label Shuffle ({label_shuffle_n} iterations) ---")
    shuffle_result = label_shuffle_test(
        all_returns, dk["dk_t_stat"], n_shuffles=label_shuffle_n, block_length=block_length,
    )
    print(f"  Observed DK-t:    {shuffle_result['observed_dk_t']:.4f}")
    print(f"  Mean shuffled t:  {shuffle_result['mean_shuffled_t']:.4f}")
    print(f"  P-value:          {shuffle_result['p_value']:.4f}")
    print(f"  Verdict (shuffle):{shuffle_result['verdict']}")

    # ------------------------------------------------------------------
    # 7. Combined verdict
    # ------------------------------------------------------------------
    dk_verdict = dk["verdict"]
    shuffle_pass = shuffle_result["verdict"] == "PASS"

    if dk_verdict == "GO" and shuffle_pass:
        combined = "GO"
    elif dk_verdict == "MARGINAL" or (dk_verdict == "GO" and not shuffle_pass):
        combined = "MARGINAL"
    else:
        combined = "REJECT"

    print(f"\n  ╔══════════════════════════════════════════╗")
    print(f"  ║  COMBINED VERDICT:  {combined:<20s} ║")
    print(f"  ╚══════════════════════════════════════════╝")

    # ------------------------------------------------------------------
    # 8. Build output
    # ------------------------------------------------------------------
    payload = {
        "trial_id": 2001,
        "strategy": "momentum_factor_rotation",
        "parameters": {
            "lookbacks": list(config.lookbacks),
            "vol_target": config.vol_target,
            "top_n": config.top_n,
            "bottom_n": config.bottom_n,
            "rebalance_freq": config.rebalance_freq,
            "min_signal_strength": config.min_signal_strength,
        },
        "universe": list(close_prices.columns),
        "cost_model": "pepperstone_razor",
        "cost_multiplier": cost_multiplier,
        "data_range": {
            "start": str(data_start.date()),
            "end": str(data_end.date()),
            "years": round(years, 2),
        },
        "regime_coverage": regime_coverage,
        "per_asset": per_asset,
        "pooled": {
            "dk_t": dk["dk_t_stat"],
            "pooled_sharpe": dk["pooled_sharpe"],
            "positive_sharpe_count": dk["positive_sharpe_count"],
            "total_trades": dk["total_trades"],
            "verdict": dk["verdict"],
        },
        "label_shuffle": {
            "n_shuffles": shuffle_result["n_shuffles"],
            "observed_sharpe": round(dk["pooled_sharpe"], 4),
            "p_value": shuffle_result["p_value"],
            "verdict": shuffle_result["verdict"],
        },
        # --- G4: Correlation-adjusted effective-N ---
        "effective_n": compute_effective_n(all_returns),
        # --- G8: Monte Carlo ruin analysis ---
        "monte_carlo_ruin": run_monte_carlo_ruin(
            trade_returns=all_returns.mean(axis=1).dropna().values,
            starting_balance=100_000.0,
            kill_threshold_dd=0.20,
            n_sims=1000,
            horizon_months=6,
        ),
        # --- G9: Lot-size feasibility (post-processing, requires backtest engine output) ---
        "lot_feasibility": {
            "status": "PENDING_BACKTEST_OUTPUT",
            "note": "Run check_lot_feasibility() with theoretical lot sizes from backtest engine. "
                    "Function ready in this module; needs per-symbol lot series from vol-targeting.",
        },
        "combined_verdict": combined,
        "honest_note": (
            "GO does not equal live-ready. Must still pass cost-stress "
            "(1.5x, 2.0x multiplier), jackknife robustness, and not burn "
            "sacred holdout until single pre-committed hypothesis."
        ),
        "timestamp": datetime.now(UTC).isoformat(),
    }

    return payload


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cross-sectional edge search: momentum_factor_rotation + pooled DK-test"
    )
    parser.add_argument(
        "--universe",
        type=str,
        default=",".join(CORE_UNIVERSE),
        help="Comma-separated asset symbols (default: 7-asset core universe)",
    )
    parser.add_argument(
        "--cost-model",
        type=str,
        default="pepperstone_razor",
        choices=["pepperstone_razor"],
        help="Cost model (only pepperstone_razor supported)",
    )
    parser.add_argument(
        "--cost-multiplier",
        type=float,
        default=1.0,
        help="Cost stress multiplier (1.0, 1.5, 2.0)",
    )
    parser.add_argument(
        "--dk-test",
        type=str,
        default="pooled",
        choices=["pooled"],
        help="DK-test type (only pooled supported)",
    )
    parser.add_argument(
        "--label-shuffle",
        type=int,
        default=200,
        help="Number of label-shuffle iterations (0 to skip)",
    )
    parser.add_argument(
        "--block-length",
        type=int,
        default=10,
        help="Mean block length for stationary bootstrap (10-20 for daily FX)",
    )
    parser.add_argument(
        "--min-years",
        type=int,
        default=8,
        help="Minimum years of data required for regime coverage",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(ROOT / "reports" / "edge_search_cross_sectional.json"),
        help="Output JSON path",
    )
    args = parser.parse_args()

    universe = [s.strip() for s in args.universe.split(",") if s.strip()]

    print(f"Cross-Sectional Edge Search — Phase 0A")
    print(f"{'=' * 60}")
    print(f"Strategy:       momentum_factor_rotation (FROZEN)")
    print(f"Universe:       {universe}")
    print(f"Cost model:     {args.cost_model}")
    print(f"Cost multiplier:{args.cost_multiplier}x")
    print(f"Label shuffle:  {args.label_shuffle} iterations (stationary bootstrap, block={args.block_length})")
    print(f"Min years:      {args.min_years}")
    print(f"GO rule:        dk_t>2.0 AND pos_sharpe>=5 AND shuffle_p<0.05")

    try:
        payload = run_edge_search(
            universe=universe,
            cost_multiplier=args.cost_multiplier,
            label_shuffle_n=args.label_shuffle,
            min_years=args.min_years,
            block_length=args.block_length,
        )
    except Exception as e:
        print(f"\nFATAL: {e}")
        traceback.print_exc()
        return 1

    # Write output
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"\nSaved: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
