#!/usr/bin/env python3
"""
Unified Walk-Forward Backtest Runner — 7 New Strategies.

Runs walk-forward validation for all 7 new research strategies and checks
the 7 validation gates required for live trading.

Usage:
    python scripts/run_new_strategies_wf.py
    python scripts/run_new_strategies_wf.py --strategy fomc_drift
    python scripts/run_new_strategies_wf.py --symbol XAUUSD --folds 5

Validation Gates (all must pass):
    1. p-value < 0.05
    2. WFA OOS win-rate >= 70%
    3. Walk-Forward Efficiency 0.5-1.5
    4. Deflated Sharpe > 95%
    5. PBO < 0.5
    6. Bootstrap CI excludes 0
    7. Min 100 trades (across all folds)
"""

import argparse
import json
import math
import sys
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# Fix Windows console encoding for Unicode output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr,attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr,attr-defined]

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ARTIFACTS_DIR = ROOT / "artifacts" / "new_strategies_wf"
REPORT_PATH = ROOT / "reports" / "new_strategies_validation.json"

from paper_engine.campaign import get_round_trip_cost_bps  # noqa: E402
from provenance import cost_calibrated_symbols, require_cost_calibrated  # noqa: E402

# ─── Strategy Registry ──────────────────────────────────────────────────

STRATEGIES = {}


def _setup_package():
    """Set up quant_os as an importable package for relative imports."""
    import types

    # Register 'quant_os' as a package in sys.modules
    if "quant_os" not in sys.modules:
        pkg = types.ModuleType("quant_os")
        pkg.__path__ = [str(ROOT)]
        pkg.__package__ = "quant_os"
        sys.modules["quant_os"] = pkg

    # Register sub-packages
    for sub in ["strategies", "core", "ml", "validation", "backtest", "risk", "execution"]:
        sub_path = ROOT / sub
        if sub_path.exists() and f"quant_os.{sub}" not in sys.modules:
            mod = types.ModuleType(f"quant_os.{sub}")
            mod.__path__ = [str(sub_path)]
            mod.__package__ = f"quant_os.{sub}"
            sys.modules[f"quant_os.{sub}"] = mod

    # Add root to sys.path
    parent = str(ROOT.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)


def _register_strategies():
    """Register all 7 new strategies with their signal functions and data requirements."""
    _setup_package()

    # Now import via the package
    from quant_os.strategies import cot_positioning as cot_mod
    from quant_os.strategies import fomc_drift as fomc_mod
    from quant_os.strategies import momentum_factor_rotation as rotation_mod
    from quant_os.strategies import orderflow_imbalance as orderflow_mod
    from quant_os.strategies import pgm_pairs as pgm_mod
    from quant_os.strategies import vol_regime_sizing as vol_regime_mod
    from quant_os.strategies import vol_risk_premium as vrp_mod

    STRATEGIES["fomc_drift"] = {
        "fn": fomc_mod.compute_fomc_drift_signals,
        "config_cls": fomc_mod.FOMCDriftConfig,
        "symbols": ["XAUUSD"],
        "timeframe": "D1",
        "type": "directional",
    }
    STRATEGIES["vol_regime_sizing"] = {
        "fn": vol_regime_mod.compute_vol_regime_sizing,
        "config_cls": vol_regime_mod.VolRegimeSizingConfig,
        "symbols": ["XAUUSD"],
        "timeframe": "D1",
        "type": "sizing",
    }
    STRATEGIES["orderflow_imbalance"] = {
        "fn": orderflow_mod.compute_orderflow_imbalance_signals,
        "config_cls": orderflow_mod.OrderflowImbalanceConfig,
        "symbols": ["XAUUSD"],
        "timeframe": "M15",
        "type": "directional",
    }
    STRATEGIES["momentum_factor_rotation"] = {
        "fn": rotation_mod.compute_momentum_factor_rotation,
        "config_cls": rotation_mod.MomentumFactorRotationConfig,
        "symbols": ["XAUUSD", "XAGUSD", "XPDUSD", "XPTUSD"],
        "timeframe": "D1",
        "type": "rotation",
    }
    STRATEGIES["vol_risk_premium"] = {
        "fn": vrp_mod.compute_vol_risk_premium_signals,
        "config_cls": vrp_mod.VolRiskPremiumConfig,
        "symbols": ["XAUUSD"],
        "timeframe": "D1",
        "type": "directional",
    }
    STRATEGIES["cot_positioning"] = {
        "fn": cot_mod.compute_cot_positioning_signals,
        "config_cls": cot_mod.COTPositioningConfig,
        "symbols": ["XAUUSD"],
        "timeframe": "W1",
        "type": "directional",
        "data_source": "cot",
    }
    STRATEGIES["pgm_pairs"] = {
        "fn": pgm_mod.compute_pgm_pairs_signals,
        "config_cls": pgm_mod.PGMPairsConfig,
        "symbols": ["XPTUSD", "XPDUSD"],
        "timeframe": "D1",
        "type": "pairs",
    }


# ─── Data Loading ───────────────────────────────────────────────────────


def load_csv(symbol: str, timeframe: str) -> pd.DataFrame:
    """Load OHLCV CSV data."""
    csv_path = ROOT / "data" / f"{symbol}_{timeframe}.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"Data not found: {csv_path}")

    df = pd.read_csv(csv_path)
    # Normalize column names
    col_map = {}
    for col in df.columns:
        lower = col.lower().strip()
        if "time" in lower or "date" in lower:
            col_map[col] = "timestamp"
        elif lower == "open":
            col_map[col] = "open"
        elif lower == "high":
            col_map[col] = "high"
        elif lower == "low":
            col_map[col] = "low"
        elif lower == "close":
            col_map[col] = "close"
        elif "vol" in lower:
            col_map[col] = "volume"
    df = df.rename(columns=col_map)

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.set_index("timestamp").sort_index()

    return df


