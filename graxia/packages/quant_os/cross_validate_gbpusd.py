"""Cross-validate Donchian(25)+Vol>1.0 on GBPUSD D1 — robustness check"""
import numpy as np, pandas as pd, json
from pathlib import Path

BASE = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os")
DATA = BASE / "data" / "GBPUSD_D1.csv"
N_SHUFFLES = 100
COST = 3.4
TRAIN = 0.80
WARMUP = 200
PERIOD = 25
VOL_THRESH = 1.0


def vol_filtered_signals(highs, lows, closes, period, vol_thresh):
    n = len(closes)
    atr = np.zeros(n)
    for i in range(14, n):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]),
                 abs(lows[i] - closes[i - 1]))
        atr[i] = (atr[i - 1] * 13 + tr) / 14 if atr[i - 1] else tr
    atr_ratio = np.where(closes > 0, atr / closes, 0)
    med_ratio = np.nanmedian(atr_ratio[200:])

    base = np.zeros(n, dtype=int)
    pos = 0
    for i in range(period, n):
        hh = np.max(highs[max(0, i - period):i])
        ll = np.min(lows[max(0, i - period):i])
        if closes[i] > hh:
            pos = 1
        elif closes[i] < ll:
            pos = -1
        base[i] = pos

    filtered = np.zeros(n, dtype=int)
    fpos = 0
    for i in range(n):
        if atr_ratio[i] > med_ratio * vol_thresh or np.isnan(atr_ratio[i]) or i < 200:
            if base[i] != 0:
                fpos = base[i]
            filtered[i] = fpos
        else:
            filtered[i] = 0
    return filtered


def simulate(opens, closes, signals):
    n = len(closes)
    sp = int(n * TRAIN)
    pos, entry_px = 0, 0.0
    trades = []
    for i in range(WARMUP, n):
        bar = "OOS" if i >= sp else "IS"
        sig = signals[i]
        if pos == 0 and sig != 0:
            entry_px = opens[i + 1] if i + 1 < n else closes[i]
            pos = sig
        elif pos != 0 and sig != pos:
            exit_px = opens[i + 1] if i + 1 < n else closes[i]
            r = (exit_px - entry_px) / entry_px if pos == 1 else (entry_px - exit_px) / entry_px
            if bar == "OOS":
                trades.append(r - COST / 10000.0)
            pos = 0
            if sig != 0:
                entry_px = exit_px
                pos = sig
    return trades


def sharpe(trades):
    if len(trades) < 5: return 0.0
    return float(np.mean(trades) / (np.std(trades, ddof=1) + 1e-10) * np.sqrt(252))


print("=" * 60)
print("  CROSS-VALIDATION — GBPUSD D1")
print("  Donchian(25) + Vol > 1.0× median ATR")
print("=" * 60)

df = pd.read_csv(DATA)
# Normalize column names to TitleCase
df.columns = [c.capitalize() for c in df.columns]
if "Date" not in df.columns and "Time" in df.columns:
    df["Date"] = pd.to_datetime(df["Time"], errors="coerce")
if "Date" in df.columns:
    df = df.dropna(subset=["Date"])

O, H, L, C = df["Open"].values, df["High"].values, df["Low"].values, df["Close"].values
n = len(C)

# Skip early data (GBP pre-2000 is monthly, not D1)
if "Date" in df.columns and df["Date"].min().year < 2000:
    df = df[df["Date"] > "2000-01-01"].reset_index(drop=True)
    O, H, L, C = df["Open"].values, df["High"].values, df["Low"].values, df["Close"].values
    n = len(C)
    print(f"\nGBPUSD D1 (filtered post-2000): {n} bars ({df['Date'].min().date()} to {df['Date'].max().date()})")
else:
    print(f"\nGBPUSD D1: {n} bars ({df['Date'].min().date()} to {df['Date'].max().date()})")

# Real
real_sigs = vol_filtered_signals(H, L, C, PERIOD, VOL_THRESH)
real_t = simulate(O, C, real_sigs)
real_s = sharpe(real_t)
real_wr = sum(1 for x in real_t if x > 0) / max(1, len(real_t)) * 100

print(f"\nReal: Sharpe={real_s:.4f}, Trades={len(real_t)}, WR={real_wr:.1f}%")

# Shuffle
idx = np.arange(n)
shuf = []
for k in range(N_SHUFFLES):
    si = idx.copy()
    np.random.shuffle(si)
    sS = vol_filtered_signals(H[si], L[si], C[si], PERIOD, VOL_THRESH)
    st = simulate(O[si], C[si], sS)
    shuf.append(sharpe(st))
    if (k + 1) % 25 == 0:
        print(f"  [{k+1}/{N_SHUFFLES}] mean={np.mean(shuf):.3f}")

shuf = np.array(shuf)
mu, sd = np.mean(shuf), np.std(shuf, ddof=1)
p = np.mean(shuf >= real_s)
z = (real_s - mu) / (sd + 1e-10)

print(f"\nNull: mean={mu:.4f}, std={sd:.4f}")
print(f"z-score: {z:.2f}")
print(f"p-value: {p:.4f}")

if p < 0.01:
    v = "*** SIGNIFICANT p < 0.01 ***"
elif p < 0.05:
    v = "** SIGNIFICANT p < 0.05 **"
elif p < 0.10:
    v = "* Suggestive p < 0.10 *"
else:
    v = f"NOT significant (p = {p:.4f})"
print(f"  {v}")

# Also test plain Donchian(25) for comparison
print("\n--- Plain Donchian(25) vs D25+Vol>1.0 on GBPUSD ---")

# Plain Donchian
def donchian_signals(highs, lows, closes, period):
    n = len(closes)
    base = np.zeros(n, dtype=int)
    pos = 0
    for i in range(period, n):
        hh = np.max(highs[max(0, i - period):i])
        ll = np.min(lows[max(0, i - period):i])
        if closes[i] > hh: pos = 1
        elif closes[i] < ll: pos = -1
        base[i] = pos
    return base

plain_sigs = donchian_signals(H, L, C, PERIOD)
plain_t = simulate(O, C, plain_sigs)
plain_s = sharpe(plain_t)
plain_wr = sum(1 for x in plain_t if x > 0) / max(1, len(plain_t)) * 100

print(f"  Plain Donchian(25): Sharpe={plain_s:.4f}, Trades={len(plain_t)}, WR={plain_wr:.1f}%")
print(f"  D25+Vol>1.0:       Sharpe={real_s:.4f}, Trades={len(real_t)}, WR={real_wr:.1f}%")

# Summary
print("\n" + "=" * 60)
print("  ROBUSTNESS VERDICT")
print("=" * 60)
if p < 0.05:
    print(f"  EDGE CONFIRMED on GBPUSD! (p={p:.4f})")
    print(f"  Strategy is robust across EURUSD and GBPUSD")
elif p < 0.10:
    print(f"  EDGE SUGGESTIVE on GBPUSD (p={p:.4f})")
else:
    print(f"  EDGE NOT CONFIRMED on GBPUSD (p={p:.4f})")
    print(f"  Strategy may be EURUSD-specific")

out = BASE / "reports" / "gbpusd_robustness.json"
with open(out, "w") as f:
    json.dump({"pair": "GBPUSD", "period": PERIOD, "vol_thresh": VOL_THRESH,
               "real_sharpe": real_s, "real_trades": len(real_t), "real_wr": real_wr,
               "p_value": float(p), "z_score": float(z), "verdict": v,
               "null_mean": float(mu), "null_std": float(sd),
               "plain_donchian_sharpe": plain_s}, f, indent=2)
print(f"\nSaved: {out}")
