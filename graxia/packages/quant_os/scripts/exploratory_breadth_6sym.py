#!/usr/bin/env python3
"""EXPLORATORY (NOT a formal trial): breadth-gain test — 52w-high + TSMOM on 6-symbol universe.

Pre-registration discipline: the frozen 1028/1032 trials used 7-symbol universe
(XAUUSD, XAGUSD, EURUSD, GBPUSD, USDJPY, NAS100, US30). This run tests the NEW
6-symbol universe enabled by SP3 calibration (XAUUSD, EURUSD, GBPUSD, USDJPY,
BTCUSD, US30 — all FROM_TICKS + provenance-passing). Results are EXPLORATORY
only — NOT recorded as trial verdicts (universe change = new hypothesis).

Same signal logic + gates as run_52week_high_1032.py / run_ws_a_tsmom.py.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from edge_search_all import run_dk_test as _verified_dk_test  # noqa: E402
from provenance import load_provenance_checked  # noqa: E402

UNIVERSE_6 = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD", "US30"]
# SP2's institutional gates — load via spec (scripts is not a package here)
_tg_spec = importlib.util.spec_from_file_location("_trial_gates", str(_ROOT / "scripts" / "_trial_gates.py"))
_tg_mod = importlib.util.module_from_spec(_tg_spec)
_tg_spec.loader.exec_module(_tg_mod)
run_institutional_gates = _tg_mod.run_institutional_gates

# pepperstone_razor cost table (extended with SP3 calibrated values)
_COST = {
    "XAUUSD": {"spread_bps": 0.324, "commission_bps": 0, "tick_size": 0.01},
    "EURUSD": {"spread_bps": 0.088, "commission_bps": 7, "tick_size": 0.00001},
    "GBPUSD": {"spread_bps": 0.076, "commission_bps": 7, "tick_size": 0.00001},
    "USDJPY": {"spread_bps": 0.124, "commission_bps": 7, "tick_size": 0.001},
    "BTCUSD": {"spread_bps": 2.511, "commission_bps": 10, "tick_size": 1.0},
    "US30": {"spread_bps": 0.231, "commission_bps": 0, "tick_size": 0.1},
}

LOOKBACK_HIGH = 252
PROX_LONG = 0.95
PROX_SHORT = 0.80
REBAL = 21
VOL_TARGET = 0.10
CLIP = (0.01, 2.0)


def compute_52w(close: pd.Series) -> pd.Series:
    high = close.shift(1).rolling(LOOKBACK_HIGH, min_periods=1).max()
    prox = close.shift(1) / high
    sig = pd.Series(0.0, index=close.index)
    sig[prox >= PROX_LONG] = 1.0
    sig[prox <= PROX_SHORT] = -1.0
    sig[prox.isna()] = 0.0
    return sig


def compute_tsmom(close: pd.Series, lb: int = 252) -> pd.Series:
    ret = close.pct_change()
    mom = close.pct_change(lb)
    sig = pd.Series(0.0, index=close.index)
    sig[mom > 0] = 1.0
    sig[mom < 0] = -1.0
    sig[mom.isna()] = 0.0
    return sig


def run_strategy(name: str, sig_fn) -> dict:
    data = {}
    for sym in UNIVERSE_6:
        try:
            df = load_provenance_checked(sym, require_cost_calibration=False)
            data[sym] = df
        except Exception as e:
            print(f"  [SKIP] {sym}: {type(e).__name__}: {str(e)[:60]}")
            return {}

    returns_by_symbol = {}
    port_ret = None
    for sym, df in data.items():
        sig = sig_fn(df["close"])
        ret = df["close"].pct_change()
        sret = sig.shift(1) * ret
        returns_by_symbol[sym] = sret.dropna()
        if port_ret is None:
            port_ret = returns_by_symbol[sym].copy()
        else:
            port_ret = port_ret.add(returns_by_symbol[sym], fill_value=0.0)
    port_ret = port_ret / len(data)

    # metrics (annualized)
    sharpe = port_ret.mean() / port_ret.std() * np.sqrt(252) if port_ret.std() > 0 else 0.0
    ann_ret = port_ret.mean() * 252
    ann_vol = port_ret.std() * np.sqrt(252)

    # DK test
    dk = _verified_dk_test(pd.DataFrame(returns_by_symbol), total_trades=0)
    dk_t = dk["dk_t_stat"]

    # DSR (unit-correct via helper)
    _ds = importlib.util.spec_from_file_location("dsr", str(_ROOT / "validation" / "deflated_sharpe.py"))
    _dsm = importlib.util.module_from_spec(_ds)
    _ds.loader.exec_module(_dsm)
    _nt = importlib.util.spec_from_file_location("nt", str(_ROOT / "validation" / "n_trials.py"))
    _ntm = importlib.util.module_from_spec(_nt)
    _nt.loader.exec_module(_ntm)
    n_trials = _ntm.get_reconciled_n_trials()
    dsr = _dsm.dsr_from_annualized(
        observed_sharpe=sharpe, n_trials=n_trials, n_observations=len(port_ret),
        annualization_factor=252, skewness=float(port_ret.skew()),
        kurtosis=float(port_ret.kurtosis()) + 3.0,
    )

    # SP2 institutional gates
    gates = run_institutional_gates(
        portfolio_returns=port_ret,
        returns_by_symbol=returns_by_symbol,
        observed_sharpe=sharpe, n_trials=n_trials, n_bars=len(port_ret),
    )

    return {
        "strategy": name,
        "universe": UNIVERSE_6,
        "n_symbols": len(data),
        "sharpe": round(sharpe, 4),
        "ann_ret": round(ann_ret, 4),
        "ann_vol": round(ann_vol, 4),
        "dk_t": round(dk_t, 4),
        "dsr_p": round(dsr.probability_alpha, 4),
        "dsr_pass": dsr.passes_threshold,
        "wfa_mean": gates["wfa"]["oos_sharpe_mean"],
        "wfa_pass": gates["wfa"]["pass"],
        "boot_ci": [gates["bootstrap_ci"]["lower"], gates["bootstrap_ci"]["upper"]],
        "boot_pass": gates["bootstrap_ci"]["pass"],
        "min_btl_sufficient": gates["min_btl"]["sufficient"],
        "per_symbol_sharpe": {s: round(float(r.mean() / r.std() * np.sqrt(252)), 3) if r.std() > 0 else 0.0 for s, r in returns_by_symbol.items()},
    }


if __name__ == "__main__":
    print("=" * 64)
    print("EXPLORATORY breadth test — 6-symbol universe (NOT a formal trial)")
    print("=" * 64)
    results = []
    for name, fn in [("52week_high", compute_52w), ("tsmom_252", compute_tsmom)]:
        print(f"\n--- {name} ---")
        r = run_strategy(name, fn)
        if r:
            results.append(r)
            print(f"  Sharpe={r['sharpe']} DK_t={r['dk_t']} DSR_p={r['dsr_p']} ({'PASS' if r['dsr_pass'] else 'FAIL'})")
            print(f"  WFA={r['wfa_mean']} BootCI={r['boot_ci']} MinBTL_suf={r['min_btl_sufficient']}")
            print(f"  per-symbol: {r['per_symbol_sharpe']}")

    out = _ROOT / "reports" / "exploratory_breadth_6sym_20260803.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=lambda o: bool(o)), encoding="utf-8")
    print(f"\n[SAVE] {out}")
