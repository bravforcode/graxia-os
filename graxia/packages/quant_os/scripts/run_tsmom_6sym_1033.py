#!/usr/bin/env python3
"""WS-A Trial 1033 Harness — TSMOM on 6-Symbol Breadth Universe.

Formal run of the exploratory result (reports/exploratory_breadth_6sym_20260803.json).
Frozen per research/pre_registration/trial_1033_tsmom_6sym.md (2026-08-04).

Full gate stack: DK + DSR (unit-correct) + WFA + Bootstrap CI + MinBTL +
jackknife + cost-stress + label-shuffle. PBO = N/A (single frozen config).
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

UNIVERSE = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD", "US30"]
LOOKBACK = 252
REBAL = 21
VOL_TARGET = 0.10
CLIP = (0.01, 2.0)

# SP3 calibrated FROM_TICKS costs
# COMMISSION UNIT FIX 2026-08-06: field was USD/rt-lot misread as bps (8-29x
# overstatement). True bps per reports/audit_trial_9001_9002_cost_model.md.
_COST = {
    "XAUUSD": {"spread_bps": 0.324, "commission_bps": 0},
    "EURUSD": {"spread_bps": 0.088, "commission_bps": 0.606},
    "GBPUSD": {"spread_bps": 0.076, "commission_bps": 0.520},
    "USDJPY": {"spread_bps": 0.124, "commission_bps": 0.700},
    "BTCUSD": {"spread_bps": 2.511, "commission_bps": 1.546},
    "US30": {"spread_bps": 0.231, "commission_bps": 0},
}
N_LABEL_SHUFFLES = 200
SEED = 20260804


def load_data() -> dict[str, pd.DataFrame]:
    data = {}
    for sym in UNIVERSE:
        try:
            df = load_provenance_checked(sym)  # require_cost_calibration=True (SP3!)
            data[sym] = df
            print(f"  {sym}: {len(df)} bars")
        except Exception as e:
            print(f"  [SKIP] {sym}: {type(e).__name__}: {str(e)[:70]}")
    return data


def compute_signal(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    mom = close.pct_change(LOOKBACK)
    sig = pd.Series(0.0, index=close.index)
    sig[mom > 0] = 1.0
    sig[mom < 0] = -1.0
    sig[mom.isna()] = 0.0
    vol = close.pct_change().rolling(21).std() * np.sqrt(252)
    scale = (VOL_TARGET / vol.clip(lower=CLIP[0])).clip(upper=CLIP[1])
    return sig, scale


def run_backtest(data: dict, cost_mult: float = 1.0) -> dict:
    """Hand-rolled TSMOM backtest with per-symbol costs + monthly rebalance."""
    signals, scales = {}, {}
    for sym, df in data.items():
        sig, sc = compute_signal(df["close"])
        signals[sym] = sig
        scales[sym] = sc

    all_dates = sorted(set().union(*[set(df["time"].tolist()) for df in data.values()]))
    rebal_dates = {all_dates[i] for i in range(LOOKBACK + 1, len(all_dates), REBAL)}

    positions: dict[str, tuple[int, float, float]] = {}  # sym -> (side, qty, entry_price)
    trades = []
    port_ret = []

    for date in all_dates:
        day_ret = {}
        for sym, df in data.items():
            mask = df["time"] == date
            if mask.any():
                idx = df.index[mask][0]
                day_ret[sym] = float(df["close"].iloc[idx] / df["close"].iloc[idx - 1] - 1) if idx > 0 else 0.0
            else:
                day_ret[sym] = 0.0

        ret_sum = 0.0
        cost_today = 0.0

        if date in rebal_dates:
            for sym, df in data.items():
                mask = df["time"] == date
                if not mask.any():
                    continue
                idx = df.index[mask][0]
                s = int(signals[sym].iloc[idx]) if idx < len(signals[sym]) else 0
                q = float(abs(scales[sym].iloc[idx])) if idx < len(scales[sym]) else 0.0
                price = float(df["close"].iloc[idx])

                old = positions.get(sym)
                if old is not None and (old[0] != s or s == 0):
                    # close cost
                    cost = old[1] * (_COST[sym]["spread_bps"] + _COST[sym]["commission_bps"]) * cost_mult / 10000
                    trades.append({"symbol": sym, "side": old[0], "pnl": old[0] * (price - old[2]) * old[1], "cost": cost})
                    cost_today += cost
                    positions.pop(sym, None)

                if s != 0 and q > 0:
                    positions[sym] = (s, q, price)

        for sym, pos in positions.items():
            ret_sum += pos[0] * pos[1] * day_ret.get(sym, 0.0)

        port_ret.append({"time": date, "return": ret_sum - cost_today})

    # close remaining
    for sym, pos in positions.items():
        df = data[sym]
        price = float(df["close"].iloc[-1])
        cost = pos[1] * (_COST[sym]["spread_bps"] + _COST[sym]["commission_bps"]) * cost_mult / 10000
        trades.append({"symbol": sym, "side": pos[0], "pnl": pos[0] * (price - pos[2]) * pos[1], "cost": cost})

    pdf = pd.DataFrame(port_ret)
    if len(pdf) > 1:
        sharpe = pdf["return"].mean() / pdf["return"].std() * np.sqrt(252) if pdf["return"].std() > 0 else 0.0
    else:
        sharpe = 0.0
    return {"portfolio_returns": pdf, "trades": trades,
            "metrics": {"sharpe": sharpe, "total_trades": len(trades),
                        "total_cost": sum(t["cost"] for t in trades)}}


def per_symbol_returns(data: dict, signals: dict) -> dict[str, pd.Series]:
    out = {}
    for sym, df in data.items():
        sret = signals[sym].shift(1) * df["close"].pct_change()
        out[sym] = sret.dropna()
    return out


def main() -> int:
    print("=" * 64)
    print("WS-A Trial 1033 — TSMOM 6-Symbol Breadth (formal)")
    print("=" * 64)

    data = load_data()
    if len(data) < 6:
        print("FAIL: not all 6 symbols loaded")
        return 1

    result = run_backtest(data, 1.0)
    m = result["metrics"]
    print(f"\nBase: Sharpe={m['sharpe']:.4f} trades={m['total_trades']} cost={m['total_cost']:.4f}")

    # per-symbol signal returns
    signals = {sym: compute_signal(df["close"])[0] for sym, df in data.items()}
    rbs = per_symbol_returns(data, signals)
    per_sym_sharpe = {s: round(float(r.mean() / r.std() * np.sqrt(252)), 3) if r.std() > 0 else 0.0 for s, r in rbs.items()}
    print(f"  per-symbol: {per_sym_sharpe}")

    # DK test
    dk = _verified_dk_test(pd.DataFrame(rbs), total_trades=m["total_trades"])
    dk_t = dk["dk_t_stat"]
    print(f"\nDK t={dk_t:.4f} verdict={dk.get('verdict')}")

    # DSR
    _ds = importlib.util.spec_from_file_location("dsr", str(_ROOT / "validation" / "deflated_sharpe.py"))
    _dsm = importlib.util.module_from_spec(_ds); _ds.loader.exec_module(_dsm)
    _nt = importlib.util.spec_from_file_location("nt", str(_ROOT / "validation" / "n_trials.py"))
    _ntm = importlib.util.module_from_spec(_nt); _nt.loader.exec_module(_ntm)
    n_trials = _ntm.get_reconciled_n_trials()
    pr = result["portfolio_returns"]["return"]
    dsr = _dsm.dsr_from_annualized(
        observed_sharpe=m["sharpe"], n_trials=n_trials, n_observations=len(pr),
        annualization_factor=252, skewness=float(pr.skew()), kurtosis=float(pr.kurtosis()) + 3.0,
    )
    print(f"DSR p={dsr.probability_alpha:.4f} pass={dsr.passes_threshold} (N={n_trials})")

    # SP2 institutional gates
    _tg = importlib.util.spec_from_file_location("_trial_gates", str(_ROOT / "scripts" / "_trial_gates.py"))
    _tgm = importlib.util.module_from_spec(_tg); _tg.loader.exec_module(_tgm)
    gates = _tgm.run_institutional_gates(
        portfolio_returns=pr, returns_by_symbol=rbs,
        observed_sharpe=m["sharpe"], n_trials=n_trials, n_bars=len(pr),
    )
    print(f"WFA mean={gates['wfa']['oos_sharpe_mean']} pass={gates['wfa']['pass']}")
    print(f"BootCI={gates['bootstrap_ci']} MinBTL_suf={gates['min_btl']['sufficient']}")

    # Jackknife (drop-one-symbol portfolio Sharpe)
    full_s = m["sharpe"]
    jk = {}
    for drop in UNIVERSE:
        sub = {s: df for s, df in data.items() if s != drop}
        r = run_backtest(sub, 1.0)
        jk[drop] = round(r["metrics"]["sharpe"], 3)
    jk_pass = all(abs(v - full_s) < 0.5 for v in jk.values())
    print(f"\nJackknife: {jk} full={full_s:.3f} pass={jk_pass}")

    # Cost stress
    stress = {f"{mult}x": round(run_backtest(data, mult)["metrics"]["sharpe"], 3) for mult in [1.5, 2.0]}
    stress_pass = all(v > 0 for v in stress.values())
    print(f"Cost-stress: {stress} pass={stress_pass}")

    # Label shuffle
    cs = pd.concat(rbs.values(), axis=1).mean(axis=1).dropna()
    obs_s = cs.mean() / cs.std() * np.sqrt(252)
    rng = np.random.default_rng(SEED)
    cnt = 0
    for _ in range(N_LABEL_SHUFFLES):
        s = cs * rng.choice([-1.0, 1.0], size=len(cs))
        sh = s.mean() / s.std() * np.sqrt(252) if s.std() > 0 else 0
        if sh >= obs_s:
            cnt += 1
    ls_p = cnt / N_LABEL_SHUFFLES
    ls_pass = ls_p <= 0.05
    print(f"Label-shuffle p={ls_p:.4f} pass={ls_pass}")

    # Gates
    dk_pass = dk_t > 2.0
    dsr_pass = dsr.passes_threshold
    wfa_pass = gates["wfa"]["pass"]
    boot_pass = gates["bootstrap_ci"]["pass"]
    minbtl_pass = gates["min_btl"]["sufficient"]
    passes = [dk_pass, dsr_pass, wfa_pass, boot_pass, minbtl_pass, jk_pass, stress_pass, ls_pass]
    names = ["DK", "DSR", "WFA", "BootCI", "MinBTL", "Jackknife", "CostStress", "LabelShuffle"]
    print("\n" + "=" * 64)
    print("GATE SUMMARY")
    for n_, p_ in zip(names, passes):
        print(f"  {n_:12s}: {'PASS' if p_ else 'FAIL'}")
    verdict = "PASS" if all(passes) else "REJECT"
    print(f"  -> {verdict}")

    artifact = {
        "trial_number": 1033,
        "id": "WS-A-TSMOM-6SYM",
        "strategy": "tsmom_252_6sym",
        "pre_registration": "research/pre_registration/trial_1033_tsmom_6sym.md",
        "executed_at": pd.Timestamp.utcnow().isoformat(),
        "universe": UNIVERSE,
        "metrics": m,
        "per_symbol_sharpe": per_sym_sharpe,
        "dk": {"t": dk_t, "verdict": dk.get("verdict")},
        "dsr": {"p": dsr.probability_alpha, "pass": dsr.passes_threshold, "n_trials": n_trials},
        "gates": gates,
        "jackknife": jk,
        "jackknife_pass": jk_pass,
        "cost_stress": stress,
        "cost_stress_pass": stress_pass,
        "label_shuffle": {"p": ls_p, "pass": ls_pass},
        "combined_verdict": verdict,
    }
    out = _ROOT / "reports" / "trial_1033_tsmom_6sym_results.json"
    out.write_text(json.dumps(artifact, indent=2, ensure_ascii=False, default=lambda o: bool(o)), encoding="utf-8")
    print(f"\n[SAVE] {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
