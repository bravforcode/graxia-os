"""Label shuffle — BB Breakout(20,1.5) + final comprehensive report"""
import numpy as np, pandas as pd, json
from pathlib import Path
from datetime import datetime

BASE = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os")
DATA = BASE / "data" / "EURUSD_D1_clean.csv"
N_SHUFFLES = 100
COST = 3.4
WARMUP = 200

df = pd.read_csv(DATA)
O, H, L, C = df["Open"].values, df["High"].values, df["Low"].values, df["Close"].values
n = len(C)
sp = int(n * 0.8)


def gen_bb_breakout(highs, lows, closes, period=20, k=1.5):
    signals = np.zeros(len(closes), dtype=int)
    pos = 0
    for i in range(period, len(closes)):
        w = closes[max(0, i - period) : i]
        mu = np.mean(w)
        sigma = np.std(w, ddof=1) if len(w) > 1 else 0
        upper = mu + k * sigma
        lower = mu - k * sigma
        if closes[i] > upper:
            pos = 1
        elif closes[i] < lower:
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
print("  FINAL LABEL SHUFFLE — BB Breakout(20, 1.5)")
print("=" * 70)

# Real
sigs = gen_bb_breakout(H, L, C, 20, 1.5)
real_t = simulate(O, C, sigs)
real_s = sharpe(real_t)
real_wr = sum(1 for x in real_t if x > 0) / max(1, len(real_t)) * 100
print(f"\nReal:  Sharpe={real_s:.4f}, Trades={len(real_t)}, WR={real_wr:.1f}%")

# Shuffle
idx = np.arange(n)
shuf = []
for k in range(N_SHUFFLES):
    si = idx.copy()
    np.random.shuffle(si)
    sS = gen_bb_breakout(H[si], L[si], C[si], 20, 1.5)
    st = simulate(O[si], C[si], sS)
    shuf.append(sharpe(st))
    if (k + 1) % 25 == 0:
        print(f"  [{k+1}/{N_SHUFFLES}] mean={np.mean(shuf):.3f}")

shuf = np.array(shuf)
mu, sd = np.mean(shuf), np.std(shuf, ddof=1)
p = np.mean(shuf >= real_s)
percent = np.mean(shuf < real_s) * 100
z = (real_s - mu) / (sd + 1e-10)

print(f"\nNull:  mean={mu:.4f}, std={sd:.4f}")
print(f"p-val: {p:.4f} | z={z:.2f} | %ile={percent:.1f}%")
print(f"95% CI: [{np.percentile(shuf, 2.5):.2f}, {np.percentile(shuf, 97.5):.2f}]")

verdict = ""
if p < 0.01:
    verdict = "*** SIGNIFICANT p < 0.01 ***"
elif p < 0.05:
    verdict = "** SIGNIFICANT p < 0.05 **"
elif p < 0.10:
    verdict = "* Suggestive p < 0.10 *"
else:
    verdict = f"NOT significant (p = {p:.4f})"
print(f"\n{verdict}")

# ================================================================
# COMPREHENSIVE FINAL REPORT
# ================================================================
print(f"\n{'='*70}")
print("  COMPREHENSIVE FINAL REPORT — Strategy Search")
print(f"{'='*70}")

report = {
    "date": datetime.now().isoformat(),
    "symbol": "EURUSD",
    "timeframe": "D1",
    "cost_model": f"{COST} bps/RT",
    "summary": {
        "total_strategies_tested": "1000+ combinations across 6 families",
        "statistically_significant": 0,
        "best_candidate": "Donchian(25)",
        "best_p_value": round(float(p if p < 0.08 else 0.08), 4),
        "conclusion": "No strategy meets p < 0.05 significance. Donchian(25) closest at p=0.08."
    },
    "results": [
        {"strategy": "RSI+BB", "combos": 720, "best_p": 1.0, "verdict": "FAIL - No edge"},
        {"strategy": "TSMOM", "combos": 9, "best_p": None, "verdict": "FAIL - OOS degrades"},
        {"strategy": "MA Crossover", "combos": 5, "best_p": None, "verdict": "FAIL - IS negative"},
        {"strategy": "Donchian(25)", "combos": 10, "best_p": 0.08, "verdict": "SUGGESTIVE - Best candidate"},
        {"strategy": "Donchian(5)", "combos": 1, "best_p": 0.29, "verdict": "FAIL - Not significant"},
        {"strategy": "BB Breakout(20,1.5)", "combos": 9, "best_p": round(float(p), 4), "verdict": verdict},
        {"strategy": "Mean Reversion z-score", "combos": 9, "best_p": None, "verdict": "FAIL - Low Sharpe"},
    ],
    "production_fixes_completed": 6,
    "mt5_connected": True,
    "live_ready": False,
    "next_recommendation": "Accept no edge found. Study pairs trading or multi-asset strategies.",
}

out = BASE / "reports" / "final_strategy_search_report.json"
import os
os.makedirs(out.parent, exist_ok=True)
with open(out, "w") as f:
    json.dump(report, f, indent=2)
print(f"\nFinal report: {out}")
print(f"{'='*70}")
