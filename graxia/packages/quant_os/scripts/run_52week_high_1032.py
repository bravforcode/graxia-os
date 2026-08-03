#!/usr/bin/env python3
"""WS-A Trial 1032 Harness — 52-Week High Momentum (George-Hwang 2004).

Level-anchored replication: proximity to trailing 52-week high predicts returns
(anchoring/disposition mechanism). Frozen per
research/pre_registration/trial_1032_52week_high.md (locked 2026-08-03).

Structure mirrors scripts/run_ws_a_tsmom.py (trial 1028):
- monthly rebalance (21 trading days), vol-target sizing (0.10, clip [0.01,2.0])
- verified DK test from edge_search_all
- DSR with reconciled N=1050
- jackknife / cluster-jackknife / cost-stress / label-shuffle
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from edge_search_all import run_dk_test as _verified_dk_test  # noqa: E402

from provenance import load_provenance_checked  # noqa: E402

# ---------------------------------------------------------------------------
# Constants (FROZEN per pre-registration §2–§3)
# ---------------------------------------------------------------------------
LOOKBACK_HIGH = 252  # 52-week trailing max (as-of prior close)
PROX_LONG = 0.95  # near 52-week high -> long
PROX_SHORT = 0.80  # far below 52-week high -> short
REBALANCE_FREQ = 21  # monthly rebalance (D1 bars)
VOL_TARGET = 0.10
VOL_CLIP_UPPER = 2.0
VOL_CLIP_LOWER = 0.01
LOOKBACK_VOL = 21
UNIVERSE = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "US30"]

N_LABEL_SHUFFLES = 200
LABEL_SHUFFLE_SEED = 20260803

# pepperstone_razor cost table (identical to trial 1028 harness)
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
# Signal computation (frozen §2 — NO lookahead)
# ---------------------------------------------------------------------------
def compute_signal(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    """52-week-high proximity signal + vol_scale.

    high_52w[t] = max(close[t-252 .. t-1])  -- trailing max EXCLUDING t
    prox[t]     = close[t-1] / high_52w[t]  -- as-of prior close
    signal      = +1 prox>=0.95, -1 prox<=0.80, 0 otherwise
    """
    # rolling max of close shifted by 1: max over the 252 closes strictly before t
    high_52w = close.shift(1).rolling(LOOKBACK_HIGH, min_periods=1).max()
    # prox uses close[t-1] (shift 1) so the signal is knowable at t-1 close
    prox = close.shift(1) / high_52w

    signal = pd.Series(0.0, index=close.index)
    signal[prox >= PROX_LONG] = 1.0
    signal[prox <= PROX_SHORT] = -1.0
    signal[prox.isna()] = 0.0

    realized_vol = close.pct_change().rolling(LOOKBACK_VOL).std() * np.sqrt(252)
    vol_scale = (VOL_TARGET / realized_vol.clip(lower=VOL_CLIP_LOWER)).clip(upper=VOL_CLIP_UPPER)
    return signal, vol_scale


# ---------------------------------------------------------------------------
# Backtest (mirrors run_ws_a_tsmom.py)
# ---------------------------------------------------------------------------
@dataclass
class Position:
    symbol: str
    side: int
    entry_price: float
    entry_bar: int
    quantity: float


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


def _compute_cost(symbol: str, quantity: float, multiplier: float = 1.0) -> float:
    cal = _COST_CALIBRATION.get(symbol, {"spread_bps": 1.0, "commission_bps": 0})
    spread_bps = cal["spread_bps"] * multiplier
    commission_bps = cal["commission_bps"] * multiplier
    return quantity * (spread_bps + commission_bps) / 10000


def run_backtest(data: dict[str, pd.DataFrame], cost_multiplier: float = 1.0) -> dict:
    signals: dict[str, pd.Series] = {}
    vol_scales: dict[str, pd.Series] = {}
    for sym, df in data.items():
        sig, vs = compute_signal(df["close"])
        signals[sym] = sig
        vol_scales[sym] = vs

    all_dates_set: set = set()
    for df in data.values():
        all_dates_set.update(df["time"].tolist())
    all_dates = sorted(all_dates_set)

    rebal_indices = list(range(LOOKBACK_HIGH + 1, len(all_dates), REBALANCE_FREQ))
    rebal_dates = {all_dates[i] for i in rebal_indices}

    positions: dict[str, Position | None] = {sym: None for sym in data}
    trades: list[Trade] = []
    portfolio_returns: list[dict] = []

    for i, date in enumerate(all_dates):
        daily_ret: dict[str, float] = {}
        for sym, df in data.items():
            mask = df["time"] == date
            if mask.any():
                idx = df.index[mask][0]
                if idx > 0:
                    daily_ret[sym] = df["close"].iloc[idx] / df["close"].iloc[idx - 1] - 1
                else:
                    daily_ret[sym] = 0.0
            else:
                daily_ret[sym] = 0.0

        port_ret = 0.0
        for sym in data:
            pos = positions[sym]
            if pos is not None:
                port_ret += pos.side * pos.quantity * daily_ret.get(sym, 0.0)

        daily_cost = 0.0

        if date in rebal_dates:
            for sym in data:
                df = data[sym]
                mask = df["time"] == date
                if not mask.any():
                    continue
                idx = df.index[mask][0]
                sig_val = signals[sym].iloc[idx] if idx < len(signals[sym]) else 0
                vs_val = vol_scales[sym].iloc[idx] if idx < len(vol_scales[sym]) else 1.0
                target_side = int(sig_val) if not np.isnan(sig_val) else 0
                target_qty = abs(vs_val) if not np.isnan(vs_val) else 0.0

                old_pos = positions[sym]
                if old_pos is not None and (old_pos.side != target_side or target_side == 0):
                    close_price = df["close"].iloc[idx]
                    cost = _compute_cost(sym, old_pos.quantity, cost_multiplier)
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

                if target_side != 0 and target_qty > 0:
                    entry_price = df["close"].iloc[idx]
                    positions[sym] = Position(
                        symbol=sym,
                        side=target_side,
                        entry_price=entry_price,
                        entry_bar=idx,
                        quantity=target_qty,
                    )

        portfolio_returns.append({"time": date, "return": port_ret - daily_cost})

    for sym in data:
        pos = positions[sym]
        if pos is not None:
            df = data[sym]
            last_idx = len(df) - 1
            close_price = df["close"].iloc[last_idx]
            cost = _compute_cost(sym, pos.quantity, cost_multiplier)
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

    port_df = pd.DataFrame(portfolio_returns)
    if len(port_df) > 1:
        port_df["cumulative"] = (1 + port_df["return"]).cumprod()
        ann_ret = port_df["return"].mean() * 252
        ann_vol = port_df["return"].std() * np.sqrt(252)
        sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0
    else:
        ann_ret = ann_vol = sharpe = 0.0

    return {
        "portfolio_returns": port_df,
        "trades": trades,
        "metrics": {
            "sharpe": sharpe,
            "annualized_return": ann_ret,
            "annualized_vol": ann_vol,
            "total_trades": len(trades),
            "total_cost": sum(t.cost for t in trades),
            "total_pnl": sum(t.pnl for t in trades),
        },
    }


def per_asset_trades(trades: list[Trade]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for t in trades:
        counts[t.symbol] = counts.get(t.symbol, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def jackknife_sharpe(returns_by_symbol: dict[str, pd.Series]) -> dict[str, float]:
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


def cluster_jackknife(returns_by_symbol: dict[str, pd.Series]) -> dict[str, float]:
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


def label_shuffle(returns_by_symbol: dict[str, pd.Series], n_shuffles: int = N_LABEL_SHUFFLES) -> dict:
    cs_mean = pd.concat(returns_by_symbol.values(), axis=1).mean(axis=1).dropna()
    if len(cs_mean) < 30:
        return {"n_shuffles": 0, "p_value": 1.0, "verdict": "INSUFFICIENT_DATA"}
    obs_sharpe = cs_mean.mean() / cs_mean.std() * np.sqrt(252) if cs_mean.std() > 0 else 0.0
    counts = 0
    rng = np.random.default_rng(LABEL_SHUFFLE_SEED)
    for _ in range(n_shuffles):
        signs = rng.choice([-1.0, 1.0], size=len(cs_mean))
        s = cs_mean * signs
        sh = s.mean() / s.std() * np.sqrt(252) if s.std() > 0 else 0.0
        if sh >= obs_sharpe:
            counts += 1
    p = counts / n_shuffles
    return {"n_shuffles": n_shuffles, "p_value": p, "verdict": "PASS" if p <= 0.05 else "FAIL"}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    print("=" * 60)
    print("WS-A Trial 1032 — 52-Week High Momentum (George-Hwang 2004)")
    print("=" * 60)

    print("\nLoading data...")
    data = {}
    for sym in UNIVERSE:
        try:
            df = load_provenance_checked(sym, require_cost_calibration=False)
            data[sym] = df
            print(f"  {sym}: {len(df)} bars, {df['time'].min().date()} to {df['time'].max().date()}")
        except Exception as e:
            print(f"  {sym}: FAILED — {e}")
            return 1

    result = run_backtest(data, cost_multiplier=1.0)
    m = result["metrics"]
    print("\nBase backtest (1.0x costs):")
    print(f"  Sharpe: {m['sharpe']:.3f}")
    print(f"  Annualized return: {m['annualized_return']:.2%}")
    print(f"  Annualized vol: {m['annualized_vol']:.2%}")
    print(f"  Total trades: {m['total_trades']}")
    print(f"  Total cost: {m['total_cost']:.4f}")
    print(f"  Per-asset trades: {per_asset_trades(result['trades'])}")

    returns_by_symbol: dict[str, pd.Series] = {}
    for sym in UNIVERSE:
        df = data[sym]
        sig, _vs = compute_signal(df["close"])
        ret = df["close"].pct_change()
        signal_ret = sig.shift(1) * ret
        returns_by_symbol[sym] = signal_ret.dropna()

    print("\nPooled DK test (Newey-West HAC)...")
    _all_returns_df = pd.DataFrame(returns_by_symbol)
    dk_result = _verified_dk_test(_all_returns_df, total_trades=len(result["trades"]))
    dk_t = dk_result["dk_t_stat"]
    print(f"  t-stat: {dk_t:.3f}  verdict: {dk_result.get('verdict')}")

    print("\nJackknife analysis...")
    jk = jackknife_sharpe(returns_by_symbol)
    full_sharpe = jk["full_sharpe"]
    print(f"  Full Sharpe: {full_sharpe:.3f}")
    for key, val in jk.items():
        if key != "full_sharpe":
            print(f"  {key}: {val:.3f} (delta: {abs(val - full_sharpe):.3f})")

    print("\nCluster jackknife analysis...")
    cjk = cluster_jackknife(returns_by_symbol)
    for key, val in cjk.items():
        if key != "full_sharpe":
            print(f"  {key}: {val:.3f} (delta: {abs(val - cjk['full_sharpe']):.3f})")

    print("\nCost stress analysis...")
    for mult in [1.5, 2.0]:
        stress = run_backtest(data, cost_multiplier=mult)
        s = stress["metrics"]["sharpe"]
        print(f"  {mult}x costs: Sharpe = {s:.3f} (PASS: {s > 0})")

    print("\nLabel shuffle...")
    ls = label_shuffle(returns_by_symbol)
    print(f"  p_value: {ls['p_value']:.4f}  verdict: {ls['verdict']}")

    print("\nDeflated Sharpe Ratio...")
    dsr_result = None
    try:
        _nt_spec = importlib.util.spec_from_file_location("n_trials", str(_ROOT / "validation" / "n_trials.py"))
        assert _nt_spec is not None and _nt_spec.loader is not None
        _nt_mod = importlib.util.module_from_spec(_nt_spec)
        _nt_spec.loader.exec_module(_nt_mod)
        n_trials = _nt_mod.get_reconciled_n_trials()
        print(f"  N trials: {n_trials}")

        _ds_spec = importlib.util.spec_from_file_location(
            "deflated_sharpe", str(_ROOT / "validation" / "deflated_sharpe.py")
        )
        assert _ds_spec is not None and _ds_spec.loader is not None
        _ds_mod = importlib.util.module_from_spec(_ds_spec)
        _ds_spec.loader.exec_module(_ds_mod)

        _port_df = result["portfolio_returns"]
        dsr_result = _ds_mod.deflated_sharpe_ratio(
            observed_sharpe=m["sharpe"],
            n_trials=n_trials,
            n_observations=len(_port_df),
            sharpe_annualization_factor=1.0,
            skewness=float(_port_df["return"].skew()),
            kurtosis=float(_port_df["return"].kurtosis()),
        )
        print(f"  Observed Sharpe: {dsr_result.observed_sharpe:.3f}")
        print(f"  Multiple testing adjustment: {dsr_result.multiple_testing_adjustment:.4f}")
        print(f"  Probability alpha: {dsr_result.probability_alpha:.4f}")
        print(f"  DSR passes (alpha < 0.05): {'PASS' if dsr_result.passes_threshold else 'FAIL'}")
    except Exception as e:
        print(f"  DSR computation failed: {e}")

    # Gates
    dk_pass = dk_t > 2.0
    dsr_pass = dsr_result is not None and dsr_result.passes_threshold
    trades_pass = all(v >= 50 for v in per_asset_trades(result["trades"]).values())
    stress_pass = all(run_backtest(data, cost_multiplier=mult)["metrics"]["sharpe"] > 0 for mult in [1.5, 2.0])
    jk_pass = all(abs(v - full_sharpe) < 0.5 for k, v in jk.items() if k != "full_sharpe" and k.startswith("drop_"))
    ls_pass = ls["verdict"] == "PASS"

    print("\n" + "=" * 60)
    print("GATE SUMMARY (pre-registered §4)")
    print("=" * 60)
    print(f"  DK t > 2.0:            {'PASS' if dk_pass else 'FAIL'} ({dk_t:.3f})")
    print(f"  DSR alpha < 0.05:      {'PASS' if dsr_pass else 'FAIL'}")
    print(f"  Trades >= 50/asset:    {'PASS' if trades_pass else 'FAIL'} ({per_asset_trades(result['trades'])})")
    print(f"  Cost stress 1.5/2.0x:  {'PASS' if stress_pass else 'FAIL'}")
    print(f"  Jackknife delta < 0.5: {'PASS' if jk_pass else 'FAIL'}")
    print(f"  Label shuffle p<=0.05: {'PASS' if ls_pass else 'FAIL'} (p={ls['p_value']:.4f})")

    if dk_pass and dsr_pass and trades_pass and stress_pass and jk_pass and ls_pass:
        print("\n  -> PRIMARY GATE: PASS")
    else:
        print("\n  -> PRIMARY GATE: FAIL")

    artifact = {
        "trial_number": 1032,
        "id": "WS-A-52WEEK-HIGH",
        "strategy": "52_week_high_proximity",
        "source": "George & Hwang (2004), Journal of Finance 59(5)",
        "registered_at": "2026-08-03",
        "executed_at": pd.Timestamp.utcnow().isoformat(),
        "universe": UNIVERSE,
        "params": {
            "lookback_high": LOOKBACK_HIGH,
            "prox_long": PROX_LONG,
            "prox_short": PROX_SHORT,
            "rebalance_freq": REBALANCE_FREQ,
            "vol_target": VOL_TARGET,
        },
        "cost_model": "pepperstone_razor (frozen, per pre-reg §2)",
        "metrics": m,
        "per_asset_trades": per_asset_trades(result["trades"]),
        "dk_test": {
            k: dk_result.get(k)
            for k in ("dk_t_stat", "pooled_sharpe", "positive_sharpe_count", "total_days", "total_trades", "verdict")
        },
        "jackknife": jk,
        "cluster_jackknife": cjk,
        "label_shuffle": ls,
        "dsr": None
        if dsr_result is None
        else {
            "observed_sharpe": dsr_result.observed_sharpe,
            "multiple_testing_adjustment": dsr_result.multiple_testing_adjustment,
            "probability_alpha": dsr_result.probability_alpha,
            "passes_threshold": dsr_result.passes_threshold,
            "n_trials": n_trials,
        },
        "gates": {
            "dk_pass": dk_pass,
            "dsr_pass": dsr_pass,
            "trades_pass": trades_pass,
            "stress_pass": stress_pass,
            "jackknife_pass": jk_pass,
            "label_shuffle_pass": ls_pass,
        },
        "combined_verdict": "PASS"
        if (dk_pass and dsr_pass and trades_pass and stress_pass and jk_pass and ls_pass)
        else "REJECT",
    }
    out = _ROOT / "reports" / "trial_1032_52week_high_results.json"
    out.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
    print(f"\nArtifact written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