def load_cot_weekly() -> tuple[pd.DatetimeIndex, pd.Series]:
    """Load COT data for COT Positioning strategy."""
    from quant_os.strategies.cot_positioning import load_cot_data

    cot_dir = ROOT / "data" / "cot"
    df = load_cot_data(cot_dir)
    if df.empty:
        raise FileNotFoundError("No COT data found in data/cot/")
    return df["date"], df["net_positioning"]


def load_gvz() -> pd.Series:
    """Load GVZ data for Vol Risk Premium strategy."""
    from quant_os.strategies.vol_risk_premium import load_gvz_data

    gvz = load_gvz_data(ROOT / "data" / "macro")
    if gvz.empty:
        raise FileNotFoundError("No GVZ data found in data/macro/")
    return gvz


# ─── Trade Simulation ───────────────────────────────────────────────────


@dataclass
class Trade:
    entry_idx: int
    exit_idx: int
    side: int  # 1=long, -1=short
    entry_price: float
    exit_price: float
    pnl_pct: float
    bars_held: int


def simulate_trades_from_signals(
    signal: pd.Series,
    close: pd.Series,
    cost_bps: float = 10.0,
) -> list[Trade]:
    """Simulate trades from a signal series.

    Signal: 1 = long, -1 = short, 0 = flat.
    Enters on signal change, exits on signal change or reversal.
    Cost applied per round-trip in basis points.
    """
    trades = []
    in_position = 0
    entry_idx = 0
    entry_price = 0.0

    signal_arr = signal.values
    close_arr = close.values

    for i in range(len(signal_arr)):
        s = int(signal_arr[i]) if not pd.isna(signal_arr[i]) else 0
        c = float(close_arr[i])

        if s != in_position:
            # Exit current position
            if in_position != 0:
                pnl = in_position * (c - entry_price) / entry_price
                pnl -= cost_bps / 10000  # round-trip cost
                trades.append(
                    Trade(
                        entry_idx=entry_idx,
                        exit_idx=i,
                        side=in_position,
                        entry_price=entry_price,
                        exit_price=c,
                        pnl_pct=pnl,
                        bars_held=i - entry_idx,
                    )
                )

            # Enter new position
            if s != 0:
                entry_idx = i
                entry_price = c

            in_position = s

    # Close any remaining position at end
    if in_position != 0 and len(close_arr) > 0:
        c = float(close_arr[-1])
        pnl = in_position * (c - entry_price) / entry_price
        pnl -= cost_bps / 10000
        trades.append(
            Trade(
                entry_idx=entry_idx,
                exit_idx=len(close_arr) - 1,
                side=in_position,
                entry_price=entry_price,
                exit_price=c,
                pnl_pct=pnl,
                bars_held=len(close_arr) - 1 - entry_idx,
            )
        )

    return trades


# ─── Walk-Forward Engine ────────────────────────────────────────────────


@dataclass
class FoldResult:
    fold_idx: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    is_trades: int
    oos_trades: int
    is_win_rate: float
    oos_win_rate: float
    is_sharpe: float
    oos_sharpe: float
    is_pnl_pct: float
    oos_pnl_pct: float
    is_max_dd: float
    oos_max_dd: float


@dataclass
class WFResult:
    strategy: str
    symbol: str
    timeframe: str
    n_folds: int
    total_trades: int
    oos_win_rate: float
    oos_sharpe: float
    oos_total_pnl_pct: float
    oos_max_dd: float
    is_sharpe: float
    wfe: float
    degradation: float
    folds: list[FoldResult]
    p_value: float
    deflated_sharpe: float
    pbo: float
    bootstrap_ci_lower: float
    bootstrap_ci_upper: float
    verdict: str
    gates: dict


