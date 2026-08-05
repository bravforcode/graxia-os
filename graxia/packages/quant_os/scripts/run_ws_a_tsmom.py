#!/usr/bin/env python3
"""WS-A TSMOM Harness — MOP-2012 Replication (Trial 1028).

Pure time-series momentum per Moskowitz, Ooi, Pedersen (2012).
Single lookback (252 days), vol-target sizing, common rebalance every 21 days.

This harness does NOT use BacktestEngine (incompatible: SL-mandate, 50-bar
force-close, single-symbol). It reuses cost model components only.

Pre-registration: research/pre_registration/trial_1028_ws_a_tsmom_mop2012.md
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# Add parent dir AND scripts dir to path for imports
_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# Import the verified DK test from edge_search_all (Newey-West HAC, Bartlett kernel, T^(1/3) bandwidth)
from edge_search_all import run_dk_test as _verified_dk_test  # noqa: E402

from provenance import load_provenance_checked  # noqa: E402

# ---------------------------------------------------------------------------
# Constants (FROZEN per pre-registration §3)
# ---------------------------------------------------------------------------
LOOKBACK = 252  # 12-month momentum
REBALANCE_FREQ = 21  # Monthly rebalance (D1 bars)
VOL_TARGET = 0.10  # Annualized vol target
VOL_CLIP_UPPER = 2.0  # Cap vol_scale
VOL_CLIP_LOWER = 0.01  # Floor for realized vol
UNIVERSE = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "US30"]

# Cost calibration (from config/cost_calibration.json)
_COST_CALIBRATION = {
    "XAUUSD": {"spread_bps": 0.32, "commission_bps": 0, "tick_size": 0.01},
    "XAGUSD": {"spread_bps": 0.50, "commission_bps": 0, "tick_size": 0.01},
    "EURUSD": {"spread_bps": 0.10, "commission_bps": 7, "tick_size": 0.0001},
    "GBPUSD": {"spread_bps": 0.12, "commission_bps": 7, "tick_size": 0.0001},
    "USDJPY": {"spread_bps": 0.12, "commission_bps": 7, "tick_size": 0.001},
    "NAS100": {"spread_bps": 1.30, "commission_bps": 0, "tick_size": 0.01},
    "US30": {"spread_bps": 0.80, "commission_bps": 0, "tick_size": 0.01},
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class Position:
    symbol: str
    side: int  # +1 long, -1 short
    entry_price: float
    entry_bar: int
    quantity: float  # vol-scaled notional / price


@dataclass
class Trade:
    symbol: str
    side: int
    entry_price: float
    exit_price: float
    entry_bar: int
    exit_bar: int
    quantity: float
    pnl: float
    cost: float
    bars_held: int


@dataclass
class BarData:
    time: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float


# ---------------------------------------------------------------------------
# Signal computation (single lookback, per MOP §2)
# ---------------------------------------------------------------------------
def compute_signal(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Compute TSMOM signal + vol_scale for a single symbol.

    Returns (signal, vol_scale) where signal ∈ {-1, 0, +1} and vol_scale ∈ [0, 2].
    """
    # 12-month return
    ret_12m = close / close.shift(LOOKBACK) - 1

    # Signal: sign of 12-month return
    signal = np.sign(ret_12m)

    # Realized vol (21-day rolling, annualized)
    realized_vol = close.pct_change().rolling(21).std() * np.sqrt(252)

    # Vol scale: target / realized, clipped
    vol_scale = (VOL_TARGET / realized_vol.clip(lower=VOL_CLIP_LOWER)).clip(upper=VOL_CLIP_UPPER)

    return signal, vol_scale


