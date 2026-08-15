"""
Label-shuffle test for MEAN-REVERSION candidates.

Tests RSI-based, Bollinger-based, and Z-score mean-reversion strategies.
Structurally different from momentum — contrarian, fade-the-move.

Shuffles daily returns → rebuilds prices → re-runs strategy signal logic.
p-value = fraction of shuffled Sharpes >= real Sharpe.
If p > 0.05 → cannot reject null (no edge / chance).
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
    "XAUUSD": 0.30,
    "NAS100": 2.60,
    "EURUSD": 3.5,
}


def load_d1(symbol: str) -> pd.DataFrame:
    df = pd.read_csv(ROOT / "data" / f"{symbol}_D1.csv")
    ts = "time" if "time" in df.columns else "date"
    df[ts] = pd.to_datetime(df[ts])
    df = df[df[ts] >= "2005-01-01"].sort_values(ts).reset_index(drop=True)
    return df.rename(columns={ts: "time"}) if ts != "time" else df


# ── Mean-Reversion Signal Functions ──────────────────────────────────────────


def rsi_mean_reversion_signals(closes, rsi_period=14, oversold=30.0, overbought=70.0):
    """RSI mean reversion: buy oversold, sell overbought."""
    n = len(closes)
    signals = np.zeros(n, dtype=int)

    # Compute RSI
    rsi = np.full(n, 50.0)
    if n < rsi_period + 2:
        return signals

    gains = []
    losses = []
    for i in range(1, rsi_period + 1):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains) / rsi_period
    avg_loss = sum(losses) / rsi_period

    for i in range(rsi_period + 1, n):
        change = closes[i] - closes[i - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = (avg_gain * (rsi_period - 1) + gain) / rsi_period
        avg_loss = (avg_loss * (rsi_period - 1) + loss) / rsi_period
        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))

    # Generate signals
    position = 0
    for i in range(rsi_period + 1, n):
        if rsi[i] < oversold:
            position = 1  # buy oversold
        elif rsi[i] > overbought:
            position = -1  # sell overbought
        signals[i] = position

    return signals


def bollinger_mean_reversion_signals(closes, bb_period=20, bb_std=2.0):
    """Bollinger mean reversion: buy below lower BB, sell above upper BB."""
    n = len(closes)
    signals = np.zeros(n, dtype=int)

    if n < bb_period + 1:
        return signals

    position = 0
    for i in range(bb_period, n):
        window = closes[i - bb_period : i]
        sma = np.mean(window)
        std = np.std(window, ddof=0)
        upper = sma + bb_std * std
        lower = sma - bb_std * std

        if closes[i] < lower:
            position = 1  # buy below lower band
        elif closes[i] > upper:
            position = -1  # sell above upper band
        signals[i] = position

    return signals


def zscore_mean_reversion_signals(closes, lookback=20, entry_z=2.0, exit_z=0.5):
    """Z-score mean reversion: buy when z < -entry_z, sell when z > entry_z."""
    n = len(closes)
    signals = np.zeros(n, dtype=int)

    if n < lookback + 1:
        return signals

    position = 0
    for i in range(lookback, n):
        window = closes[i - lookback : i]
        mean = np.mean(window)
        std = np.std(window, ddof=0)
        if std == 0:
            signals[i] = position
            continue
        z = (closes[i] - mean) / std

        if z < -entry_z:
            position = 1  # buy oversold (z low)
        elif z > entry_z:
            position = -1  # sell overbought (z high)
        elif abs(z) < exit_z:
            position = 0  # exit when z normalizes
        signals[i] = position

    return signals


def rsi_with_ema_filter_signals(closes, rsi_period=14, oversold=35.0, overbought=65.0, ema_period=50):
    """RSI mean reversion with EMA trend filter: only trade in direction of EMA."""
    n = len(closes)
    signals = np.zeros(n, dtype=int)

    if n < max(rsi_period, ema_period) + 2:
        return signals

    # Compute RSI
    rsi = np.full(n, 50.0)
    gains = []
    losses = []
    for i in range(1, rsi_period + 1):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains) / rsi_period
    avg_loss = sum(losses) / rsi_period

    for i in range(rsi_period + 1, n):
        change = closes[i] - closes[i - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = (avg_gain * (rsi_period - 1) + gain) / rsi_period
        avg_loss = (avg_loss * (rsi_period - 1) + loss) / rsi_period
        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))

    # Compute EMA
    ema = np.full(n, closes[0])
    k = 2.0 / (ema_period + 1)
    for i in range(1, n):
        ema[i] = closes[i] * k + ema[i - 1] * (1 - k)

    # Generate signals with EMA filter
    position = 0
    for i in range(max(rsi_period, ema_period) + 1, n):
        if closes[i] > ema[i]:
            # Uptrend: only buy dips
            if rsi[i] < oversold:
                position = 1
        elif closes[i] < ema[i]:
            # Downtrend: only sell rallies
            if rsi[i] > overbought:
                position = -1
        signals[i] = position

    return signals


# ── Shared functions ─────────────────────────────────────────────────────────


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
            rets[i] -= cost_bps / 10000.0
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

    with np.errstate(divide="ignore", invalid="ignore"):
        open_ratio = np.where(closes != 0, opens / closes, 1.0)
        high_ratio = np.where(closes != 0, highs / closes, 1.0)
        low_ratio = np.where(closes != 0, lows / closes, 1.0)
    new_opens = new_closes * open_ratio
    new_highs = new_closes * high_ratio
    new_lows = new_closes * low_ratio
    new_highs = np.maximum(new_highs, np.maximum(new_opens, new_closes))
    new_lows = np.minimum(new_lows, np.minimum(new_opens, new_closes))
    return new_opens, new_highs, new_lows, new_closes


def run_case(name: str, symbol: str, signal_fn, cost_bps: float) -> dict:
    df = load_d1(symbol)
    opens = df["open"].values.astype(float)
    highs = df["high"].values.astype(float)
    lows = df["low"].values.astype(float)
    closes = df["close"].values.astype(float)

    sig = signal_fn(closes)
    real_rets = simulate_bar_returns(closes, sig, cost_bps)
    real_sharpe = sharpe_ann(real_rets)

    split = int(len(closes) * 0.8)
    oos_rets = real_rets[split:]
    oos_sharpe = sharpe_ann(oos_rets)

    null_sharpes = []
    for k in range(N_SHUFFLES):
        no, nh, nl, nc = rebuild_prices_from_shuffled_returns(opens, highs, lows, closes, seed=2000 + k)
        nsig = signal_fn(nc)
        nrets = simulate_bar_returns(nc, nsig, cost_bps)
        null_sharpes.append(sharpe_ann(nrets[split:]))

    null_arr = np.array(null_sharpes)
    p_value = float(np.mean(null_arr >= oos_sharpe))
    verdict = "EDGE_SURVIVES" if p_value < 0.05 and oos_sharpe > 0 else "NO_EDGE"

    n_trades = int(np.sum(np.abs(np.diff(sig)) > 0))

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
        "n_trades": n_trades,
        "verdict": verdict,
    }


def main() -> int:
    cases = [
        # ── RSI Mean Reversion ──
        ("RSI_MR_30_70_XAUUSD", "XAUUSD",
         lambda c: rsi_mean_reversion_signals(c, rsi_period=14, oversold=30, overbought=70),
         COST_RT_BPS["XAUUSD"]),
        ("RSI_MR_30_70_NAS100", "NAS100",
         lambda c: rsi_mean_reversion_signals(c, rsi_period=14, oversold=30, overbought=70),
         COST_RT_BPS["NAS100"]),
        # ── RSI with EMA filter ──
        ("RSI_EMA_MR_XAUUSD", "XAUUSD",
         lambda c: rsi_with_ema_filter_signals(c, rsi_period=14, oversold=35, overbought=65, ema_period=50),
         COST_RT_BPS["XAUUSD"]),
        ("RSI_EMA_MR_NAS100", "NAS100",
         lambda c: rsi_with_ema_filter_signals(c, rsi_period=14, oversold=35, overbought=65, ema_period=50),
         COST_RT_BPS["NAS100"]),
        # ── Bollinger Mean Reversion ──
        ("BB_MR_20_2_XAUUSD", "XAUUSD",
         lambda c: bollinger_mean_reversion_signals(c, bb_period=20, bb_std=2.0),
         COST_RT_BPS["XAUUSD"]),
        ("BB_MR_20_2_NAS100", "NAS100",
         lambda c: bollinger_mean_reversion_signals(c, bb_period=20, bb_std=2.0),
         COST_RT_BPS["NAS100"]),
        # ── Z-Score Mean Reversion ──
        ("ZSCORE_MR_20_2_XAUUSD", "XAUUSD",
         lambda c: zscore_mean_reversion_signals(c, lookback=20, entry_z=2.0),
         COST_RT_BPS["XAUUSD"]),
        ("ZSCORE_MR_20_2_NAS100", "NAS100",
         lambda c: zscore_mean_reversion_signals(c, lookback=20, entry_z=2.0),
         COST_RT_BPS["NAS100"]),
    ]

    results = []
    print("=" * 70)
    print(f"  LABEL SHUFFLE — MEAN-REVERSION — {N_SHUFFLES} iterations per case")
    print("=" * 70)
    for name, sym, fn, cost in cases:
        print(f"\n  Running {name}...", flush=True)
        r = run_case(name, sym, fn, cost)
        results.append(r)
        print(
            f"    OOS Sharpe={r['oos_sharpe']}  p={r['p_value']}  "
            f"null_p95={r['null_p95_sharpe']}  trades={r['n_trades']}  → {r['verdict']}",
            flush=True,
        )

    survives = [r for r in results if r["verdict"] == "EDGE_SURVIVES"]
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "n_shuffles": N_SHUFFLES,
        "method": "shuffle log-returns, rebuild OHLC, re-run signals, OOS last 20%",
        "strategy_class": "mean-reversion",
        "survives": [r["name"] for r in survives],
        "results": results,
        "honest_note": (
            "EDGE_SURVIVES means p<0.05 on label-shuffle OOS only. "
            "Still not live-ready without pooled multi-asset DK + cost stress + paper."
        ),
    }
    out = ROOT / "reports" / "label_shuffle_mr_results.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\n  Survives: {payload['survives'] or 'NONE'}")
    print(f"  Saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