def _sharpe(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    mean = np.mean(returns)
    std = np.std(returns, ddof=1)
    if std < 1e-10:
        return 0.0
    return (mean / std) * np.sqrt(252)


def _max_drawdown(equity: list[float]) -> float:
    if not equity:
        return 0.0
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
    return max_dd


def _bootstrap_ci(returns: list[float], n_boot: int = 1000, ci: float = 0.95, seed: int = 42) -> tuple[float, float]:
    """Bootstrap confidence interval for mean return."""
    if len(returns) < 5:
        return -1.0, 1.0
    rng = np.random.default_rng(seed)
    means = []
    arr = np.array(returns)
    for _ in range(n_boot):
        sample = rng.choice(arr, size=len(arr), replace=True)
        means.append(np.mean(sample))
    alpha = (1 - ci) / 2
    return float(np.percentile(means, alpha * 100)), float(np.percentile(means, (1 - alpha) * 100))


def _p_value_one_sample(returns: list[float]) -> float:
    """One-sample t-test p-value (two-tailed) for mean return != 0."""
    n = len(returns)
    if n < 3:
        return 1.0
    mean = np.mean(returns)
    std = np.std(returns, ddof=1)
    if std < 1e-10:
        return 1.0
    t_stat = mean / (std / np.sqrt(n))
    # Approximate p-value using normal distribution for large n
    from math import erf, sqrt

    p = 2 * (1 - 0.5 * (1 + erf(abs(t_stat) / sqrt(2))))
    return max(0.0, min(1.0, p))


def _deflated_sharpe(sharpe_obs: float, n_trials: int) -> float:
    """Simplified DSR: P(Sharpe > 0 | observed, n_trials)."""
    if n_trials <= 1:
        return max(0.0, min(1.0, 0.5 + sharpe_obs / 2))
    # Higher n_trials → more penalty
    penalty = math.log(max(n_trials, 1)) / 10
    adjusted = sharpe_obs - penalty
    # Convert to probability-like score
    return max(0.0, min(1.0, 0.5 + adjusted / 2))


def _pbo(is_sharpes: list[float], oos_sharpes: list[float]) -> float:
    """Probability of Backtest Overfitting (simplified).
    P(OOS Sharpe < 0 | IS Sharpe was best)."""
    if not is_sharpes or not oos_sharpes:
        return 0.5
    # Count folds where OOS is negative despite positive IS
    count = 0
    total = 0
    for is_s, oos_s in zip(is_sharpes, oos_sharpes, strict=False):
        if is_s > 0:
            total += 1
            if oos_s < 0:
                count += 1
    return count / total if total > 0 else 0.5


def run_walk_forward(
    strategy_name: str,
    signal_fn,
    config,
    close: pd.Series,
    gvz: pd.Series | None = None,
    high: pd.Series | None = None,
    low: pd.Series | None = None,
    open_: pd.Series | None = None,
    n_folds: int = 5,
    train_ratio: float = 0.7,
    cost_bps: float = 10.0,
) -> WFResult:
    """Run walk-forward validation for a directional strategy."""
    strat_info = STRATEGIES[strategy_name]
    symbol = strat_info["symbols"][0]
    timeframe = strat_info["timeframe"]

    # Generate signal on full dataset
    kwargs = {"config": config}
    if strategy_name == "fomc_drift":
        result = signal_fn(close, high, low, **kwargs)
        sig = result.signal
    elif strategy_name == "vol_risk_premium":
        result = signal_fn(close, gvz, **kwargs)
        sig = result.signal
    elif strategy_name == "orderflow_imbalance":
        result = signal_fn(open_, high, low, close, **kwargs)
        sig = result.signal
    elif strategy_name == "vol_regime_sizing":
        result = signal_fn(close, high, low, **kwargs)
        # Sizing strategy: convert to directional signal based on vol regime
        # Low vol → trend-follow recent direction, High vol → flat
        returns = close.pct_change()
        recent = returns.rolling(5).mean()
        sig = pd.Series(0, index=close.index)
        sig[result.size_multiplier > 1.0] = np.sign(recent[result.size_multiplier > 1.0])
        sig[result.size_multiplier < 0.8] = 0  # defensive
    else:
        raise ValueError(f"Unknown strategy: {strategy_name}")

    # Walk-forward split
    n = len(sig)
    fold_size = n // n_folds
    folds = []
    all_oos_returns = []
    all_is_returns = []

    for f in range(n_folds):
        test_start = f * fold_size
        test_end = min((f + 1) * fold_size, n)
        train_start = max(0, test_start - int(fold_size * train_ratio / (1 - train_ratio)))
        train_end = test_start

        if train_end - train_start < 20 or test_end - test_start < 10:
            continue

        # IS trades
        is_sig = sig.iloc[train_start:train_end]
        is_close = close.iloc[train_start:train_end]
        is_trades = simulate_trades_from_signals(is_sig, is_close, cost_bps)

        # OOS trades
        oos_sig = sig.iloc[test_start:test_end]
        oos_close = close.iloc[test_start:test_end]
        oos_trades = simulate_trades_from_signals(oos_sig, oos_close, cost_bps)

        is_returns = [t.pnl_pct for t in is_trades]
        oos_returns = [t.pnl_pct for t in oos_trades]
        all_is_returns.extend(is_returns)
        all_oos_returns.extend(oos_returns)

        is_equity = np.cumsum(is_returns).tolist()
        oos_equity = np.cumsum(oos_returns).tolist()

        folds.append(
            FoldResult(
                fold_idx=f,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                is_trades=len(is_trades),
                oos_trades=len(oos_trades),
                is_win_rate=sum(1 for t in is_trades if t.pnl_pct > 0) / max(len(is_trades), 1),
                oos_win_rate=sum(1 for t in oos_trades if t.pnl_pct > 0) / max(len(oos_trades), 1),
                is_sharpe=_sharpe(is_returns),
                oos_sharpe=_sharpe(oos_returns),
                is_pnl_pct=sum(is_returns),
                oos_pnl_pct=sum(oos_returns),
                is_max_dd=_max_drawdown(is_equity),
                oos_max_dd=_max_drawdown(oos_equity),
            )
        )

    if not folds:
        return WFResult(
            strategy=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            n_folds=0,
            total_trades=0,
            oos_win_rate=0,
            oos_sharpe=0,
            oos_total_pnl_pct=0,
            oos_max_dd=0,
            is_sharpe=0,
            wfe=0,
            degradation=1.0,
            folds=[],
            p_value=1.0,
            deflated_sharpe=0,
            pbo=1.0,
            bootstrap_ci_lower=-1,
            bootstrap_ci_upper=-1,
            verdict="INSUFFICIENT_SAMPLE",
            gates={},
        )

    # Aggregate metrics
    oos_sharpes = [f.oos_sharpe for f in folds]
    is_sharpes = [f.is_sharpe for f in folds]
    total_oos_trades = sum(f.oos_trades for f in folds)
    avg_oos_wr = float(np.mean([f.oos_win_rate for f in folds]))
    avg_oos_sharpe = float(np.mean(oos_sharpes))
    avg_is_sharpe = float(np.mean(is_sharpes))
    total_oos_pnl = sum(f.oos_pnl_pct for f in folds)
    max_oos_dd = max(f.oos_max_dd for f in folds)

    # WFE = OOS Sharpe / IS Sharpe
    wfe = avg_oos_sharpe / avg_is_sharpe if abs(avg_is_sharpe) > 1e-6 else 0.0

    # Degradation
    degradation = 1 - (avg_oos_sharpe / avg_is_sharpe) if abs(avg_is_sharpe) > 1e-6 else 1.0

    # Statistical tests
    p_value = _p_value_one_sample(all_oos_returns)
    dsr = _deflated_sharpe(avg_oos_sharpe, n_trials=7)  # 7 strategies tested
    pbo = _pbo(is_sharpes, oos_sharpes)
    ci_lower, ci_upper = _bootstrap_ci(all_oos_returns)

    # ─── 7 Validation Gates ─────────────────────────────────────────
    gates = {
        "1_pvalue": p_value < 0.05,
        "2_oos_winrate": avg_oos_wr >= 0.70,
        "3_wfe": 0.5 <= wfe <= 1.5,
        "4_deflated_sharpe": dsr > 0.95,
        "5_pbo": pbo < 0.5,
        "6_bootstrap_ci": ci_lower > 0,
        "7_min_trades": total_oos_trades >= 100,
    }
    gates_passed = sum(gates.values())
    total_gates = len(gates)

    # Verdict
    if gates_passed == total_gates:
        verdict = "PASS_TO_NEXT_PHASE"
    elif gates_passed >= 5 and gates["7_min_trades"]:
        verdict = "CONDITIONAL_PASS"
    elif gates["1_pvalue"] and total_oos_pnl < 0:
        verdict = "NEGATIVE_EDGE_CONFIRMED"
    elif total_oos_trades < 50:
        verdict = "INSUFFICIENT_SAMPLE"
    else:
        verdict = "ARCHIVE_NO_EDGE"

    return WFResult(
        strategy=strategy_name,
        symbol=symbol,
        timeframe=timeframe,
        n_folds=len(folds),
        total_trades=total_oos_trades,
        oos_win_rate=round(avg_oos_wr, 4),
        oos_sharpe=round(avg_oos_sharpe, 4),
        oos_total_pnl_pct=round(total_oos_pnl, 6),
        oos_max_dd=round(max_oos_dd, 4),
        is_sharpe=round(avg_is_sharpe, 4),
        wfe=round(wfe, 4),
        degradation=round(degradation, 4),
        folds=folds,
        p_value=round(p_value, 6),
        deflated_sharpe=round(dsr, 4),
        pbo=round(pbo, 4),
        bootstrap_ci_lower=round(ci_lower, 6),
        bootstrap_ci_upper=round(ci_upper, 6),
        verdict=verdict,
        gates=gates,
    )


def run_pairs_strategy(
    strategy_name: str,
    close_a: pd.Series,
    high_a: pd.Series,
    low_a: pd.Series,
    close_b: pd.Series,
    high_b: pd.Series,
    low_b: pd.Series,
    config,
    n_folds: int = 5,
    cost_bps: float = 15.0,
) -> WFResult:
    """Run walk-forward for pairs strategy (PGM Pairs)."""
    from quant_os.strategies.pgm_pairs import compute_pgm_pairs_signals

    result = compute_pgm_pairs_signals(close_a, high_a, low_a, close_b, high_b, low_b, config=config)
    sig = result.signal
    close = close_a  # Use first leg for P&L

    strat_info = STRATEGIES[strategy_name]
    symbol = f"{strat_info['symbols'][0]}/{strat_info['symbols'][1]}"

    # Same walk-forward logic as directional
    n = len(sig)
    fold_size = n // n_folds
    folds = []
    all_oos_returns = []
    all_is_returns = []

    for f in range(n_folds):
        test_start = f * fold_size
        test_end = min((f + 1) * fold_size, n)
        train_start = max(0, test_start - int(fold_size * 0.7 / 0.3))
        train_end = test_start

        if train_end - train_start < 20 or test_end - test_start < 10:
            continue

        is_sig = sig.iloc[train_start:train_end]
        is_close = close.iloc[train_start:train_end]
        is_trades = simulate_trades_from_signals(is_sig, is_close, cost_bps)

        oos_sig = sig.iloc[test_start:test_end]
        oos_close = close.iloc[test_start:test_end]
        oos_trades = simulate_trades_from_signals(oos_sig, oos_close, cost_bps)

        is_returns = [t.pnl_pct for t in is_trades]
        oos_returns = [t.pnl_pct for t in oos_trades]
        all_is_returns.extend(is_returns)
        all_oos_returns.extend(oos_returns)

        is_equity = np.cumsum(is_returns).tolist()
        oos_equity = np.cumsum(oos_returns).tolist()

        folds.append(
            FoldResult(
                fold_idx=f,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                is_trades=len(is_trades),
                oos_trades=len(oos_trades),
                is_win_rate=sum(1 for t in is_trades if t.pnl_pct > 0) / max(len(is_trades), 1),
                oos_win_rate=sum(1 for t in oos_trades if t.pnl_pct > 0) / max(len(oos_trades), 1),
                is_sharpe=_sharpe(is_returns),
                oos_sharpe=_sharpe(oos_returns),
                is_pnl_pct=sum(is_returns),
                oos_pnl_pct=sum(oos_returns),
                is_max_dd=_max_drawdown(is_equity),
                oos_max_dd=_max_drawdown(oos_equity),
            )
        )

    if not folds:
        return WFResult(
            strategy=strategy_name,
            symbol=symbol,
            timeframe="D1",
            n_folds=0,
            total_trades=0,
            oos_win_rate=0,
            oos_sharpe=0,
            oos_total_pnl_pct=0,
            oos_max_dd=0,
            is_sharpe=0,
            wfe=0,
            degradation=1.0,
            folds=[],
            p_value=1.0,
            deflated_sharpe=0,
            pbo=1.0,
            bootstrap_ci_lower=-1,
            bootstrap_ci_upper=-1,
            verdict="INSUFFICIENT_SAMPLE",
            gates={},
        )

    oos_sharpes = [f.oos_sharpe for f in folds]
    is_sharpes = [f.is_sharpe for f in folds]
    total_oos_trades = sum(f.oos_trades for f in folds)
    avg_oos_wr = float(np.mean([f.oos_win_rate for f in folds]))
    avg_oos_sharpe = float(np.mean(oos_sharpes))
    avg_is_sharpe = float(np.mean(is_sharpes))
    total_oos_pnl = sum(f.oos_pnl_pct for f in folds)
    max_oos_dd = max(f.oos_max_dd for f in folds)
    wfe = avg_oos_sharpe / avg_is_sharpe if abs(avg_is_sharpe) > 1e-6 else 0.0
    degradation = 1 - (avg_oos_sharpe / avg_is_sharpe) if abs(avg_is_sharpe) > 1e-6 else 1.0
    p_value = _p_value_one_sample(all_oos_returns)
    dsr = _deflated_sharpe(avg_oos_sharpe, n_trials=7)
    pbo_val = _pbo(is_sharpes, oos_sharpes)
    ci_lower, ci_upper = _bootstrap_ci(all_oos_returns)

    gates = {
        "1_pvalue": p_value < 0.05,
        "2_oos_winrate": avg_oos_wr >= 0.70,
        "3_wfe": 0.5 <= wfe <= 1.5,
        "4_deflated_sharpe": dsr > 0.95,
        "5_pbo": pbo_val < 0.5,
        "6_bootstrap_ci": ci_lower > 0,
        "7_min_trades": total_oos_trades >= 100,
    }
    gates_passed = sum(gates.values())

    if gates_passed == 7:
        verdict = "PASS_TO_NEXT_PHASE"
    elif gates_passed >= 5 and gates["7_min_trades"]:
        verdict = "CONDITIONAL_PASS"
    elif p_value < 0.05 and total_oos_pnl < 0:
        verdict = "NEGATIVE_EDGE_CONFIRMED"
    elif total_oos_trades < 50:
        verdict = "INSUFFICIENT_SAMPLE"
    else:
        verdict = "ARCHIVE_NO_EDGE"

    return WFResult(
        strategy=strategy_name,
        symbol=symbol,
        timeframe="D1",
        n_folds=len(folds),
        total_trades=total_oos_trades,
        oos_win_rate=round(avg_oos_wr, 4),
        oos_sharpe=round(avg_oos_sharpe, 4),
        oos_total_pnl_pct=round(total_oos_pnl, 6),
        oos_max_dd=round(max_oos_dd, 4),
        is_sharpe=round(avg_is_sharpe, 4),
        wfe=round(wfe, 4),
        degradation=round(degradation, 4),
        folds=folds,
        p_value=round(p_value, 6),
        deflated_sharpe=round(dsr, 4),
        pbo=round(pbo_val, 4),
        bootstrap_ci_lower=round(ci_lower, 6),
        bootstrap_ci_upper=round(ci_upper, 6),
        verdict=verdict,
        gates=gates,
    )


def run_cot_strategy(n_folds: int = 3, cost_bps: float = 10.0) -> WFResult:
    """Run walk-forward for COT Positioning (weekly data)."""
    from quant_os.strategies.cot_positioning import COTPositioningConfig, compute_cot_positioning_signals

    dates, net_pos = load_cot_weekly()
    config = COTPositioningConfig()
    result = compute_cot_positioning_signals(dates, net_pos, config)
    sig = result.signal

    # Use net_positioning as proxy for "price" (directional P&L)
    n = len(sig)
    fold_size = max(n // n_folds, 10)
    all_oos_returns = []
    all_is_returns = []

    for f in range(n_folds):
        test_start = f * fold_size
        test_end = min((f + 1) * fold_size, n)
        train_start = max(0, test_start - int(fold_size * 0.7 / 0.3))
        train_end = test_start

        if train_end - train_start < 10 or test_end - test_start < 5:
            continue

        # Simulate returns from signal * next-period change in net_positioning
        for phase, start, end in [("IS", train_start, train_end), ("OOS", test_start, test_end)]:
            returns = []
            for i in range(start + 1, end):
                s = sig.iloc[i - 1] if not pd.isna(sig.iloc[i - 1]) else 0
                if s != 0:
                    # Normalize return
                    np_val = net_pos.iloc[i]
                    np_prev = net_pos.iloc[i - 1]
                    if abs(np_prev) > 0:
                        ret = s * (np_val - np_prev) / abs(np_prev) - cost_bps / 10000
                        returns.append(ret)

            if phase == "IS":
                all_is_returns.extend(returns)
            else:
                all_oos_returns.extend(returns)

    if not all_oos_returns:
        return WFResult(
            strategy="cot_positioning",
            symbol="XAUUSD",
            timeframe="W1",
            n_folds=0,
            total_trades=0,
            oos_win_rate=0,
            oos_sharpe=0,
            oos_total_pnl_pct=0,
            oos_max_dd=0,
            is_sharpe=0,
            wfe=0,
            degradation=1.0,
            folds=[],
            p_value=1.0,
            deflated_sharpe=0,
            pbo=1.0,
            bootstrap_ci_lower=-1,
            bootstrap_ci_upper=-1,
            verdict="INSUFFICIENT_SAMPLE",
            gates={},
        )

    avg_oos_sharpe = _sharpe(all_oos_returns)
    avg_is_sharpe = _sharpe(all_is_returns)
    total_trades = len(all_oos_returns)
    avg_oos_wr = sum(1 for r in all_oos_returns if r > 0) / max(total_trades, 1)
    wfe = avg_oos_sharpe / avg_is_sharpe if abs(avg_is_sharpe) > 1e-6 else 0.0
    degradation = 1 - (avg_oos_sharpe / avg_is_sharpe) if abs(avg_is_sharpe) > 1e-6 else 1.0
    p_value = _p_value_one_sample(all_oos_returns)
    dsr = _deflated_sharpe(avg_oos_sharpe, n_trials=7)
    ci_lower, ci_upper = _bootstrap_ci(all_oos_returns)

    gates = {
        "1_pvalue": p_value < 0.05,
        "2_oos_winrate": avg_oos_wr >= 0.70,
        "3_wfe": 0.5 <= wfe <= 1.5,
        "4_deflated_sharpe": dsr > 0.95,
        "5_pbo": False,  # Not enough folds for PBO
        "6_bootstrap_ci": ci_lower > 0,
        "7_min_trades": total_trades >= 100,
    }
    gates_passed = sum(gates.values())

    if gates_passed == 7:
        verdict = "PASS_TO_NEXT_PHASE"
    elif gates_passed >= 5:
        verdict = "CONDITIONAL_PASS"
    elif total_trades < 50:
        verdict = "INSUFFICIENT_SAMPLE"
    else:
        verdict = "ARCHIVE_NO_EDGE"

    return WFResult(
        strategy="cot_positioning",
        symbol="XAUUSD",
        timeframe="W1",
        n_folds=3,
        total_trades=total_trades,
        oos_win_rate=round(avg_oos_wr, 4),
        oos_sharpe=round(avg_oos_sharpe, 4),
        oos_total_pnl_pct=round(sum(all_oos_returns), 6),
        oos_max_dd=0,
        is_sharpe=round(avg_is_sharpe, 4),
        wfe=round(wfe, 4),
        degradation=round(degradation, 4),
        folds=[],
        p_value=round(p_value, 6),
        deflated_sharpe=round(dsr, 4),
        pbo=0.5,
        bootstrap_ci_lower=round(ci_lower, 6),
        bootstrap_ci_upper=round(ci_upper, 6),
        verdict=verdict,
        gates=gates,
    )


def run_rotation_strategy(n_folds: int = 5, cost_bps: float = 10.0) -> WFResult:
    """Run walk-forward for Momentum Factor Rotation (multi-asset)."""
    from quant_os.strategies.momentum_factor_rotation import (
        MomentumFactorRotationConfig,
        compute_momentum_factor_rotation,
    )

    symbols = ["XAUUSD", "XAGUSD", "XPDUSD", "XPTUSD"]
    prices = {}
    for sym in symbols:
        try:
            df = load_csv(sym, "D1")
            prices[sym] = df["close"]
        except FileNotFoundError:
            continue

    if len(prices) < 2:
        return WFResult(
            strategy="momentum_factor_rotation",
            symbol="MULTI",
            timeframe="D1",
            n_folds=0,
            total_trades=0,
            oos_win_rate=0,
            oos_sharpe=0,
            oos_total_pnl_pct=0,
            oos_max_dd=0,
            is_sharpe=0,
            wfe=0,
            degradation=1.0,
            folds=[],
            p_value=1.0,
            deflated_sharpe=0,
            pbo=1.0,
            bootstrap_ci_lower=-1,
            bootstrap_ci_upper=-1,
            verdict="INSUFFICIENT_SAMPLE",
            gates={},
        )

    prices_df = pd.DataFrame(prices).dropna()
    config = MomentumFactorRotationConfig()
    result = compute_momentum_factor_rotation(prices_df, config)

    # Simulate P&L from rotation signals
    # Equal-weight portfolio of signaled assets
    returns_df = prices_df.pct_change()
    portfolio_returns = []
    for i in range(1, len(prices_df)):
        bar_ret = 0.0
        count = 0
        for col in prices_df.columns:
            s = result.signal.iloc[i - 1][col] if not pd.isna(result.signal.iloc[i - 1][col]) else 0
            if s != 0:
                r = returns_df.iloc[i][col]
                if not pd.isna(r):
                    bar_ret += s * r
                    count += 1
        if count > 0:
            bar_ret /= count
            bar_ret -= cost_bps / 10000
        portfolio_returns.append(bar_ret)

    # Walk-forward
    n = len(portfolio_returns)
    fold_size = n // n_folds
    all_oos = []
    all_is = []

    for f in range(n_folds):
        test_start = f * fold_size
        test_end = min((f + 1) * fold_size, n)
        train_start = max(0, test_start - int(fold_size * 0.7 / 0.3))
        train_end = test_start

        if train_end - train_start < 20 or test_end - test_start < 10:
            continue

        is_ret = portfolio_returns[train_start:train_end]
        oos_ret = portfolio_returns[test_start:test_end]
        all_is.extend(is_ret)
        all_oos.extend(oos_ret)

    if not all_oos:
        return WFResult(
            strategy="momentum_factor_rotation",
            symbol="MULTI",
            timeframe="D1",
            n_folds=0,
            total_trades=0,
            oos_win_rate=0,
            oos_sharpe=0,
            oos_total_pnl_pct=0,
            oos_max_dd=0,
            is_sharpe=0,
            wfe=0,
            degradation=1.0,
            folds=[],
            p_value=1.0,
            deflated_sharpe=0,
            pbo=1.0,
            bootstrap_ci_lower=-1,
            bootstrap_ci_upper=-1,
            verdict="INSUFFICIENT_SAMPLE",
            gates={},
        )

    avg_oos_sharpe = _sharpe(all_oos)
    avg_is_sharpe = _sharpe(all_is)
    avg_oos_wr = sum(1 for r in all_oos if r > 0) / max(len(all_oos), 1)
    wfe = avg_oos_sharpe / avg_is_sharpe if abs(avg_is_sharpe) > 1e-6 else 0.0
    degradation = 1 - (avg_oos_sharpe / avg_is_sharpe) if abs(avg_is_sharpe) > 1e-6 else 1.0
    p_value = _p_value_one_sample(all_oos)
    dsr = _deflated_sharpe(avg_oos_sharpe, n_trials=7)
    ci_lower, ci_upper = _bootstrap_ci(all_oos)

    gates = {
        "1_pvalue": p_value < 0.05,
        "2_oos_winrate": avg_oos_wr >= 0.70,
        "3_wfe": 0.5 <= wfe <= 1.5,
        "4_deflated_sharpe": dsr > 0.95,
        "5_pbo": False,
        "6_bootstrap_ci": ci_lower > 0,
        "7_min_trades": len(all_oos) >= 100,
    }
    gates_passed = sum(gates.values())

    if gates_passed == 7:
        verdict = "PASS_TO_NEXT_PHASE"
    elif gates_passed >= 5:
        verdict = "CONDITIONAL_PASS"
    elif len(all_oos) < 50:
        verdict = "INSUFFICIENT_SAMPLE"
    else:
        verdict = "ARCHIVE_NO_EDGE"

    return WFResult(
        strategy="momentum_factor_rotation",
        symbol="MULTI",
        timeframe="D1",
        n_folds=n_folds,
        total_trades=len(all_oos),
        oos_win_rate=round(avg_oos_wr, 4),
        oos_sharpe=round(avg_oos_sharpe, 4),
        oos_total_pnl_pct=round(sum(all_oos), 6),
        oos_max_dd=0,
        is_sharpe=round(avg_is_sharpe, 4),
        wfe=round(wfe, 4),
        degradation=round(degradation, 4),
        folds=[],
        p_value=round(p_value, 6),
        deflated_sharpe=round(dsr, 4),
        pbo=0.5,
        bootstrap_ci_lower=round(ci_lower, 6),
        bootstrap_ci_upper=round(ci_upper, 6),
        verdict=verdict,
        gates=gates,
    )


# ─── Main ───────────────────────────────────────────────────────────────


def print_result(result: WFResult):
    """Print formatted result to console."""
    status_emoji = {
        "PASS_TO_NEXT_PHASE": "✅",
        "CONDITIONAL_PASS": "⚠️",
        "NEGATIVE_EDGE_CONFIRMED": "❌",
        "INSUFFICIENT_SAMPLE": "📊",
        "ARCHIVE_NO_EDGE": "🗑️",
    }
    emoji = status_emoji.get(result.verdict, "❓")

    print(f"\n{'=' * 60}")
    print(f"  {emoji} {result.strategy.upper()} — {result.symbol} ({result.timeframe})")
    print(f"{'=' * 60}")
    print(f"  Verdict:         {result.verdict}")
    print(f"  OOS Sharpe:      {result.oos_sharpe:.4f}")
    print(f"  OOS Win Rate:    {result.oos_win_rate:.1%}")
    print(f"  OOS Total PnL:   {result.oos_total_pnl_pct:.4%}")
    print(f"  OOS Max DD:      {result.oos_max_dd:.2%}")
    print(f"  IS Sharpe:       {result.is_sharpe:.4f}")
    print(f"  WFE:             {result.wfe:.4f}")
    print(f"  Degradation:     {result.degradation:.2%}")
    print(f"  Total Trades:    {result.total_trades}")
    print(f"  p-value:         {result.p_value:.6f}")
    print(f"  Deflated Sharpe: {result.deflated_sharpe:.4f}")
    print(f"  PBO:             {result.pbo:.4f}")
    print(f"  Bootstrap 95%CI: [{result.bootstrap_ci_lower:.6f}, {result.bootstrap_ci_upper:.6f}]")
    print("\n  Validation Gates:")
    for gate, passed in result.gates.items():
        status = "✅" if passed else "❌"
        print(f"    {status} {gate}")
    print(f"  Passed: {sum(result.gates.values())}/{len(result.gates)}")


def main():
    parser = argparse.ArgumentParser(description="Run walk-forward validation for new strategies")
    parser.add_argument("--strategy", type=str, help="Run specific strategy only")
    parser.add_argument("--folds", type=int, default=5, help="Number of walk-forward folds")
    parser.add_argument(
        "--cost-bps",
        type=float,
        default=None,
        help="Round-trip cost in bps. If omitted, uses the real measured "
        "XAUUSD spread for calibrated strategies and skips strategies whose "
        "symbol(s) have no verified cost data (see cost_calibrated_symbols()) "
        "instead of silently defaulting to a flat guess -- that guess is "
        "exactly the fabrication trial #1030 was invalidated for.",
    )
    args = parser.parse_args()

    _register_strategies()
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  NEW STRATEGIES WALK-FORWARD VALIDATION")
    print(f"  {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    results = []
    strategies_to_run = [args.strategy] if args.strategy else list(STRATEGIES.keys())

    for name in strategies_to_run:
        if name not in STRATEGIES:
            print(f"\n❌ Unknown strategy: {name}")
            continue

        info = STRATEGIES[name]
        print(f"\n> Running {name} ({info['type']})...")

        if args.cost_bps is not None:
            cost_bps = args.cost_bps  # explicit user override, honored as-is
        elif all(s in cost_calibrated_symbols(mode="paper") for s in info["symbols"]):
            require_cost_calibrated(info["symbols"][0], mode="paper")
            cost_bps = get_round_trip_cost_bps(info["symbols"][0])
        else:
            print(
                f"  SKIPPED: {info['symbols']} not fully cost-calibrated "
                f"({sorted(cost_calibrated_symbols(mode='paper'))}). Pass --cost-bps to "
                f"override with an explicit assumed value."
            )
            continue

        try:
            if name == "pgm_pairs":
                df_a = load_csv("XPTUSD", "D1")
                df_b = load_csv("XPDUSD", "D1")
                # Align
                common_idx = df_a.index.intersection(df_b.index)
                df_a = df_a.loc[common_idx]
                df_b = df_b.loc[common_idx]
                result = run_pairs_strategy(
                    name,
                    df_a["close"],
                    df_a["high"],
                    df_a["low"],
                    df_b["close"],
                    df_b["high"],
                    df_b["low"],
                    info["config_cls"](),
                    n_folds=args.folds,
                    cost_bps=cost_bps,
                )
            elif name == "cot_positioning":
                result = run_cot_strategy(n_folds=3, cost_bps=cost_bps)
            elif name == "momentum_factor_rotation":
                result = run_rotation_strategy(n_folds=args.folds, cost_bps=cost_bps)
            else:
                df = load_csv(info["symbols"][0], info["timeframe"])
                # VRP needs GVZ data
                if name == "vol_risk_premium":
                    try:
                        gvz = load_gvz()
                    except FileNotFoundError:
                        gvz = None
                    result = run_walk_forward(
                        name,
                        info["fn"],
                        info["config_cls"](),
                        df["close"],
                        gvz,
                        n_folds=args.folds,
                        cost_bps=cost_bps,
                    )
                else:
                    result = run_walk_forward(
                        name,
                        info["fn"],
                        info["config_cls"](),
                        df["close"],
                        df.get("high"),
                        df.get("low"),
                        df.get("open"),
                        n_folds=args.folds,
                        cost_bps=cost_bps,
                    )

            results.append(result)
            print_result(result)

        except Exception as e:
            print(f"  ❌ Error: {e}")
            import traceback

            traceback.print_exc()

    # Summary
    print(f"\n{'=' * 60}")
    print("  SUMMARY")
    print(f"{'=' * 60}")

    passed = [r for r in results if r.verdict == "PASS_TO_NEXT_PHASE"]
    conditional = [r for r in results if r.verdict == "CONDITIONAL_PASS"]
    failed = [r for r in results if r.verdict not in ("PASS_TO_NEXT_PHASE", "CONDITIONAL_PASS")]

    print(f"  ✅ PASS:           {len(passed)} — {', '.join(r.strategy for r in passed) or 'none'}")
    print(f"  ⚠️  CONDITIONAL:    {len(conditional)} — {', '.join(r.strategy for r in conditional) or 'none'}")
    print(f"  ❌ FAIL/ARCHIVE:   {len(failed)} — {', '.join(r.strategy for r in failed) or 'none'}")

    # Save report
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        # cost_bps is now resolved per-strategy (real spread or explicit
        # override) rather than one global value; None here means every
        # strategy used its own real measured cost, not a flat guess.
        "cost_bps_override": args.cost_bps,
        "results": [],
    }
    for r in results:
        report["results"].append(
            {
                "strategy": r.strategy,
                "symbol": r.symbol,
                "timeframe": r.timeframe,
                "verdict": r.verdict,
                "oos_sharpe": r.oos_sharpe,
                "oos_win_rate": r.oos_win_rate,
                "total_trades": r.total_trades,
                "p_value": r.p_value,
                "wfe": r.wfe,
                "gates_passed": sum(r.gates.values()),
                "gates_total": len(r.gates),
                "gates": r.gates,
            }
        )

    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  Report saved: {REPORT_PATH}")

    # Determine overall verdict
    if passed:
        print(f"\n  🎯 PROCEED TO PAPER TRADING with: {', '.join(r.strategy for r in passed)}")
    elif conditional:
        print(f"\n  ⚠️  CONDITIONAL — proceed with caution: {', '.join(r.strategy for r in conditional)}")
    else:
        print("\n  🛑 NO STRATEGIES PASSED — do not proceed to live trading")


if __name__ == "__main__":
    main()