# ---------------------------------------------------------------------------
# Position lifecycle (hand-rolled, no BacktestEngine)
# ---------------------------------------------------------------------------
def run_backtest(
    data: dict[str, pd.DataFrame],
    cost_multiplier: float = 1.0,
) -> dict:
    """Run TSMOM backtest across all symbols.

    Parameters
    ----------
    data : dict[symbol -> DataFrame with time, open, high, low, close, volume]
    cost_multiplier : float, cost stress multiplier (1.0 = base, 1.5 = stress, 2.0 = stress)

    Returns
    -------
    dict with portfolio_returns, trades, metrics
    """
    # Compute signals for each symbol
    signals = {}
    vol_scales = {}
    for sym, df in data.items():
        sig, vs = compute_signal(df["close"])
        signals[sym] = sig
        vol_scales[sym] = vs

    # Find common rebalance dates (every REBALANCE_FREQ bars from start)
    all_dates_set: set = set()
    for df in data.values():
        all_dates_set.update(df["time"].tolist())
    all_dates = sorted(all_dates_set)

    # Rebalance dates: every REBALANCE_FREQ bars from the first date
    rebal_indices = list(range(LOOKBACK, len(all_dates), REBALANCE_FREQ))
    rebal_dates = [all_dates[i] for i in rebal_indices]

    # Track positions and P&L
    positions: dict[str, Position | None] = {sym: None for sym in data}
    trades: list[Trade] = []
    portfolio_returns = []

    for i, date in enumerate(all_dates):
        # Daily returns for all symbols
        daily_ret = {}
        for sym, df in data.items():
            mask = df["time"] == date
            if mask.any():
                idx = df.index[mask][0]
                if idx > 0:
                    prev_close = df["close"].iloc[idx - 1]
                    daily_ret[sym] = df["close"].iloc[idx] / prev_close - 1
                else:
                    daily_ret[sym] = 0.0
            else:
                daily_ret[sym] = 0.0

        # Portfolio return = sum of position * daily_return across symbols
        port_ret = 0.0
        for sym in data:
            pos = positions[sym]
            if pos is not None:
                port_ret += pos.side * pos.quantity * daily_ret.get(sym, 0.0)

        # Costs accumulated during rebalance (below), deducted from this day's return
        daily_cost = 0.0

        # Rebalance: update positions based on signals
        if date in rebal_dates:
            for sym in data:
                df = data[sym]
                mask = df["time"] == date
                if not mask.any():
                    continue
                idx = df.index[mask][0]

                sig_val = signals[sym].iloc[idx] if idx < len(signals[sym]) else 0
                vs_val = vol_scales[sym].iloc[idx] if idx < len(vol_scales[sym]) else 1.0

                # Target position size (vol-scaled notional)
                target_side = int(sig_val) if not np.isnan(sig_val) else 0
                target_qty = abs(vs_val) if not np.isnan(vs_val) else 0.0

                # Close existing position if side changed or going flat
                old_pos = positions[sym]
                if old_pos is not None and (old_pos.side != target_side or target_side == 0):
                    # Close position
                    close_price = df["close"].iloc[idx]
                    cost = _compute_cost(sym, old_pos.entry_price, close_price, old_pos.quantity, cost_multiplier)
                    pnl = old_pos.side * (close_price - old_pos.entry_price) * old_pos.quantity - cost
                    trades.append(
                        Trade(
                            symbol=sym,
                            side=old_pos.side,
                            entry_price=old_pos.entry_price,
                            exit_price=close_price,
                            entry_bar=old_pos.entry_bar,
                            exit_bar=idx,
                            quantity=old_pos.quantity,
                            pnl=pnl,
                            cost=cost,
                            bars_held=idx - old_pos.entry_bar,
                        )
                    )
                    daily_cost += cost
                    positions[sym] = None

                # Open new position if we have a signal
                if target_side != 0 and target_qty > 0:
                    entry_price = df["close"].iloc[idx]
                    # Vol-scaled notional: target_qty is vol_scale, convert to units
                    # For simplicity: quantity = vol_scale (represents risk budget)
                    positions[sym] = Position(
                        symbol=sym,
                        side=target_side,
                        entry_price=entry_price,
                        entry_bar=idx,
                        quantity=target_qty,
                    )

        portfolio_returns.append({"time": date, "return": port_ret - daily_cost})

    # Close any remaining positions at last price
    for sym in data:
        pos = positions[sym]
        if pos is not None:
            df = data[sym]
            last_idx = len(df) - 1
            close_price = df["close"].iloc[last_idx]
            cost = _compute_cost(sym, pos.entry_price, close_price, pos.quantity, cost_multiplier)
            pnl = pos.side * (close_price - pos.entry_price) * pos.quantity - cost
            trades.append(
                Trade(
                    symbol=sym,
                    side=pos.side,
                    entry_price=pos.entry_price,
                    exit_price=close_price,
                    entry_bar=pos.entry_bar,
                    exit_bar=last_idx,
                    quantity=pos.quantity,
                    pnl=pnl,
                    cost=cost,
                    bars_held=last_idx - pos.entry_bar,
                )
            )

    # Compute metrics
    port_df = pd.DataFrame(portfolio_returns)
    port_df["cumulative"] = (1 + port_df["return"]).cumprod()

    # Sharpe ratio (annualized)
    ann_ret = port_df["return"].mean() * 252
    ann_vol = port_df["return"].std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0

    # Total trades and position changes
    total_trades = len(trades)
    total_cost = sum(t.cost for t in trades)

    return {
        "portfolio_returns": port_df,
        "trades": trades,
        "metrics": {
            "sharpe": sharpe,
            "annualized_return": ann_ret,
            "annualized_vol": ann_vol,
            "total_trades": total_trades,
            "total_cost": total_cost,
            "total_pnl": sum(t.pnl for t in trades),
        },
    }


