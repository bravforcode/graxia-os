"""
Label-shuffle test for top D1 single-asset candidates.

Shuffles daily returns → rebuilds prices → re-runs strategy signal logic.
p-value = fraction of shuffled Sharpes >= real Sharpe.
If p > 0.05 → cannot reject null (no edge / chance).

Does NOT use sacred holdout.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

ROOT = Path(__file__).resolve().parent.parent
N_SHUFFLES = 200
# Corrected costs from config/cost_calibration.json (MEASURED, not assumed)
COST_RT_BPS = {
    "XAUUSD": 0.30,  # Pepperstone Razor: $0 commission, measured spread+slip
    "NAS100": 2.60,  # Pepperstone Razor: measured spread+slip
    "EURUSD": 3.5,   # FX: spread + $7/rt commission (unchanged)
}


def load_d1(symbol: str) -> pd.DataFrame:
    df = pd.read_csv(ROOT / "data" / f"{symbol}_D1.csv")
    ts = "time" if "time" in df.columns else "date"
    df[ts] = pd.to_datetime(df[ts])
    df = df[df[ts] >= "2005-01-01"].sort_values(ts).reset_index(drop=True)
    return df.rename(columns={ts: "time"}) if ts != "time" else df


def donchian_signals(highs, lows, closes, period: int) -> np.ndarray:
    n = len(closes)
    signals = np.zeros(n, dtype=int)
    position = 0
    for i in range(period, n):
        hh = np.max(highs[i - period : i])
        ll = np.min(lows[i - period : i])
        if closes[i] > hh:
            position = 1
        elif closes[i] < ll:
            position = -1
        signals[i] = position
    return signals


def momentum_signals(closes, lookback: int) -> np.ndarray:
    n = len(closes)
    signals = np.zeros(n, dtype=int)
    for i in range(lookback + 1, n):
        ret = closes[i] / closes[i - lookback] - 1.0
        if ret > 0:
            signals[i] = 1
        elif ret < 0:
            signals[i] = -1
    return signals


def simulate_bar_returns(closes, signals, cost_bps: float) -> np.ndarray:
    """Position-held bar returns with round-trip cost on flips."""
    n = len(closes)
    rets = np.zeros(n)
    pos = 0
    for i in range(1, n):
        bar_ret = closes[i] / closes[i - 1] - 1.0
        rets[i] = pos * bar_ret
        new_pos = int(signals[i])
        if new_pos != pos and new_pos != 0:
            rets[i] -= cost_bps / 10000.0  # pay cost on entry/flip
            pos = new_pos
        elif new_pos == 0 and pos != 0:
            rets[i] -= cost_bps / 10000.0
            pos = 0
        else:
            pos = new_pos
    return rets


def sharpe_ann(rets: np.ndarray) -> float:
    r = rets[np.isfinite(rets)]
    if len(r) < 30:
        return 0.0
    mu = float(np.mean(r))
    sd = float(np.std(r, ddof=1))
    if sd <= 0:
        return 0.0
    return mu / sd * math.sqrt(252)


def rebuild_prices_from_shuffled_returns(opens, highs, lows, closes, seed: int):
    """Shuffle log-returns, rebuild OHLC preserving relative bar shape."""
    rng = np.random.default_rng(seed)
    log_rets = np.diff(np.log(closes))
    shuffled = rng.permutation(log_rets)
    new_closes = np.zeros_like(closes)
    new_closes[0] = closes[0]
    for i in range(1, len(closes)):
        new_closes[i] = new_closes[i - 1] * math.exp(shuffled[i - 1])

    # Scale OHLC around close proportionally
    with np.errstate(divide="ignore", invalid="ignore"):
        open_ratio = np.where(closes != 0, opens / closes, 1.0)
        high_ratio = np.where(closes != 0, highs / closes, 1.0)
        low_ratio = np.where(closes != 0, lows / closes, 1.0)
    new_opens = new_closes * open_ratio
    new_highs = new_closes * high_ratio
    new_lows = new_closes * low_ratio
    # Ensure high >= max(o,c) and low <= min(o,c)
    new_highs = np.maximum(new_highs, np.maximum(new_opens, new_closes))
    new_lows = np.minimum(new_lows, np.minimum(new_opens, new_closes))
    return new_opens, new_highs, new_lows, new_closes


def run_case(name: str, symbol: str, signal_fn, cost_bps: float) -> dict:
    df = load_d1(symbol)
    opens = df["open"].values.astype(float)
    highs = df["high"].values.astype(float)
    lows = df["low"].values.astype(float)
    closes = df["close"].values.astype(float)

    sig = signal_fn(highs, lows, closes)
    real_rets = simulate_bar_returns(closes, sig, cost_bps)
    real_sharpe = sharpe_ann(real_rets)
    real_mean = float(np.mean(real_rets))

    # OOS = last 20%
    split = int(len(closes) * 0.8)
    oos_rets = real_rets[split:]
    oos_sharpe = sharpe_ann(oos_rets)

    null_sharpes = []
    for k in range(N_SHUFFLES):
        no, nh, nl, nc = rebuild_prices_from_shuffled_returns(opens, highs, lows, closes, seed=1000 + k)
        nsig = signal_fn(nh, nl, nc)
        nrets = simulate_bar_returns(nc, nsig, cost_bps)
        null_sharpes.append(sharpe_ann(nrets[split:]))  # compare on OOS window length

    null_arr = np.array(null_sharpes)
    p_value = float(np.mean(null_arr >= oos_sharpe))
    verdict = "EDGE_SURVIVES" if p_value < 0.05 and oos_sharpe > 0 else "NO_EDGE"

    return {
        "name": name,
        "symbol": symbol,
        "n_bars": len(closes),
        "cost_rt_bps": cost_bps,
        "full_sharpe": round(real_sharpe, 4),
        "oos_sharpe": round(oos_sharpe, 4),
        "oos_mean_ret": round(float(np.mean(oos_rets)), 8),
        "null_mean_sharpe": round(float(np.mean(null_arr)), 4),
        "null_p95_sharpe": round(float(np.percentile(null_arr, 95)), 4),
        "p_value": round(p_value, 4),
        "n_shuffles": N_SHUFFLES,
        "verdict": verdict,
    }


def main() -> int:
    cases = [
        (
            "Donchian_10_XAUUSD",
            "XAUUSD",
            lambda h, l, c: donchian_signals(h, l, c, 10),
            COST_RT_BPS["XAUUSD"],
        ),
        (
            "Donchian_55_NAS100",
            "NAS100",
            lambda h, l, c: donchian_signals(h, l, c, 55),
            COST_RT_BPS["NAS100"],
        ),
        (
            "Momentum126_NAS100",
            "NAS100",
            lambda h, l, c: momentum_signals(c, 126),
            COST_RT_BPS["NAS100"],
        ),
        (
            "Hybrid60_NAS100",
            "NAS100",
            lambda h, l, c: momentum_signals(c, 60),
            COST_RT_BPS["NAS100"],
        ),
        (
            "Donchian_20_XAUUSD",
            "XAUUSD",
            lambda h, l, c: donchian_signals(h, l, c, 20),
            COST_RT_BPS["XAUUSD"],
        ),
    ]

    results = []
    print("=" * 70)
    print(f"  LABEL SHUFFLE — {N_SHUFFLES} iterations per case")
    print("=" * 70)
    for name, sym, fn, cost in cases:
        print(f"\n  Running {name}...", flush=True)
        r = run_case(name, sym, fn, cost)
        results.append(r)
        print(
            f"    OOS Sharpe={r['oos_sharpe']}  p={r['p_value']}  "
            f"null_p95={r['null_p95_sharpe']}  → {r['verdict']}",
            flush=True,
        )

    survives = [r for r in results if r["verdict"] == "EDGE_SURVIVES"]
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "n_shuffles": N_SHUFFLES,
        "method": "shuffle log-returns, rebuild OHLC, re-run signals, OOS last 20%",
        "survives": [r["name"] for r in survives],
        "results": results,
        "honest_note": (
            "EDGE_SURVIVES means p<0.05 on label-shuffle OOS only. "
            "Still not live-ready without pooled multi-asset DK + cost stress + paper."
        ),
    }
    out = ROOT / "reports" / "label_shuffle_top_results.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\n  Survives: {payload['survives'] or 'NONE'}")
    print(f"  Saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
