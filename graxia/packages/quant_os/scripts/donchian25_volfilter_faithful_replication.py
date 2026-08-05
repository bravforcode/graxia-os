"""
Faithful replication of the "Donchian(25)+Vol Filter" GENUINE EDGE claim
=========================================================================
reports/final_strategy_summary.json (2026-07-10T21:48) claims p<0.001 and
26-27 OOS trades on EURUSD/GBPUSD for this strategy, contradicting the
same-day search report (17:56, p=0.08, "Accept no edge found") and never
matching any locatable, rerunnable script in the repo.

The first tie-breaker attempt (deep_dive_donchian25_volfilter_validation.py,
using the StrategyValidator harness with ATR SL/TP exits) is NOT a faithful
reproduction: it produced only 1 trade (EURUSD) and 5 trades (GBPUSD) over
14k+ bars, vs. the claimed 26-27 OOS trades. That harness's exit logic
(ATR-based SL/TP) holds a position open indefinitely until a stop or target
is hit, starving the strategy of new entries -- a different strategy in
all but name. That run is DISCARDED as a strawman, not evidence of anything.

This script instead clones the *exact* method used everywhere else in this
research trail -- gen_bb_breakout / simulate / sharpe / 100-shuffle
permutation test from final_label_shuffle_and_report.py -- and swaps in a
Donchian(25) + ATR-ratio vol-filter signal generator matching
strategies/donchian_rsi.py's filter logic (current TR/price ratio vs.
trailing-200-bar median ratio, gated by vol_filter_pctile). Same
signal-reversal position holding, same WARMUP/COST/split, same shuffle test.

Data:
  EURUSD: data/EURUSD_D1_clean.csv (the exact file the original script used)
  GBPUSD: no GBPUSD_D1_clean.csv exists in the repo. GBPUSD_D1.csv contains
    a garbage extended history back to 1900 (clearly fabricated/placeholder
    pre-modern data), so it is date-filtered to 2003-12-01..2026-07-09 --
    the same window EURUSD_D1_clean.csv covers (5863 vs 5865 rows, a close
    match consistent with the same cleaning approach) -- as the closest
    faithful reconstruction available. This is NOT the literal file used
    for the original GBPUSD claim (no such file exists to recover), so
    treat the GBPUSD result as best-effort, not an exact replication.

A validity gate is enforced: if the replicated trade count is not roughly
in the neighborhood of the claimed 26-27 OOS trades, the replication itself
is flagged as non-faithful rather than its p-value being reported as if
it settled anything.
"""

import numpy as np
import pandas as pd
from pathlib import Path

BASE = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os")
N_SHUFFLES = 100
COST = 3.4
WARMUP = 200

CLAIMED_OOS_TRADES = {"EURUSD": 26, "GBPUSD": 27}


def gen_donchian_vf_signals(highs, lows, closes, period=25, vol_filter_pctile=1.0, vol_lookback=200):
    """Donchian(period) breakout gated by current TR/price ratio vs trailing
    median ratio * vol_filter_pctile -- mirrors strategies/donchian_rsi.py."""
    n = len(closes)
    signals = np.zeros(n, dtype=int)
    pos = 0
    for i in range(period, n):
        hh = np.max(highs[i - period : i])
        ll = np.min(lows[i - period : i])
        direction = 0
        if closes[i] > hh:
            direction = 1
        elif closes[i] < ll:
            direction = -1

        if direction != 0:
            lb = min(vol_lookback, i)
            start = i - lb
            seg_c = closes[start:i]
            seg_h = highs[start:i]
            seg_l = lows[start:i]
            mask = seg_c > 0
            if mask.any():
                hist_ratios = (seg_h[mask] - seg_l[mask]) / seg_c[mask]
                median_ratio = np.median(hist_ratios)
                current_ratio = (highs[i] - lows[i]) / closes[i]
                if current_ratio < median_ratio * vol_filter_pctile:
                    direction = 0  # vol filter blocks this breakout

        if direction != 0:
            pos = direction
        signals[i] = pos
    return signals


def simulate(opens, closes, signals, n, sp):
    """Identical to final_label_shuffle_and_report.py's simulate()."""
    pos, entry_px = 0, 0.0
    trades = []
    for i in range(WARMUP, n):
        bar = "OOS" if i >= sp else "IS"
        sig = signals[i]
        if pos == 0 and sig != 0:
            ei = i + 1 if i + 1 < n else i
            entry_px = opens[ei] if i + 1 < n else closes[i]
            pos = sig
        elif pos != 0 and sig != pos:
            ei = i + 1 if i + 1 < n else i
            exit_px = opens[ei] if i + 1 < n else closes[i]
            r = (exit_px - entry_px) / entry_px if pos == 1 else (entry_px - exit_px) / entry_px
            if bar == "OOS":
                trades.append(r - COST / 10000.0)
            pos = 0
            if sig != 0:
                entry_px = exit_px
                pos = sig
    return trades