def _compute_cost(
    symbol: str,
    entry_price: float,
    exit_price: float,
    quantity: float,
    multiplier: float = 1.0,
) -> float:
    """Compute round-trip cost for a trade.

    Since quantity = vol_scale (dimensionless risk budget, NOT units),
    cost is in portfolio-return terms: vol_scale * spread_bps / 10000.
    """
    cal = _COST_CALIBRATION.get(symbol, {"spread_bps": 1.0, "commission_bps": 0})
    spread_bps = cal["spread_bps"] * multiplier
    commission_bps = cal["commission_bps"] * multiplier

    # Cost in return terms: vol_scale * (spread + commission) in bps
    return quantity * (spread_bps + commission_bps) / 10000


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def pooled_dk_test(returns_by_symbol: dict[str, pd.Series]) -> float:
    """Pooled Driscoll-Kraay t-statistic across symbols."""
    # Simple pooled test: concatenate all returns and compute t-stat
    all_returns = []
    for sym, ret in returns_by_symbol.items():
        all_returns.extend(ret.dropna().tolist())

    if len(all_returns) < 10:
        return 0.0

    arr = np.array(all_returns)
    mean = arr.mean()
    std = arr.std()
    n = len(arr)

    if std == 0:
        return 0.0

    t_stat = mean / (std / np.sqrt(n))
    return t_stat


def jackknife_sharpe(
    returns_by_symbol: dict[str, pd.Series],
) -> dict[str, float]:
    """Jackknife: Sharpe with each symbol dropped."""
    # Full portfolio returns (equal-weight)
    full_ret = pd.concat(returns_by_symbol.values(), axis=1).mean(axis=1)
    full_sharpe = full_ret.mean() / full_ret.std() * np.sqrt(252) if full_ret.std() > 0 else 0.0

    results = {"full_sharpe": full_sharpe}
    for drop_sym in returns_by_symbol:
        remaining = {s: r for s, r in returns_by_symbol.items() if s != drop_sym}
        if remaining:
            jack_ret = pd.concat(remaining.values(), axis=1).mean(axis=1)
            jack_sharpe = jack_ret.mean() / jack_ret.std() * np.sqrt(252) if jack_ret.std() > 0 else 0.0
            results[f"drop_{drop_sym}"] = jack_sharpe

    return results


