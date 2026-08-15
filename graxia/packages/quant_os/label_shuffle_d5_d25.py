"""Label shuffle — Donchian(5) + Donchian(25) comparison"""
import numpy as np, pandas as pd, json
from pathlib import Path

BASE = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os")
DATA = BASE / "data" / "EURUSD_D1_clean.csv"
N_SHUFFLES = 100
COST = 3.4
WARMUP = 200

df = pd.read_csv(DATA)
O, H, L, C = df["Open"].values, df["High"].values, df["Low"].values, df["Close"].values
n = len(C)
sp = int(n * 0.8)


def gen_signals(highs, lows, closes, period):
    signals = np.zeros(len(closes), dtype=int)
    pos = 0
    for i in range(period, len(closes)):
        hh = np.max(highs[max(0, i - period) : i])
        ll = np.min(lows[max(0, i - period) : i])
        if closes[i] > hh:
            pos = 1
        elif closes[i] < ll:
            pos = -1
        signals[i] = pos
    return signals


def simulate(opens, closes, signals):
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


print("=" * 70)
print("  LABEL SHUFFLE — Donchian(5) vs Donchian(25)")
print("=" * 70)

for period in [5, 25]:
    print(f"\n--- Donchian({period}) ---")

    # Real
    sigs = gen_signals(H, L, C, period)
    real_t = simulate(O, C, sigs)
    real_s = sharpe(real_t)
    real_wr = sum(1 for x in real_t if x > 0) / max(1, len(real_t)) * 100
    print(f"  Real:  Sharpe={real_s:.4f}, Trades={len(real_t)}, WR={real_wr:.1f}%")

    # Shuffled
    idx = np.arange(n)
    shuf = []
    for k in range(N_SHUFFLES):
        si = idx.copy()
        np.random.shuffle(si)
        sS = gen_signals(H[si], L[si], C[si], period)
        st = simulate(O[si], C[si], sS)
        shuf.append(sharpe(st))
        if (k + 1) % 25 == 0:
            print(f"    [{k+1}/{N_SHUFFLES}] mean={np.mean(shuf):.3f}")

    shuf = np.array(shuf)
    mu, sd = np.mean(shuf), np.std(shuf, ddof=1)
    p = np.mean(shuf >= real_s)
    percent = np.mean(shuf < real_s) * 100
    z = (real_s - mu) / (sd + 1e-10)

    print(f"  Null:  mean={mu:.4f}, std={sd:.4f}")
    print(f"  p-val: {p:.4f} | z={z:.2f} | %ile={percent:.1f}%")
    print(f"  95% CI: [{np.percentile(shuf, 2.5):.2f}, {np.percentile(shuf, 97.5):.2f}]")
    if p < 0.01:
        print(f"  *** SIGNIFICANT p < 0.01 ***")
    elif p < 0.05:
        print(f"  ** SIGNIFICANT p < 0.05 **")
    elif p < 0.10:
        print(f"  * Suggestive p < 0.10 *")
    else:
        print(f"  NOT significant (p = {p:.4f})")

print(f"\n{'='*70}")
print("  Complete")