def sharpe(trades):
    if len(trades) < 5:
        return 0.0
    return float(np.mean(trades) / (np.std(trades, ddof=1) + 1e-10) * np.sqrt(252))


def load_eurusd():
    df = pd.read_csv(BASE / "data" / "EURUSD_D1_clean.csv")
    return df["Open"].values, df["High"].values, df["Low"].values, df["Close"].values


def load_gbpusd_reconstructed():
    df = pd.read_csv(BASE / "data" / "GBPUSD_D1.csv")
    df["time"] = pd.to_datetime(df["time"])
    sub = df[(df["time"] >= "2003-12-01") & (df["time"] <= "2026-07-09")].reset_index(drop=True)
    return sub["open"].values, sub["high"].values, sub["low"].values, sub["close"].values


def run(symbol: str, O, H, L, C) -> dict:
    n = len(C)
    sp = int(n * 0.8)

    print("=" * 70)
    print(f"  FAITHFUL REPLICATION — Donchian(25)+VolFilter(1.0x median ATR ratio) — {symbol}")
    print("=" * 70)

    sigs = gen_donchian_vf_signals(H, L, C, period=25, vol_filter_pctile=1.0, vol_lookback=200)
    real_t = simulate(O, C, sigs, n, sp)
    real_s = sharpe(real_t)
    real_wr = sum(1 for x in real_t if x > 0) / max(1, len(real_t)) * 100

    claimed = CLAIMED_OOS_TRADES[symbol]
    faithful = abs(len(real_t) - claimed) <= max(5, claimed // 3)

    print(f"\nReal:  Sharpe={real_s:.4f}, OOS Trades={len(real_t)}, WR={real_wr:.1f}%")
    print(f"Claimed OOS trades: {claimed}  |  Replication trade count {'MATCHES (roughly)' if faithful else 'DOES NOT MATCH'} the claim")

    idx = np.arange(n)
    shuf = []
    for k in range(N_SHUFFLES):
        si = idx.copy()
        np.random.shuffle(si)
        sS = gen_donchian_vf_signals(H[si], L[si], C[si], period=25, vol_filter_pctile=1.0, vol_lookback=200)
        st = simulate(O[si], C[si], sS, n, sp)
        shuf.append(sharpe(st))
        if (k + 1) % 25 == 0:
            print(f"  [{k+1}/{N_SHUFFLES}] mean={np.mean(shuf):.3f}")

    shuf = np.array(shuf)
    mu, sd = np.mean(shuf), np.std(shuf, ddof=1)
    p = np.mean(shuf >= real_s)
    z = (real_s - mu) / (sd + 1e-10)

    print(f"\nNull:  mean={mu:.4f}, std={sd:.4f}")
    print(f"p-val: {p:.4f} | z={z:.2f}")

    if p < 0.01:
        verdict = "*** SIGNIFICANT p < 0.01 ***"
    elif p < 0.05:
        verdict = "** SIGNIFICANT p < 0.05 **"
    elif p < 0.10:
        verdict = "* Suggestive p < 0.10 *"
    else:
        verdict = f"NOT significant (p = {p:.4f})"
    print(f"\n{verdict}")

    return {
        "symbol": symbol,
        "n_bars": n,
        "oos_trades": len(real_t),
        "claimed_oos_trades": claimed,
        "trade_count_faithful": faithful,
        "sharpe": real_s,
        "win_rate_pct": real_wr,
        "null_mean": float(mu),
        "null_std": float(sd),
        "p_value": float(p),
        "z_score": float(z),
        "verdict": verdict,
    }


def main():
    results = []
    results.append(run("EURUSD", *load_eurusd()))
    results.append(run("GBPUSD", *load_gbpusd_reconstructed()))

    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    for r in results:
        print(
            f"{r['symbol']}: {r['oos_trades']} OOS trades (claimed {r['claimed_oos_trades']}, "
            f"faithful={r['trade_count_faithful']}), Sharpe={r['sharpe']:.4f}, p={r['p_value']:.4f} -> {r['verdict']}"
        )

    import json
    out = BASE / "reports" / "donchian25_volfilter_faithful_replication.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