def cluster_jackknife(
    returns_by_symbol: dict[str, pd.Series],
) -> dict[str, float]:
    """Cluster jackknife: Sharpe with each correlated cluster dropped.

    Clusters:
      - precious_metals: XAUUSD, XAGUSD
      - us_indices: NAS100, US30
      - fx: EURUSD, GBPUSD, USDJPY
    """
    clusters = {
        "precious_metals": ["XAUUSD", "XAGUSD"],
        "us_indices": ["NAS100", "US30"],
        "fx": ["EURUSD", "GBPUSD", "USDJPY"],
    }

    full_ret = pd.concat(returns_by_symbol.values(), axis=1).mean(axis=1)
    full_sharpe = full_ret.mean() / full_ret.std() * np.sqrt(252) if full_ret.std() > 0 else 0.0

    results = {"full_sharpe": full_sharpe}
    for cluster_name, syms in clusters.items():
        remaining = {s: r for s, r in returns_by_symbol.items() if s not in syms}
        if remaining:
            jack_ret = pd.concat(remaining.values(), axis=1).mean(axis=1)
            jack_sharpe = jack_ret.mean() / jack_ret.std() * np.sqrt(252) if jack_ret.std() > 0 else 0.0
            results[f"drop_{cluster_name}"] = jack_sharpe

    return results


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main():
    """Run WS-A TSMOM backtest and validation."""
    print("=" * 60)
    print("WS-A TSMOM Harness — MOP-2012 Replication (Trial 1028)")
    print("=" * 60)

    # Load data
    print("\nLoading data...")
    data = {}
    for sym in UNIVERSE:
        try:
            # SP1 note: cost config moved XAGUSD/others to removed_assets (2026-08-03);
            # pre-reg 1028 locked pepperstone_razor table in harness — same as 3008/1032.
            df = load_provenance_checked(sym, require_cost_calibration=False)
            data[sym] = df
            print(f"  {sym}: {len(df)} bars, {df['time'].min().date()} to {df['time'].max().date()}")
        except Exception as e:
            print(f"  {sym}: FAILED — {e}")
            return 1

    # Run backtest (base costs)
    print("\nRunning backtest (base costs)...")
    result = run_backtest(data, cost_multiplier=1.0)
    m = result["metrics"]
    print(f"  Sharpe: {m['sharpe']:.3f}")
    print(f"  Annualized return: {m['annualized_return']:.2%}")
    print(f"  Annualized vol: {m['annualized_vol']:.2%}")
    print(f"  Total trades: {m['total_trades']}")
    print(f"  Total cost: ${m['total_cost']:.2f}")

    # Compute per-symbol returns for validation
    print("\nComputing per-symbol returns...")
    returns_by_symbol = {}
    for sym in UNIVERSE:
        df = data[sym]
        sig, vs = compute_signal(df["close"])
        # Simple signal * return series
        ret = df["close"].pct_change()
        signal_ret = sig.shift(1) * ret  # signal from prior bar
        returns_by_symbol[sym] = signal_ret.dropna()

    # Pooled DK test (using verified Newey-West HAC implementation from edge_search_all)
    print("\nPooled DK test (Newey-West HAC)...")
    _all_returns_df = pd.DataFrame(returns_by_symbol)
    _dk_result = _verified_dk_test(_all_returns_df, total_trades=len(result["trades"]))
    dk_t = _dk_result["dk_t_stat"]
    print(f"  t-stat: {dk_t:.3f}")
    print(f"  PASS (t > 2.0): {dk_t > 2.0}")
    print(f"  Verdict: {_dk_result.get('verdict', 'N/A')}")

    # Jackknife
    print("\nJackknife analysis...")
    jk = jackknife_sharpe(returns_by_symbol)
    full_sharpe = jk["full_sharpe"]
    print(f"  Full Sharpe: {full_sharpe:.3f}")
    for key, val in jk.items():
        if key != "full_sharpe":
            delta = abs(val - full_sharpe)
            print(f"  {key}: {val:.3f} (delta: {delta:.3f})")

    # Cluster jackknife (drop correlated groups)
    print("\nCluster jackknife analysis...")
    cjk = cluster_jackknife(returns_by_symbol)
    for key, val in cjk.items():
        if key != "full_sharpe":
            delta = abs(val - cjk["full_sharpe"])
            print(f"  {key}: {val:.3f} (delta: {delta:.3f})")

    # Cost stress (1.5x and 2.0x)
    print("\nCost stress analysis...")
    base_total_cost = sum(t.cost for t in result["trades"])
    print(f"  Base total cost: {base_total_cost:.6f}")
    for mult in [1.5, 2.0]:
        stress_result = run_backtest(data, cost_multiplier=mult)
        stress_sharpe = stress_result["metrics"]["sharpe"]
        stress_total_cost = sum(t.cost for t in stress_result["trades"])
        print(
            f"  {mult}x costs: Sharpe = {stress_sharpe:.3f} (PASS: {stress_sharpe > 0}), total_cost = {stress_total_cost:.6f} (expected {base_total_cost * mult:.6f})"
        )

    # DSR — bypass validation/__init__.py (which imports heavy deps) via importlib
    print("\nDeflated Sharpe Ratio...")
    try:
        import importlib.util

        # Load n_trials directly (only depends on pathlib + logging)
        _nt_spec = importlib.util.spec_from_file_location("n_trials", str(_ROOT / "validation" / "n_trials.py"))
        _nt_mod = importlib.util.module_from_spec(_nt_spec)
        _nt_spec.loader.exec_module(_nt_mod)
        n_trials = _nt_mod.get_reconciled_n_trials()
        print(f"  N trials: {n_trials}")

        # Load deflated_sharpe directly (only depends on math + dataclasses)
        _ds_spec = importlib.util.spec_from_file_location(
            "deflated_sharpe", str(_ROOT / "validation" / "deflated_sharpe.py")
        )
        _ds_mod = importlib.util.module_from_spec(_ds_spec)
        _ds_spec.loader.exec_module(_ds_mod)

        # Compute DSR — annualized Sharpe, daily bars: de-annualize via helper (SP1)
        _port_df = result["portfolio_returns"]
        dsr_result = _ds_mod.dsr_from_annualized(
            observed_sharpe=m["sharpe"],
            n_trials=n_trials,
            n_observations=len(_port_df),
            annualization_factor=252,  # D1 bars — SP1: unit-correct DSR
            skewness=float(_port_df["return"].skew()),
            kurtosis=float(_port_df["return"].kurtosis()) + 3.0,  # pandas kurtosis() is EXCESS; module expects RAW
        )
        print(f"  Observed Sharpe: {dsr_result.observed_sharpe:.3f}")
        print(f"  Multiple testing adjustment: {dsr_result.multiple_testing_adjustment:.4f}")
        print(f"  Probability alpha (false positive): {dsr_result.probability_alpha:.4f}")
        print(f"  DSR passes (alpha < 0.05): {'PASS' if dsr_result.passes_threshold else 'FAIL'}")

        # ── Institutional gates (SP2): WFA + Bootstrap CI + MinBTL ──────
        _tg_spec = importlib.util.spec_from_file_location(
            "_trial_gates", str(_ROOT / "scripts" / "_trial_gates.py")
        )
        _tg_mod = importlib.util.module_from_spec(_tg_spec)
        _tg_spec.loader.exec_module(_tg_mod)
        gates = _tg_mod.run_institutional_gates(
            portfolio_returns=_port_df["return"],
            returns_by_symbol=returns_by_symbol,
            observed_sharpe=m["sharpe"],
            n_trials=n_trials,
            n_bars=len(_port_df),
        )
        print(f"  WFA (purged-CV): folds={gates['wfa']['n_folds']} mean={gates['wfa']['oos_sharpe_mean']:.3f} pass={gates['wfa']['pass']}")
        print(f"  Bootstrap CI: [{gates['bootstrap_ci']['lower']:.3f}, {gates['bootstrap_ci']['upper']:.3f}] pass={gates['bootstrap_ci']['pass']}")
        print(f"  MinBTL: min_obs={gates['min_btl']['min_observations']} sufficient={gates['min_btl']['sufficient']}")
        print(f"  PBO: N/A — {gates['pbo_na']['reason'][:80]}...")
        _gates = gates
    except Exception as e:
        print(f"  DSR computation failed: {e}")
        dsr_result = None
        _gates = None

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Sharpe: {m['sharpe']:.3f}")
    print(f"DK t-stat: {dk_t:.3f}")
    print(f"Jackknife full: {full_sharpe:.3f}")
    print(f"Total trades: {m['total_trades']}")
    if dsr_result is not None:
        print(f"DSR alpha: {dsr_result.probability_alpha:.4f}")

    # Pre-registration gates
    dk_pass = dk_t > 2.0
    trades_pass = m["total_trades"] >= 50
    dsr_pass = dsr_result is not None and dsr_result.passes_threshold
    print("\nPre-registration gates:")
    print(f"  DK t > 2.0: {'PASS' if dk_pass else 'FAIL'} ({dk_t:.3f})")
    print(f"  Trades >= 50: {'PASS' if trades_pass else 'FAIL'} ({m['total_trades']})")
    dsr_alpha_str = f"{dsr_result.probability_alpha:.4f}" if dsr_result else "N/A"
    print(f"  DSR alpha < 0.05: {'PASS' if dsr_pass else 'FAIL'} ({dsr_alpha_str})")

    if dk_pass and trades_pass and dsr_pass:
        print("\n  -> PRIMARY GATE: PASS")
    else:
        print("\n  -> PRIMARY GATE: FAIL")

    return 0


if __name__ == "__main__":
    sys.exit(main())
